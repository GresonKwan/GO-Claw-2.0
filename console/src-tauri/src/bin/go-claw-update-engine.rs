//! Standalone process: no Tauri runtime and no customer credentials.
#[path = "../update_engine/mod.rs"]
mod update_engine;

fn run() -> update_engine::Result<serde_json::Value> {
    use std::{collections::HashMap, path::Path};
    let mut args = std::env::args().skip(1);
    let action = args.next().ok_or("INVALID_COMMAND")?;
    let mut options = HashMap::new();
    while let Some(key) = args.next() {
        if ![
            "--root",
            "--index-url",
            "--target-version",
            "--target-manifest",
            "--source-version",
            "--transaction-id",
        ]
        .contains(&key.as_str())
        {
            return Err("INVALID_COMMAND".into());
        }
        let value = args.next().ok_or("INVALID_COMMAND")?;
        if options.insert(key, value).is_some() {
            return Err("INVALID_COMMAND".into());
        }
    }
    let get = |key: &str| {
        options
            .get(key)
            .map(String::as_str)
            .ok_or_else(|| "INVALID_COMMAND".to_string())
    };
    match action.as_str() {
        "catalog" => serde_json::to_value(update_engine::staging::catalog(
            &update_engine::staging::transport()?,
            get("--index-url")?,
        )?)
        .map_err(|_| "INVALID_CATALOG".into()),
        "reconcile" => serde_json::to_value(update_engine::staging::reconcile(Path::new(get(
            "--root",
        )?))?)
        .map_err(|_| "INVALID_TRANSACTION".into()),
        #[cfg(windows)]
        "bridge" => {
            let root = Path::new(get("--root")?);
            let source = update_engine::native::source_version(root)?;
            let transaction = update_engine::staging::stage(
                root,
                get("--index-url")?,
                get("--target-version")?,
                get("--target-manifest")?,
                &source,
            )?;
            serde_json::to_value(update_engine::bootstrap::install(
                root,
                &transaction.transaction_id,
                &transaction.target_manifest_sha256,
                &mut update_engine::native::WindowsRuntime::default(),
            )?)
            .map_err(|_| "INVALID_TRANSACTION".into())
        }
        #[cfg(windows)]
        "source-version" => Ok(
            serde_json::json!({"version": update_engine::native::source_version(Path::new(get("--root")?))?}),
        ),
        #[cfg(windows)]
        "install" => serde_json::to_value(update_engine::bootstrap::install(
            Path::new(get("--root")?),
            get("--transaction-id")?,
            get("--target-manifest")?,
            &mut update_engine::native::WindowsRuntime::default(),
        )?)
        .map_err(|_| "INVALID_TRANSACTION".into()),
        #[cfg(windows)]
        "recover" => serde_json::to_value(update_engine::bootstrap::recover(
            Path::new(get("--root")?),
            &mut update_engine::native::WindowsRuntime::default(),
        )?)
        .map_err(|_| "INVALID_TRANSACTION".into()),
        "discover" => serde_json::to_value(update_engine::staging::discover(
            &update_engine::staging::transport()?,
            get("--index-url")?,
        )?)
        .map_err(|_| "INVALID_MANIFEST".into()),
        "stage" => serde_json::to_value(update_engine::staging::stage(
            Path::new(get("--root")?),
            get("--index-url")?,
            get("--target-version")?,
            get("--target-manifest")?,
            get("--source-version")?,
        )?)
        .map_err(|_| "INVALID_TRANSACTION".into()),
        "status" => Ok(serde_json::to_value(
            update_engine::staging::current(Path::new(get("--root")?))?.map(|(_, t)| t),
        )
        .map_err(|_| "INVALID_TRANSACTION")?),
        "bridge-progress" => {
            let percent = update_engine::staging::current(Path::new(get("--root")?))?
                .map(|(_, transaction)| transaction.progress_percent.round() as u64)
                .unwrap_or(0)
                .min(100);
            Ok(serde_json::json!(percent))
        }
        _ => Err("INVALID_COMMAND".into()),
    }
}

#[cfg(windows)]
fn bridge_result_path() -> Option<std::path::PathBuf> {
    let args: Vec<_> = std::env::args().collect();
    if args.get(1).map(String::as_str) != Some("bridge") {
        return None;
    }
    let index = args.iter().position(|value| value == "--root")?;
    let root = std::path::Path::new(args.get(index + 1)?);
    if !root.join("portable.json").is_file() {
        return None;
    }
    Some(root.join("updates/bridge/result.txt"))
}

#[cfg(windows)]
fn write_bridge_result(path: Option<std::path::PathBuf>, status: &str) {
    if let Some(path) = path {
        if let Some(parent) = path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        let _ = update_engine::state::atomic_write(&path, status.as_bytes());
    }
}

fn main() {
    #[cfg(windows)]
    let bridge_result = bridge_result_path();
    match run() {
        Ok(value) => {
            println!("{value}");
            let action = std::env::args().nth(1);
            if [Some("install"), Some("bridge")].contains(&action.as_deref())
                && value["enginePhase"] != "COMMITTED"
            {
                #[cfg(windows)]
                write_bridge_result(bridge_result, "2\nNOT_COMMITTED\n");
                std::process::exit(2);
            }
            #[cfg(windows)]
            if action.as_deref() == Some("bridge") {
                write_bridge_result(bridge_result, "0\nCOMMITTED\n");
            }
        }
        Err(code) => {
            eprintln!("{}", serde_json::json!({"error": code}));
            #[cfg(windows)]
            write_bridge_result(bridge_result, &format!("1\n{code}\n"));
            std::process::exit(1);
        }
    }
}
