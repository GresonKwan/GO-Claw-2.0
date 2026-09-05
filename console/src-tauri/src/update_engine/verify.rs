use super::{paths, Result};
use base64::Engine;
use minisign_verify::{PublicKey, Signature};
use sha2::{Digest, Sha256};
use std::{fs::File, io::Read, path::Path};

pub fn sha256(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

pub fn hash_file(path: &Path) -> Result<(String, u64)> {
    if !paths::no_link(path)?.is_file() {
        return Err("NOT_REGULAR_FILE".into());
    }
    let mut stream = File::open(path).map_err(|_| "FILE_READ_FAILED")?;
    let mut hash = Sha256::new();
    let mut length = 0;
    let mut buffer = [0u8; 65536];
    loop {
        let n = stream.read(&mut buffer).map_err(|_| "FILE_READ_FAILED")?;
        if n == 0 {
            break;
        }
        hash.update(&buffer[..n]);
        length += n as u64;
    }
    Ok((format!("{:x}", hash.finalize()), length))
}

pub fn public_key() -> Result<PublicKey> {
    let config: serde_json::Value = serde_json::from_str(include_str!("../../tauri.conf.json"))
        .map_err(|_| "INVALID_TRUST_ROOT")?;
    let encoded = config["plugins"]["updater"]["pubkey"]
        .as_str()
        .ok_or("INVALID_TRUST_ROOT")?;
    decode_key(encoded)
}

pub fn decode_key(encoded: &str) -> Result<PublicKey> {
    let bytes = base64::engine::general_purpose::STANDARD
        .decode(encoded.trim())
        .map_err(|_| "INVALID_TRUST_ROOT")?;
    if bytes.len() == 42 {
        return PublicKey::from_base64(encoded.trim()).map_err(|_| "INVALID_TRUST_ROOT".into());
    }
    let text = std::str::from_utf8(&bytes).map_err(|_| "INVALID_TRUST_ROOT")?;
    PublicKey::decode(text.trim()).map_err(|_| "INVALID_TRUST_ROOT".into())
}

fn signature(encoded: &str) -> Result<Signature> {
    if encoded.len() > 4096 {
        return Err("SIGNATURE_INVALID".into());
    }
    let bytes = base64::engine::general_purpose::STANDARD
        .decode(encoded.trim())
        .map_err(|_| "SIGNATURE_INVALID")?;
    let text = std::str::from_utf8(&bytes).map_err(|_| "SIGNATURE_INVALID")?;
    Signature::decode(text.trim()).map_err(|_| "SIGNATURE_INVALID".into())
}

pub fn signed_bytes(bytes: &[u8], encoded: &str, key: &PublicKey) -> Result<()> {
    let sig = signature(encoded)?;
    let mut verifier = key.verify_stream(&sig).map_err(|_| "SIGNATURE_INVALID")?;
    verifier.update(bytes);
    verifier.finalize().map_err(|_| "SIGNATURE_INVALID".into())
}

pub fn signed_file(
    path: &Path,
    encoded: &str,
    key: &PublicKey,
    expected: &str,
    size: u64,
) -> Result<()> {
    if !paths::no_link(path)?.is_file() {
        return Err("NOT_REGULAR_FILE".into());
    }
    let sig = signature(encoded)?;
    let mut verifier = key.verify_stream(&sig).map_err(|_| "SIGNATURE_INVALID")?;
    let mut file = File::open(path).map_err(|_| "FILE_READ_FAILED")?;
    let mut hash = Sha256::new();
    let mut length = 0u64;
    let mut buffer = [0u8; 65536];
    loop {
        let n = file.read(&mut buffer).map_err(|_| "FILE_READ_FAILED")?;
        if n == 0 {
            break;
        }
        length = length.checked_add(n as u64).ok_or("SIZE_MISMATCH")?;
        if length > size {
            return Err("SIZE_MISMATCH".into());
        }
        verifier.update(&buffer[..n]);
        hash.update(&buffer[..n]);
    }
    if length != size || format!("{:x}", hash.finalize()) != expected {
        return Err("HASH_MISMATCH".into());
    }
    verifier.finalize().map_err(|_| "SIGNATURE_INVALID".into())
}
