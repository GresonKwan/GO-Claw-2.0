//! Bounded HTTPS transport. Trust is anchored in the shipped key and host list,
//! never in a host supplied by a downloaded index or a browser request.
use super::{manifest::Reference, paths, state, verify, Result};
use minisign_verify::PublicKey;
use reqwest::{header, redirect::Policy, Client, Response, StatusCode, Url};
use sha2::{Digest, Sha256};
use std::{
    collections::HashSet,
    fs::OpenOptions,
    io::{Read, Write},
    path::Path,
    sync::Arc,
    time::Duration,
};

pub struct Transport {
    client: Client,
    hosts: HashSet<String>,
    runtime: Arc<tokio::runtime::Runtime>,
    idle_timeout: Duration,
    #[cfg(test)]
    test_port: Option<u16>,
    #[cfg(test)]
    range_bytes: u64,
}

/// Bridge the streaming HTTP body into the bounded file-copy routines. Each
/// chunk gets an idle deadline, independent of the entire transfer budget.
struct BodyResponse {
    inner: Response,
    runtime: Arc<tokio::runtime::Runtime>,
    deadline: std::time::Instant,
    idle_timeout: Duration,
    buffered: std::io::Cursor<Vec<u8>>,
}
impl BodyResponse {
    fn status(&self) -> StatusCode {
        self.inner.status()
    }
    fn headers(&self) -> &header::HeaderMap {
        self.inner.headers()
    }
    fn content_length(&self) -> Option<u64> {
        self.inner.content_length()
    }
}
impl Read for BodyResponse {
    fn read(&mut self, output: &mut [u8]) -> std::io::Result<usize> {
        if output.is_empty() {
            return Ok(0);
        }
        loop {
            let size = self.buffered.read(output)?;
            if size != 0 {
                return Ok(size);
            }
            let timeout = self
                .deadline
                .saturating_duration_since(std::time::Instant::now())
                .min(self.idle_timeout);
            if timeout.is_zero() {
                return Err(std::io::ErrorKind::TimedOut.into());
            }
            let chunk = self
                .runtime
                .block_on(async { tokio::time::timeout(timeout, self.inner.chunk()).await })
                .map_err(|_| std::io::Error::from(std::io::ErrorKind::TimedOut))?
                .map_err(|_| std::io::Error::from(std::io::ErrorKind::ConnectionReset))?;
            match chunk {
                Some(bytes) => self.buffered = std::io::Cursor::new(bytes.to_vec()),
                None => return Ok(0),
            }
        }
    }
}

pub fn trusted_url(value: &str, hosts: &HashSet<String>) -> Result<Url> {
    if value.chars().any(|c| c <= ' ' || c == '\\') {
        return Err("UNTRUSTED_URL".into());
    }
    let url = Url::parse(value).map_err(|_| "UNTRUSTED_URL")?;
    if url.scheme() != "https"
        || !url.username().is_empty()
        || url.password().is_some()
        || url.fragment().is_some()
        || ![None, Some(443), Some(8443)].contains(&url.port())
        || !url.host_str().is_some_and(|host| hosts.contains(host))
    {
        return Err("UNTRUSTED_URL".into());
    }
    Ok(url)
}

impl Transport {
    pub fn new(hosts: HashSet<String>) -> Result<Self> {
        let client = Client::builder()
            .redirect(Policy::none())
            .connect_timeout(Duration::from_secs(15))
            .build()
            .map_err(|_| "NETWORK_FAILED")?;
        let runtime = Arc::new(
            tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
                .map_err(|_| "NETWORK_FAILED")?,
        );
        Ok(Self {
            client,
            hosts,
            runtime,
            idle_timeout: Duration::from_secs(60),
            #[cfg(test)]
            test_port: None,
            #[cfg(test)]
            range_bytes: 4 * 1024 * 1024,
        })
    }

