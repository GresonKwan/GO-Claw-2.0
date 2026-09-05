//! Real loopback TLS and wire-format faults. Test-only ephemeral CA/key; no
//! connection to a release server or production trust-root override.
use super::*;
use base64::Engine;
use std::{
    net::TcpListener,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
    thread,
};

struct Server {
    url: String,
    client: Transport,
    requests: Arc<Mutex<Vec<String>>>,
    done: Arc<AtomicBool>,
    worker: Option<thread::JoinHandle<()>>,
}
impl Drop for Server {
    fn drop(&mut self) {
        self.done.store(true, Ordering::Relaxed);
        if let Some(worker) = self.worker.take() {
            worker.join().unwrap();
        }
    }
}

fn server(responses: Vec<Vec<u8>>) -> Server {
    server_with_delay(responses, Duration::ZERO)
}

fn server_with_delay(responses: Vec<Vec<u8>>, delay: Duration) -> Server {
    let cert = rcgen::generate_simple_self_signed(vec!["localhost".into()]).unwrap();
    let tls = rustls::ServerConfig::builder_with_provider(Arc::new(
        rustls::crypto::ring::default_provider(),
    ))
    .with_safe_default_protocol_versions()
    .unwrap()
    .with_no_client_auth()
    .with_single_cert(
        vec![cert.cert.der().clone()],
        rustls::pki_types::PrivatePkcs8KeyDer::from(cert.signing_key.serialize_der()).into(),
    )
    .unwrap();
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let port = listener.local_addr().unwrap().port();
    listener.set_nonblocking(true).unwrap();
    let client = Client::builder()
        .no_proxy()
        .redirect(Policy::none())
        .add_root_certificate(reqwest::Certificate::from_der(cert.cert.der()).unwrap())
        .build()
        .unwrap();
    let requests = Arc::new(Mutex::new(vec![]));
    let done = Arc::new(AtomicBool::new(false));
    let done_worker = done.clone();
    let seen = requests.clone();
    let worker = thread::spawn(move || {
        let tls = Arc::new(tls);
        let mut responses = responses.into_iter();
        while !done_worker.load(Ordering::Relaxed) {
            match listener.accept() {
                Ok((stream, _)) => {
                    // Windows inherits the listener's nonblocking mode.
                    stream.set_nonblocking(false).unwrap();
                    stream.set_nodelay(true).unwrap();
                    stream
                        .set_read_timeout(Some(Duration::from_secs(2)))
                        .unwrap();
                    stream
                        .set_write_timeout(Some(Duration::from_secs(2)))
                        .unwrap();
                    let connection = rustls::ServerConnection::new(tls.clone()).unwrap();
                    let mut stream = rustls::StreamOwned::new(connection, stream);
                    let mut bytes = vec![];
                    let mut byte = [0];
                    while bytes.len() < 8192 && !bytes.ends_with(b"\r\n\r\n") {
                        match stream.read(&mut byte) {
                            Ok(1) => bytes.push(byte[0]),
                            Err(error) => {
                                eprintln!("loopback TLS fixture read: {error:?}");
                                break;
                            }
                            _ => break,
                        }
                    }
                    if !bytes.is_empty() {
                        seen.lock()
                            .unwrap()
                            .push(String::from_utf8_lossy(&bytes).to_string());
                        let response = responses.next().unwrap_or_else(|| b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".to_vec());
                        if delay.is_zero() {
                            let _ = stream.write_all(&response);
                            let _ = stream.flush();
                        } else {
                            let split =
                                response.windows(4).position(|w| w == b"\r\n\r\n").unwrap() + 4;
                            let _ = stream.write_all(&response[..split]);
                            let _ = stream.flush();
                            for byte in &response[split..] {
                                thread::sleep(delay);
                                if stream
                                    .write_all(&[*byte])
                                    .and_then(|_| stream.flush())
                                    .is_err()
                                {
                                    break;
                                }
                            }
                        }
                    }
                }
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                    thread::sleep(Duration::from_millis(5))
                }
                Err(_) => break,
            }
        }
    });
    Server {
        url: format!("https://localhost:{port}/package.zip"),
        client: Transport {
            client,
            hosts: HashSet::from(["localhost".into()]),
            runtime: Arc::new(
                tokio::runtime::Builder::new_current_thread()
                    .enable_all()
                    .build()
                    .unwrap(),
            ),
            idle_timeout: Duration::from_secs(60),
            test_port: Some(port),
            range_bytes: 2,
        },
        requests,
        done,
        worker: Some(worker),
    }
}

