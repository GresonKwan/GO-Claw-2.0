use super::Result;
use std::path::{Path, PathBuf};

pub const MUTABLE: &[&str] = &[
    "data",
    "secrets",
    "logs",
    "cache",
    "backups",
    "updates",
    "go-claw-config",
    "portable.json",
    "runtime",
];

pub fn relative(value: &str) -> Result<()> {
    if value.is_empty()
        || value.len() > 1024
        || value
            .chars()
            .any(|c| c.is_control() || "\\:*?\"<>|".contains(c))
    {
        return Err("UNSAFE_PATH".into());
    }
    for part in value.split('/') {
        if part.is_empty() || part == "." || part == ".." || part.ends_with(['.', ' ']) {
            return Err("UNSAFE_PATH".into());
        }
        let lower = part.to_lowercase();
        let base = lower.split('.').next().unwrap_or("").trim_end();
        if ["con", "prn", "aux", "nul", "conin$", "conout$"].contains(&base)
            || ["com", "lpt"].iter().any(|prefix| {
                base.strip_prefix(prefix).is_some_and(|n| {
                    ["1", "2", "3", "4", "5", "6", "7", "8", "9", "¹", "²", "³"].contains(&n)
                })
            })
        {
            return Err("UNSAFE_PATH".into());
        }
        if [
            "credentials.json",
            "provision.json",
            "instance.id",
            ".go-claw-billing.json",
            ".go-claw-credentials-imported.json",
            ".env",
            "id_rsa",
            "id_ed25519",
        ]
        .contains(&lower.as_str())
            || lower.starts_with(".env.")
            || lower.ends_with(".private.key")
        {
            return Err("FORBIDDEN_MATERIAL".into());
        }
    }
    Ok(())
}

pub fn no_link(path: &Path) -> Result<std::fs::Metadata> {
    let metadata = std::fs::symlink_metadata(path).map_err(|_| "PATH_UNAVAILABLE")?;
    if metadata.file_type().is_symlink() {
        return Err("REPARSE_POINT".into());
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        if metadata.file_attributes() & 0x400 != 0 {
            return Err("REPARSE_POINT".into());
        }
    }
    Ok(metadata)
}

pub fn absolute_directory(path: &Path) -> Result<()> {
    if !path.is_absolute()
        || path.components().any(|c| {
            matches!(
                c,
                std::path::Component::ParentDir | std::path::Component::CurDir
            )
        })
    {
        return Err("UNSAFE_PATH".into());
    }
    // Checking only the final directory would permit an ancestor junction.
    for ancestor in path.ancestors() {
        if !no_link(ancestor)?.is_dir() {
            return Err("UNSAFE_PATH".into());
        }
    }
    Ok(())
}

/// Validate each existing ancestor, and reject a link even when its target is
/// inside the root. Call again immediately before creation/opening a member.
pub fn join(root: &Path, name: &str) -> Result<PathBuf> {
    relative(name)?;
    no_link(root)?;
    let mut path = root.to_path_buf();
    for part in name.split('/') {
        path.push(part);
        match std::fs::symlink_metadata(&path) {
            Ok(_) => {
                no_link(&path)?;
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
            Err(_) => return Err("PATH_UNAVAILABLE".into()),
        }
    }
    Ok(path)
}

pub fn assignment(name: &str, component: &str, mount: &str) -> Result<()> {
    relative(name)?;
    let parts: Vec<_> = name.split('/').collect();
    if MUTABLE.contains(&parts[0].to_lowercase().as_str()) {
        return Err("MUTABLE_PATH".into());
    }
    let valid = match component {
        "desktop-shell" => mount == "bootstrap" && name == "GO-CLAW-Portable.exe",
        "product-docs" => {
            mount == "root-docs" && ["LICENSE", "README-PORTABLE.zh-CN.txt"].contains(&name)
        }
        "python-runtime" | "node-runtime" => {
            mount == "slot" && parts.len() > 2 && parts[0] == "binaries" && parts[1] == component
        }
        "backend-core" | "backend-heavy-runtime" | "bundled-plugins" => {
            mount == "slot"
                && parts.len() > 1
                && parts[0] == "binaries"
                && !["python-runtime", "node-runtime"].contains(&parts[1])
        }
        _ => false,
    };
    if !valid {
        return Err("INVALID_COMPONENT_MOUNT".into());
    }
    Ok(())
}