    fn url(&self, value: &str) -> Result<Url> {
        #[cfg(test)]
        if let Some(port) = self.test_port {
            let original = Url::parse(value).map_err(|_| "UNTRUSTED_URL")?;
            if original.host_str() == Some("localhost") && original.port() == Some(port) {
                let mut checked = original.clone();
                checked.set_port(Some(443)).map_err(|_| "UNTRUSTED_URL")?;
                trusted_url(checked.as_str(), &self.hosts)?;
                return Ok(original);
            }
        }
        trusted_url(value, &self.hosts)
    }

    fn response(
        &self,
        value: &str,
        range: Option<(u64, u64)>,
        etag: Option<&str>,
        timeout: Duration,
    ) -> Result<BodyResponse> {
        let mut url = self.url(value)?;
        let started = std::time::Instant::now();
        for redirects in 0..=3 {
            let remaining = timeout
                .checked_sub(started.elapsed())
                .ok_or("NETWORK_FAILED")?;
            let mut request = self
                .client
                .get(url.clone())
                .timeout(remaining)
                .header(header::ACCEPT_ENCODING, "identity");
            if let Some((start, end)) = range {
                request = request.header(header::RANGE, format!("bytes={start}-{end}"));
            }
            if let Some(etag) = etag {
                request = request.header(header::IF_RANGE, etag);
            }
            let response = self
                .runtime
                .block_on(async {
                    tokio::time::timeout(remaining.min(self.idle_timeout), request.send()).await
                })
                .map_err(|_| "NETWORK_FAILED")?
                .map_err(|_| "NETWORK_FAILED")?;
            if response.status().is_redirection() {
                if redirects == 3 {
                    return Err("REDIRECT_LIMIT".into());
                }
                let location = response
                    .headers()
                    .get(header::LOCATION)
                    .and_then(|v| v.to_str().ok())
                    .ok_or("UNTRUSTED_URL")?;
                let next = url.join(location).map_err(|_| "UNTRUSTED_URL")?;
                url = self.url(next.as_str())?;
                continue;
            }
            if response.status().is_server_error()
                || response.status() == StatusCode::TOO_MANY_REQUESTS
            {
                return Err("NETWORK_FAILED".into());
            }
            if !response.status().is_success() {
                return Err("DOWNLOAD_REJECTED".into());
            }
            if response
                .headers()
                .get(header::CONTENT_ENCODING)
                .is_some_and(|v| v != "identity")
            {
                return Err("INVALID_ENCODING".into());
            }
            return Ok(BodyResponse {
                inner: response,
                runtime: self.runtime.clone(),
                deadline: started + timeout,
                idle_timeout: self.idle_timeout,
                buffered: std::io::Cursor::new(vec![]),
            });
        }
        Err("REDIRECT_LIMIT".into())
    }

    pub fn small(&self, url: &str, limit: usize) -> Result<Vec<u8>> {
        self.small_before(
            url,
            limit,
            std::time::Instant::now() + Duration::from_secs(15),
        )
    }

    pub fn small_before(
        &self,
        url: &str,
        limit: usize,
        deadline: std::time::Instant,
    ) -> Result<Vec<u8>> {
        let remaining = deadline
            .checked_duration_since(std::time::Instant::now())
            .ok_or("NETWORK_FAILED")?;
        let response = self.response(url, None, None, remaining)?;
        if response.status() != StatusCode::OK
            || response.content_length().is_some_and(|n| n > limit as u64)
        {
            return Err("INVALID_SIZE".into());
        }
        let mut bytes = Vec::new();
        response
            .take(limit as u64 + 1)
            .read_to_end(&mut bytes)
            .map_err(|_| "NETWORK_FAILED")?;
        if bytes.len() > limit {
            return Err("INVALID_SIZE".into());
        }
        Ok(bytes)
    }