fn signed_reference(url: &str) -> (Reference, PublicKey) {
    let key =
        verify::decode_key("RWQf6LRCGA9i53mlYecO4IzT51TGPpvWucNSCh1CBM0QTaLn73Y7GFO3").unwrap();
    let signature = base64::engine::general_purpose::STANDARD.encode(concat!(
        "untrusted comment: signature from minisign secret key\n",
        "RUQf6LRCGA9i559r3g7V1qNyJDApGip8MfqcadIgT9CuhV3EMhHoN1mGTkUidF/z7SrlQgXdy8ofjb7bNJJylDOocrCo8KLzZwo=\n",
        "trusted comment: timestamp:1556193335\tfile:test\n",
        "y/rUw2y8/hOUYjZU71eHp/Wo1KZ40fGy2VJEDl34XMJM+TX48Ss/17u3IvIfbVR1FkZZSNCisQbuQY+bHwhEBg==\n"
    ));
    (
        Reference {
            url: url.into(),
            sha256: verify::sha256(b"test"),
            size_bytes: 4,
            signature,
        },
        key,
    )
}

#[test]
fn loopback_tls_fixture_has_a_valid_certificate() {
    let server = server(vec![
        b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\nConnection: close\r\n\r\ntest".to_vec(),
    ]);
    let response = server.client.runtime.block_on(async {
        server
            .client
            .client
            .get(&server.url)
            .send()
            .await
            .expect("TLS fixture handshake")
            .bytes()
            .await
            .unwrap()
    });
    assert_eq!(response.as_ref(), b"test");
}

fn partial(start: u64, body: &[u8], etag: &str) -> Vec<u8> {
    let mut response = format!("HTTP/1.1 206 Partial Content\r\nContent-Length: 2\r\nContent-Range: bytes {start}-{}/4\r\nETag: {etag}\r\nConnection: close\r\n\r\n", start+1).into_bytes();
    response.extend_from_slice(body);
    response
}

#[test]
fn https_ranges_resume_after_cancel_with_a_verified_prefix() {
    let server = server(vec![
        partial(0, b"te", "\"v1\""),
        partial(2, b"st", "\"v1\""),
    ]);
    let (reference, key) = signed_reference(&server.url);
    let temp = tempfile::tempdir().unwrap();
    let mut count = 0;
    let error = server
        .client
        .package(&reference, temp.path(), &key, |bytes| {
            if count >= 2 {
                return Err("CANCELLED".into());
            }
            count += bytes;
            Ok(())
        })
        .unwrap_err();
    assert_eq!(error, "CANCELLED");
    let target = server
        .client
        .package(&reference, temp.path(), &key, |_| Ok(()))
        .unwrap();
    assert_eq!(std::fs::read(target).unwrap(), b"test");
    let requests = server.requests.lock().unwrap();
    assert_eq!(requests.len(), 2);
    assert!(requests[1].to_lowercase().contains("range: bytes=2-3"));
    assert!(requests[1].to_lowercase().contains("if-range: \"v1\""));
}

#[test]
fn https_partial_disconnect_retries_without_appending_failed_suffix() {
    let server = server(vec![
        partial(0, b"t", "\"v1\""),
        partial(0, b"te", "\"v1\""),
        partial(2, b"st", "\"v1\""),
    ]);
    let (reference, key) = signed_reference(&server.url);
    let temp = tempfile::tempdir().unwrap();
    let mut received = 0;
    let result = server
        .client
        .package(&reference, temp.path(), &key, |bytes| {
            received += bytes;
            Ok(())
        })
        .unwrap();
    assert_eq!(std::fs::read(result).unwrap(), b"test");
    assert_eq!(received, 5);
    assert_eq!(server.requests.lock().unwrap().len(), 3);
}

#[test]
fn https_ignored_range_restarts_only_this_package() {
    let server = server(vec![
        partial(0, b"te", "\"v1\""),
        b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\nConnection: close\r\n\r\ntest".to_vec(),
    ]);
    let (reference, key) = signed_reference(&server.url);
    let temp = tempfile::tempdir().unwrap();
    let mut received = 0;
    let result = server
        .client
        .package(&reference, temp.path(), &key, |bytes| {
            received += bytes;
            Ok(())
        })
        .unwrap();
    assert_eq!(std::fs::read(result).unwrap(), b"test");
    assert_eq!(received, 6);
}

