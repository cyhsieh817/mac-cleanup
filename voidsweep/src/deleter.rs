use std::path::Path;
use std::process::Command;

use crate::scanner::is_protected;
use crate::types::DeleteMode;

pub struct DeleteOutcome {
    pub successes: Vec<String>,
    pub failures: Vec<(String, String)>,
    pub freed_bytes: u64,
}

pub fn execute(items: &[(std::path::PathBuf, u64)], mode: DeleteMode) -> DeleteOutcome {
    let mut successes = Vec::new();
    let mut failures = Vec::new();
    let mut freed_bytes = 0u64;

    for (path, size) in items {
        if is_protected(path) {
            failures.push((path.display().to_string(), "refused: protected path".into()));
            continue;
        }
        let result = match mode {
            DeleteMode::Trash => trash::delete(path).map_err(|e| e.to_string()),
            DeleteMode::Permanent => permanent_delete(path).map_err(|e| e.to_string()),
        };
        match result {
            Ok(()) => {
                freed_bytes = freed_bytes.saturating_add(*size);
                successes.push(path.display().to_string());
            }
            Err(e) => failures.push((path.display().to_string(), e)),
        }
    }

    DeleteOutcome { successes, failures, freed_bytes }
}

fn permanent_delete(path: &Path) -> std::io::Result<()> {
    let meta = std::fs::symlink_metadata(path)?;
    if meta.file_type().is_dir() {
        std::fs::remove_dir_all(path)
    } else {
        std::fs::remove_file(path)
    }
}

pub fn reveal_in_finder(path: &Path) {
    let _ = Command::new("open").arg("-R").arg(path).spawn();
}