    /// Bounded 4 MiB ranges permit long packages without unbounded request time.
    /// Every persisted partial prefix has a local SHA-256 and strong ETag;
    /// full-package signature/hash is still mandatory before promotion.
    pub fn package(
        &self,
        reference: &Reference,
        directory: &Path,
        key: &PublicKey,
        mut progress: impl FnMut(u64) -> Result<()>,
    ) -> Result<std::path::PathBuf> {
        self.url(&reference.url)?;
        if !super::manifest::hash_valid(&reference.sha256) || reference.size_bytes == 0 {
            return Err("INVALID_REFERENCE".into());
        }
        let target = paths::join(directory, &format!("{}.zip", reference.sha256))?;
        if target.exists() {
            if let Err(error) = verify::signed_file(
                &target,
                &reference.signature,
                key,
                &reference.sha256,
                reference.size_bytes,
            ) {
                quarantine(directory, &[&target])?;
                return Err(error);
            }
            return Ok(target);
        }
        let part = paths::join(directory, &format!("{}.part", reference.sha256))?;
        let meta = paths::join(directory, &format!("{}.part.json", reference.sha256))?;
        if part.exists() && paths::no_link(&part)?.len() == reference.size_bytes {
            // Power loss after the last flush but before rename need not
            // retransmit a complete package. The full signature still gates it.
            match verify::signed_file(
                &part,
                &reference.signature,
                key,
                &reference.sha256,
                reference.size_bytes,
            ) {
                Ok(()) => {
                    state::replace(&part, &target)?;
                    return Ok(target);
                }
                Err(error) => {
                    quarantine(directory, &[&part, &meta])?;
                    return Err(error);
                }
            }
        }
        let mut offset = 0u64;
        let mut etag: Option<String> = None;
        let mut prefix_hash = Sha256::new();
        if part.exists() && meta.exists() {
            let previous = state::read_limited(&meta, 8192)
                .ok()
                .and_then(|bytes| serde_json::from_slice::<Partial>(&bytes).ok());
            let (hash, length) = verify::hash_file(&part)?;
            if let Some(previous) = previous.filter(|previous| {
                previous.target == reference.sha256
                    && previous.size == length
                    && previous.prefix_sha256 == hash
                    && length < reference.size_bytes
                    && strong_etag(&previous.etag)
            }) {
                offset = length;
                etag = Some(previous.etag);
                let mut prefix = std::fs::File::open(&part).map_err(|_| "FILE_READ_FAILED")?;
                let mut buffer = [0u8; 65536];
                loop {
                    let count = prefix.read(&mut buffer).map_err(|_| "FILE_READ_FAILED")?;
                    if count == 0 {
                        break;
                    }
                    prefix_hash.update(&buffer[..count]);
                }
            }
        }
        if offset == 0 && (part.exists() || meta.exists()) {
            quarantine(directory, &[&part, &meta])?;
        }
        let mut file = OpenOptions::new()
            .create(true)
            .write(true)
            .truncate(offset == 0)
            .open(&part)
            .map_err(|_| "DOWNLOAD_WRITE_FAILED")?;
        use std::io::Seek;
        file.seek(std::io::SeekFrom::Start(offset))
            .map_err(|_| "DOWNLOAD_WRITE_FAILED")?;
        let mut attempts = 0;
        let started = std::time::Instant::now();
        let budget =
            Duration::from_secs((reference.size_bytes / (64 * 1024) + 120).clamp(120, 4 * 60 * 60));
        while offset < reference.size_bytes {
            progress(0)?;
            if started.elapsed() > budget {
                return Err("DOWNLOAD_TIMEOUT".into());
            }
            #[cfg(test)]
            let range_bytes = self.range_bytes;
            #[cfg(not(test))]
            let range_bytes = 4 * 1024 * 1024;
            let end = (offset + range_bytes - 1).min(reference.size_bytes - 1);
            let result = self.response(
                &reference.url,
                Some((offset, end)),
                etag.as_deref(),
                budget.saturating_sub(started.elapsed()),
            );
            let mut response = match result {
                Err(e) if e == "NETWORK_FAILED" && attempts < 3 => {
                    attempts += 1;
                    std::thread::sleep(Duration::from_secs(1 << (attempts - 1)));
                    continue;
                }
                other => other?,
            };
            let response_etag = response
                .headers()
                .get(header::ETAG)
                .and_then(|v| v.to_str().ok())
                .filter(|v| strong_etag(v))
                .map(str::to_owned);
            let expected = if response.status() == StatusCode::PARTIAL_CONTENT {
                let value = response
                    .headers()
                    .get(header::CONTENT_RANGE)
                    .and_then(|v| v.to_str().ok())
                    .ok_or("INVALID_RANGE")?;
                if value != format!("bytes {offset}-{end}/{}", reference.size_bytes)
                    || (offset > 0 && response_etag != etag)
                {
                    return Err("INVALID_RANGE".into());
                }
                end - offset + 1
            } else if response.status() == StatusCode::OK {
                // Origin ignored Range/If-Range: restart this component only.
                offset = 0;
                file.set_len(0).map_err(|_| "DOWNLOAD_WRITE_FAILED")?;
                prefix_hash = Sha256::new();
                file.seek(std::io::SeekFrom::Start(0))
                    .map_err(|_| "DOWNLOAD_WRITE_FAILED")?;
                reference.size_bytes
            } else {
                return Err("INVALID_RANGE".into());
            };
            if response.content_length().is_some_and(|n| n != expected) {
                return Err("INVALID_SIZE".into());
            }
            let checkpoint_hash = prefix_hash.clone();
            if let Err(error) = copy_body(
                &mut response,
                &mut file,
                &mut prefix_hash,
                expected,
                &mut progress,
            ) {
                // Only complete ranges are checkpoints. A reset/short body
                // must not append its retry after an uncommitted suffix.
                restore_prefix(&mut file, offset)?;
                prefix_hash = checkpoint_hash;
                if error == "NETWORK_FAILED" && attempts < 3 {
                    attempts += 1;
                    std::thread::sleep(Duration::from_secs(1 << (attempts - 1)));
                    continue;
                }
                return Err(error);
            }
            offset += expected;
            attempts = 0;
            etag = response_etag;
            file.sync_all().map_err(|_| "DOWNLOAD_FLUSH_FAILED")?;
            if let Some(ref tag) = etag {
                // Incremental digest avoids rereading the growing USB file for
                // every range (quadratic I/O on large runtime components).
                let partial = Partial {
                    target: reference.sha256.clone(),
                    size: offset,
                    prefix_sha256: format!("{:x}", prefix_hash.clone().finalize()),
                    etag: tag.clone(),
                };
                state::atomic_write(
                    &meta,
                    &serde_json::to_vec(&partial).map_err(|_| "INVALID_PARTIAL")?,
                )?;
            }
        }
        drop(file);
        if let Err(error) = verify::signed_file(
            &part,
            &reference.signature,
            key,
            &reference.sha256,
            reference.size_bytes,
        ) {
            quarantine(directory, &[&part, &meta])?;
            return Err(error);
        }
        state::replace(&part, &target)?;
        Ok(target)
    }
}