#[test]
fn https_changed_etag_and_untrusted_redirect_fail_closed() {
    for responses in [
        vec![partial(0,b"te","\"v1\""),partial(2,b"st","\"v2\"")],
        vec![b"HTTP/1.1 302 Found\r\nLocation: http://localhost/unsafe\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".to_vec()],
    ] {
        let server = server(responses); let (reference,key) = signed_reference(&server.url);
        let temp = tempfile::tempdir().unwrap();
        let error = server.client.package(&reference,temp.path(),&key,|_|Ok(())).unwrap_err();
        assert!(["INVALID_RANGE","UNTRUSTED_URL"].contains(&error.as_str()));
        assert!(!temp.path().join(format!("{}.zip",reference.sha256)).exists());
    }
}

#[test]
fn corrupt_partial_is_retained_then_downloaded_from_zero() {
    let server = server(vec![
        partial(0, b"te", "\"v1\""),
        partial(2, b"st", "\"v1\""),
    ]);
    let (reference, key) = signed_reference(&server.url);
    let temp = tempfile::tempdir().unwrap();
    std::fs::write(
        temp.path().join(format!("{}.part", reference.sha256)),
        b"bad-prefix",
    )
    .unwrap();
    std::fs::write(
        temp.path().join(format!("{}.part.json", reference.sha256)),
        b"{broken-json",
    )
    .unwrap();
    let target = server
        .client
        .package(&reference, temp.path(), &key, |_| Ok(()))
        .unwrap();
    assert_eq!(std::fs::read(target).unwrap(), b"test");
    let retained = std::fs::read_dir(temp.path())
        .unwrap()
        .flatten()
        .find(|entry| {
            entry
                .file_name()
                .to_string_lossy()
                .starts_with("quarantine-")
        })
        .unwrap()
        .path();
    assert_eq!(
        std::fs::read(retained.join(format!("{}.part", reference.sha256))).unwrap(),
        b"bad-prefix"
    );
    assert!(server.requests.lock().unwrap()[0]
        .to_lowercase()
        .contains("range: bytes=0-1"));
}

#[test]
fn invalid_signed_cache_is_quarantined_without_network_retry() {
    let server = server(vec![]);
    let (reference, key) = signed_reference(&server.url);
    let temp = tempfile::tempdir().unwrap();
    let target = temp.path().join(format!("{}.zip", reference.sha256));
    std::fs::write(&target, b"evil").unwrap();
    assert_eq!(
        server
            .client
            .package(&reference, temp.path(), &key, |_| Ok(()))
            .unwrap_err(),
        "HASH_MISMATCH"
    );
    assert!(!target.exists());
    assert!(server.requests.lock().unwrap().is_empty());
}

#[test]
fn completed_partial_after_power_loss_is_verified_without_retransmitting() {
    let server = server(vec![]);
    let (reference, key) = signed_reference(&server.url);
    let temp = tempfile::tempdir().unwrap();
    std::fs::write(
        temp.path().join(format!("{}.part", reference.sha256)),
        b"test",
    )
    .unwrap();
    let result = server
        .client
        .package(&reference, temp.path(), &key, |_| {
            panic!("cache hit must not download")
        })
        .unwrap();
    assert_eq!(std::fs::read(result).unwrap(), b"test");
    assert!(server.requests.lock().unwrap().is_empty());
}

#[test]
fn ignored_range_can_stream_longer_than_idle_timeout_while_making_progress() {
    let mut server = server_with_delay(
        vec![b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\nConnection: close\r\n\r\ntest".to_vec()],
        Duration::from_millis(200),
    );
    server.client.idle_timeout = Duration::from_millis(500);
    let (reference, key) = signed_reference(&server.url);
    let temp = tempfile::tempdir().unwrap();
    let started = std::time::Instant::now();
    let result = server
        .client
        .package(&reference, temp.path(), &key, |_| Ok(()))
        .unwrap();
    assert!(started.elapsed() > server.client.idle_timeout);
    assert_eq!(std::fs::read(result).unwrap(), b"test");
}

#[test]
fn stalled_body_and_total_check_deadline_are_independently_bounded() {
    for (delay, idle, total) in [(300, 100, 2000), (100, 500, 250)] {
        let mut server = server_with_delay(
            vec![b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\nConnection: close\r\n\r\ntest".to_vec()],
            Duration::from_millis(delay),
        );
        server.client.idle_timeout = Duration::from_millis(idle);
        let started = std::time::Instant::now();
        assert!(server
            .client
            .small_before(&server.url, 4, started + Duration::from_millis(total))
            .is_err());
        assert!(started.elapsed() < Duration::from_secs(1));
    }
}
