use super::{paths, verify, Result};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashMap, HashSet};

pub const COMPONENTS: &[&str] = &[
    "desktop-shell",
    "backend-core",
    "backend-heavy-runtime",
    "python-runtime",
    "node-runtime",
    "bundled-plugins",
    "product-docs",
];
pub const MAX_INDEX: usize = 500 * 1024;
pub const MAX_MANIFEST: usize = 32 * 1024 * 1024;
pub const MAX_FILES: usize = 200_000;
// Same fixed entrypoint contract as the Python release assembler. A valid
// signature proves origin, not that the build contains a runnable product.
pub const REQUIRED_PROGRAMS: &[(&str, &str, &str)] = &[
    ("GO-CLAW-Portable.exe", "desktop-shell", "bootstrap"),
    ("binaries/go-claw-update-engine.exe", "backend-core", "slot"),
    (
        "binaries/qwenpaw-backend/qwenpaw-backend.exe",
        "backend-core",
        "slot",
    ),
    (
        "binaries/python-runtime/python/python.exe",
        "python-runtime",
        "slot",
    ),
    ("binaries/node-runtime/node.exe", "node-runtime", "slot"),
    ("LICENSE", "product-docs", "root-docs"),
    ("README-PORTABLE.zh-CN.txt", "product-docs", "root-docs"),
    (
        "binaries/qwenpaw-backend/_internal/qwenpaw/bundled_plugins/qwen-image/plugin.json",
        "bundled-plugins",
        "slot",
    ),
    (
        "binaries/qwenpaw-backend/_internal/qwenpaw/bundled_plugins/wan27/plugin.json",
        "bundled-plugins",
        "slot",
    ),
];

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct FileRecord {
    pub relative_path: String,
    pub size_bytes: u64,
    pub sha256: String,
    pub component: String,
    pub mount: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Component {
    pub id: String,
    pub archive_url: String,
    pub archive_bytes: u64,
    pub unpacked_bytes: u64,
    pub sha256: String,
    pub signature: String,
    pub content_digest: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Reference {
    pub url: String,
    pub sha256: String,
    pub signature: String,
    pub size_bytes: u64,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ComponentDigest {
    pub id: String,
    pub content_digest: String,
    pub archive_bytes: u64,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Index {
    pub schema_version: u8,
    pub version: String,
    pub build_commit: String,
    pub platform: String,
    pub channel: String,
    pub min_updater_version: String,
    pub component_digests: Vec<ComponentDigest>,
    pub full_bytes: u64,
    pub release_manifest: Reference,
    pub legacy_bridge: Reference,
    #[serde(default)]
    pub notes: String,
    #[serde(default)]
    pub pub_date: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CatalogEntry {
    pub index_url: String,
    pub release: Index,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Catalog {
    pub schema_version: u8,
    pub releases: Vec<CatalogEntry>,
}

impl Catalog {
    pub fn validate(&self) -> Result<()> {
        if self.schema_version != 2 || self.releases.len() > 50 {
            return Err("INVALID_CATALOG".into());
        }
        let mut versions = HashSet::new();
        let hosts = HashSet::from([
            "goclaw.host".into(),
            "github.com".into(),
            "release-assets.githubusercontent.com".into(),
            "objects.githubusercontent.com".into(),
        ]);
        for entry in &self.releases {
            entry.release.validate()?;
            super::download::trusted_url(&entry.index_url, &hosts)?;
            if !versions.insert(&entry.release.version) {
                return Err("INVALID_CATALOG".into());
            }
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Manifest {
    pub schema_version: u8,
    pub version: String,
    pub build_commit: String,
    pub platform: String,
    pub channel: String,
    pub min_updater_version: String,
    pub files: Vec<FileRecord>,
    pub components: Vec<Component>,
    pub delete_files: Vec<String>,
    pub min_free_bytes: u64,
    pub readiness_version: u8,
    pub entrypoint_id: String,
}

pub fn hash_valid(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}

fn common(
    schema: u8,
    version: &str,
    commit: &str,
    platform: &str,
    channel: &str,
    minimum: &str,
) -> Result<()> {
    if schema != 2
        || semver::Version::parse(version).is_err()
        || commit.len() != 40
        || !commit
            .bytes()
            .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
        || platform != "windows-x86_64"
        || !["stable", "staging"].contains(&channel)
    {
        return Err("INVALID_MANIFEST".into());
    }
    let minimum = semver::Version::parse(minimum).map_err(|_| "INVALID_MANIFEST")?;
    if minimum > semver::Version::new(2, 1, 2) {
        return Err("UPDATER_TOO_OLD".into());
    }
    Ok(())
}

pub fn content_digest(files: &[&FileRecord]) -> Result<String> {
    let mut sorted = files.to_vec();
    sorted.sort_by(|a, b| a.relative_path.as_bytes().cmp(b.relative_path.as_bytes()));
    let rows: Vec<BTreeMap<&str, serde_json::Value>> = sorted
        .iter()
        .map(|f| {
            BTreeMap::from([
                ("relativePath", serde_json::json!(f.relative_path)),
                ("component", serde_json::json!(f.component)),
                ("mount", serde_json::json!(f.mount)),
                ("sizeBytes", serde_json::json!(f.size_bytes)),
                ("sha256", serde_json::json!(f.sha256)),
            ])
        })
        .collect();
    let mut bytes = serde_json::to_vec(&rows).map_err(|_| "INVALID_MANIFEST")?;
    bytes.push(b'\n');
    Ok(verify::sha256(&bytes))
}

impl Index {
    pub fn validate(&self) -> Result<()> {
        common(
            self.schema_version,
            &self.version,
            &self.build_commit,
            &self.platform,
            &self.channel,
            &self.min_updater_version,
        )?;
        if self.component_digests.is_empty() || self.component_digests.len() > 7 {
            return Err("INVALID_COMPONENTS".into());
        }
        let mut ids = HashSet::new();
        let mut full = 0u64;
        for c in &self.component_digests {
            if !COMPONENTS.contains(&c.id.as_str())
                || !ids.insert(&c.id)
                || !hash_valid(&c.content_digest)
            {
                return Err("INVALID_COMPONENTS".into());
            }
            full = full.checked_add(c.archive_bytes).ok_or("INVALID_SIZE")?;
        }
        if full != self.full_bytes || self.release_manifest.size_bytes > MAX_MANIFEST as u64 {
            return Err("INVALID_SIZE".into());
        }
        for reference in [&self.release_manifest, &self.legacy_bridge] {
            if !hash_valid(&reference.sha256)
                || reference.signature.is_empty()
                || reference.signature.len() > 4096
            {
                return Err("INVALID_REFERENCE".into());
            }
        }
        Ok(())
    }
}

impl Manifest {
    pub fn validate(&self) -> Result<()> {
        common(
            self.schema_version,
            &self.version,
            &self.build_commit,
            &self.platform,
            &self.channel,
            &self.min_updater_version,
        )?;
        if self.readiness_version != 1
            || self.entrypoint_id != "go-claw-portable-v1"
            || self.files.is_empty()
            || self.files.len() > MAX_FILES
        {
            return Err("INVALID_MANIFEST".into());
        }
        let mut seen = HashSet::new();
        let mut spellings = HashMap::new();
        let mut directories = HashSet::new();
        for f in &self.files {
            paths::assignment(&f.relative_path, &f.component, &f.mount)?;
            if !hash_valid(&f.sha256) || !seen.insert(f.relative_path.to_lowercase()) {
                return Err("DUPLICATE_OR_INVALID_FILE".into());
            }
            let parts: Vec<_> = f.relative_path.split('/').collect();
            for i in 1..=parts.len() {
                let path = parts[..i].join("/");
                let key = path.to_lowercase();
                if i < parts.len() {
                    directories.insert(key.clone());
                }
                if spellings
                    .insert(key, path.clone())
                    .is_some_and(|previous| previous != path)
                {
                    return Err("CASE_COLLISION".into());
                }
            }
        }
        if !seen.is_disjoint(&directories) {
            return Err("FILE_DIRECTORY_COLLISION".into());
        }
        let mut ids = HashSet::new();
        for c in &self.components {
            if !COMPONENTS.contains(&c.id.as_str())
                || !ids.insert(c.id.clone())
                || !hash_valid(&c.sha256)
                || !hash_valid(&c.content_digest)
                || c.signature.is_empty()
                || c.signature.len() > 4096
            {
                return Err("INVALID_COMPONENTS".into());
            }
            let files: Vec<_> = self.files.iter().filter(|f| f.component == c.id).collect();
            let size = files
                .iter()
                .try_fold(0u64, |n, f| n.checked_add(f.size_bytes))
                .ok_or("INVALID_SIZE")?;
            if files.is_empty()
                || size != c.unpacked_bytes
                || content_digest(&files)? != c.content_digest
            {
                return Err("CONTENT_DIGEST_MISMATCH".into());
            }
        }
        if ids != self.files.iter().map(|f| f.component.clone()).collect() {
            return Err("INCOMPLETE_OWNERSHIP".into());
        }
        for (path, component, mount) in REQUIRED_PROGRAMS {
            if !self
                .files
                .iter()
                .any(|f| f.relative_path == *path && f.component == *component && f.mount == *mount)
            {
                return Err("MISSING_REQUIRED_PROGRAM".into());
            }
        }
        let mut deletes = HashSet::new();
        for name in &self.delete_files {
            paths::relative(name)?;
            if !name.starts_with("binaries/")
                || !deletes.insert(name.to_lowercase())
                || seen.contains(&name.to_lowercase())
            {
                return Err("UNSAFE_DELETE".into());
            }
        }
        Ok(())
    }

    pub fn matches_index(&self, index: &Index) -> Result<()> {
        self.validate()?;
        index.validate()?;
        if self.version != index.version
            || self.build_commit != index.build_commit
            || self.platform != index.platform
            || self.channel != index.channel
            || self.components.len() != index.component_digests.len()
        {
            return Err("TARGET_CHANGED".into());
        }
        for c in &self.components {
            if !index.component_digests.iter().any(|d| {
                d.id == c.id
                    && d.content_digest == c.content_digest
                    && d.archive_bytes == c.archive_bytes
            }) {
                return Err("TARGET_CHANGED".into());
            }
        }
        Ok(())
    }
}