fn quarantine(directory: &Path, files: &[&Path]) -> Result<()> {
    let retained = paths::join(directory, &format!("quarantine-{}", uuid::Uuid::new_v4()))?;
    std::fs::create_dir(&retained).map_err(|_| "CACHE_QUARANTINE_FAILED")?;
    for file in files {
        if file.exists() {
            if file.parent() != Some(directory) || !paths::no_link(file)?.is_file() {
                return Err("UNSAFE_PATH".into());
            }
            let name = file
                .file_name()
                .and_then(|n| n.to_str())
                .ok_or("UNSAFE_PATH")?;
            state::replace(file, &paths::join(&retained, name)?)?;
        }
    }
    Ok(())
}

fn restore_prefix(file: &mut std::fs::File, offset: u64) -> Result<()> {
    use std::io::{Seek, SeekFrom};
    file.set_len(offset)
        .and_then(|_| file.seek(SeekFrom::Start(offset)))
        .and_then(|_| file.sync_all())
        .map_err(|_| "DOWNLOAD_WRITE_FAILED".into())
}

fn copy_body(
    response: &mut impl Read,
    file: &mut impl Write,
    prefix_hash: &mut Sha256,
    expected: u64,
    progress: &mut impl FnMut(u64) -> Result<()>,
) -> Result<()> {
    let mut received = 0u64;
    let mut buffer = [0u8; 65536];
    loop {
        let count = response.read(&mut buffer).map_err(|_| "NETWORK_FAILED")?;
        if count == 0 {
            break;
        }
        received = received.checked_add(count as u64).ok_or("INVALID_SIZE")?;
        if received > expected {
            return Err("INVALID_SIZE".into());
        }
        file.write_all(&buffer[..count])
            .map_err(|_| "DOWNLOAD_WRITE_FAILED")?;
        prefix_hash.update(&buffer[..count]);
        progress(count as u64)?;
    }
    if received != expected {
        return Err("NETWORK_FAILED".into());
    }
    Ok(())
}

