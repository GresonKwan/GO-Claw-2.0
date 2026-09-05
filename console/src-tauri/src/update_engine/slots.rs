use super::{
    manifest::{hash_valid, MAX_MANIFEST},
    paths, state, verify, Result,
};
use serde::{Deserialize, Serialize};
use std::{
    collections::BTreeMap,
    path::{Path, PathBuf},
};

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ActiveSlot {
    pub schema_version: u8,
    pub active: String,
    pub last_known_good: String,
    pub generation: u64,
    pub active_version: String,
    pub active_manifest_sha256: String,
    pub last_known_good_manifest_sha256: String,
}

pub fn resolve(root: &Path) -> Result<(PathBuf, Option<ActiveSlot>)> {
    let pointer = paths::join(root, "runtime/active-slot.json")?;
    if !pointer.exists() {
        return Ok((root.to_path_buf(), None));
    }
    let slot: ActiveSlot = serde_json::from_slice(&state::read_limited(&pointer, 65536)?)
        .map_err(|_| "INVALID_SLOT_POINTER")?;
    if slot.schema_version != 1
        || !["A", "B"].contains(&slot.active.as_str())
        || !["A", "B"].contains(&slot.last_known_good.as_str())
        || slot.generation == 0
        || !hash_valid(&slot.active_manifest_sha256)
        || !hash_valid(&slot.last_known_good_manifest_sha256)
    {
        return Err("INVALID_SLOT_POINTER".into());
    }
    let program_root = paths::join(root, &format!("runtime/slots/{}", slot.active))?;
    let bytes = state::read_limited(
        &paths::join(&program_root, "release-manifest.json")?,
        MAX_MANIFEST,
    )?;
    if verify::sha256(&bytes) != slot.active_manifest_sha256 {
        return Err("SLOT_MANIFEST_MISMATCH".into());
    }
    let sig = state::read_limited(
        &paths::join(&program_root, "release-manifest.json.sig")?,
        4096,
    )?;
    verify::signed_bytes(
        &bytes,
        std::str::from_utf8(&sig)
            .map_err(|_| "SIGNATURE_INVALID")?
            .trim(),
        &verify::public_key()?,
    )?;
    // Verify the exact stored bytes before interpreting any manifest fields.
    let value: super::manifest::Manifest =
        serde_json::from_slice(&bytes).map_err(|_| "INVALID_MANIFEST")?;
    value.validate()?;
    if value.version != slot.active_version {
        return Err("SLOT_VERSION_MISMATCH".into());
    }
    Ok((program_root, Some(slot)))
}

/// Both normal shell launch and trusted engine health launch use this builder.
/// Never infer data location from the current working directory/program slot.
pub fn environment(root: &Path, program_root: &Path) -> BTreeMap<String, String> {
    let mut env = BTreeMap::new();
    for (name, relative) in [
        ("QWENPAW_WORKING_DIR", "data"),
        ("QWENPAW_SECRET_DIR", "secrets"),
        ("QWENPAW_BACKUP_DIR", "backups"),
        ("PIP_CACHE_DIR", "cache/pip"),
        ("UV_CACHE_DIR", "cache/uv"),
    ] {
        env.insert(
            name.into(),
            root.join(relative).to_string_lossy().into_owned(),
        );
    }
    env.insert("QWENPAW_PORTABLE".into(), "1".into());
    env.insert("QWENPAW_DISABLE_KEYRING".into(), "1".into());
    env.insert(
        "GO_CLAW_PROGRAM_ROOT".into(),
        program_root.to_string_lossy().into_owned(),
    );
    env.insert(
        "QWENPAW_DESKTOP_PY_RUNTIME".into(),
        program_root
            .join(if cfg!(windows) {
                "binaries/python-runtime/python/python.exe"
            } else {
                "binaries/python-runtime/python/bin/python3"
            })
            .to_string_lossy()
            .into_owned(),
    );
    env.insert(
        "QWENPAW_DESKTOP_NODE_RUNTIME".into(),
        program_root
            .join("binaries/node-runtime")
            .to_string_lossy()
            .into_owned(),
    );
    env
}