fn strong_etag(value: &str) -> bool {
    value.len() <= 1024
        && value.starts_with('"')
        && value.ends_with('"')
        && !value.chars().any(char::is_control)
}

#[derive(serde::Serialize, serde::Deserialize)]
struct Partial {
    target: String,
    size: u64,
    prefix_sha256: String,
    etag: String,
}

#[cfg(test)]
#[path = "download_https_tests.rs"]
mod https_tests;

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Cursor, Seek, SeekFrom};

    #[test]
    fn interrupted_body_restores_checkpoint_before_retry() {
        struct BrokenBody(bool);
        impl Read for BrokenBody {
            fn read(&mut self, buf: &mut [u8]) -> std::io::Result<usize> {
                if self.0 {
                    return Err(std::io::ErrorKind::ConnectionReset.into());
                }
                self.0 = true;
                buf[..2].copy_from_slice(b"ba");
                Ok(2)
            }
        }
        let mut file = tempfile::tempfile().unwrap();
        file.write_all(b"prefix").unwrap();
        let mut hash = Sha256::new();
        hash.update(b"prefix");
        let checkpoint = hash.clone();
        let mut transferred = 0;
        let mut progress = |n| {
            transferred += n;
            Ok(())
        };
        assert_eq!(
            copy_body(
                &mut BrokenBody(false),
                &mut file,
                &mut hash,
                4,
                &mut progress
            )
            .unwrap_err(),
            "NETWORK_FAILED"
        );
        restore_prefix(&mut file, 6).unwrap();
        hash = checkpoint;
        copy_body(
            &mut Cursor::new(b"good"),
            &mut file,
            &mut hash,
            4,
            &mut progress,
        )
        .unwrap();
        assert_eq!(transferred, 6); // Actual network bytes include the failed suffix.
        file.seek(SeekFrom::Start(0)).unwrap();
        let mut bytes = Vec::new();
        file.read_to_end(&mut bytes).unwrap();
        assert_eq!(bytes, b"prefixgood");
        assert_eq!(format!("{:x}", hash.finalize()), verify::sha256(&bytes));
    }

    #[test]
    fn short_body_is_retryable_but_oversize_and_cancel_are_not() {
        for (body, expected, error) in [
            (b"x".as_slice(), 2, "NETWORK_FAILED"),
            (b"xy".as_slice(), 1, "INVALID_SIZE"),
        ] {
            assert_eq!(
                copy_body(
                    &mut Cursor::new(body),
                    &mut Vec::new(),
                    &mut Sha256::new(),
                    expected,
                    &mut |_| Ok(())
                )
                .unwrap_err(),
                error
            );
        }
        assert_eq!(
            copy_body(
                &mut Cursor::new(b"ok"),
                &mut Vec::new(),
                &mut Sha256::new(),
                2,
                &mut |_| Err("CANCELLED".into())
            )
            .unwrap_err(),
            "CANCELLED"
        );
        struct FullDisk;
        impl Write for FullDisk {
            fn write(&mut self, _: &[u8]) -> std::io::Result<usize> {
                Err(std::io::ErrorKind::WriteZero.into())
            }
            fn flush(&mut self) -> std::io::Result<()> {
                Ok(())
            }
        }
        assert_eq!(
            copy_body(
                &mut Cursor::new(b"ok"),
                &mut FullDisk,
                &mut Sha256::new(),
                2,
                &mut |_| Ok(())
            )
            .unwrap_err(),
            "DOWNLOAD_WRITE_FAILED"
        );
    }
}
