use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::Sender;
use std::sync::Arc;
use std::thread;

use walkdir::WalkDir;

use crate::caches;
use crate::types::{CandidateKind, DeleteCandidate};

pub const PREFIX: &str = "_DELETE_";

const SKIP_DIR_NAMES: &[&str] = &[
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "target",
    "Pods",
    "DerivedData",
    "__pycache__",
    "Photos Library.photoslibrary",
    "Music Library.musiclibrary",
];

const PROTECTED_ROOTS: &[&str] = &[
    "/System", "/Library", "/Applications", "/usr", "/bin",
    "/sbin", "/etc", "/var", "/cores", "/private", "/dev",
];

pub enum ScanMsg {
    Found(DeleteCandidate),
    Progress(String),
    Done(usize),
    Error(String),
}

pub struct ScanHandle {
    pub stop_flag: Arc<AtomicBool>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ScanMode {
    DeletePrefix,
    Caches,
}

pub fn spawn_scan(
    mode: ScanMode,
    roots: Vec<PathBuf>,
    tx: Sender<ScanMsg>,
) -> ScanHandle {
    let stop = Arc::new(AtomicBool::new(false));
    let stop_clone = stop.clone();

    thread::spawn(move || {
        let count = match mode {
            ScanMode::DeletePrefix => scan_delete_prefix(&roots, &tx, &stop_clone),
            ScanMode::Caches => scan_caches(&tx, &stop_clone),
        };
        let _ = tx.send(ScanMsg::Done(count));
    });

    ScanHandle { stop_flag: stop }
}

fn scan_delete_prefix(
    roots: &[PathBuf],
    tx: &Sender<ScanMsg>,
    stop: &Arc<AtomicBool>,
) -> usize {
    let mut found = 0usize;
    let mut visited = 0usize;

    for root in roots {
        if stop.load(Ordering::Relaxed) {
            break;
        }
        if is_protected(root) {
            let _ = tx.send(ScanMsg::Error(format!(
                "refused protected root: {}",
                root.display()
            )));
            continue;
        }
        let _ = tx.send(ScanMsg::Progress(format!("scanning {}", root.display())));

        let mut it = WalkDir::new(root).follow_links(false).into_iter();
        loop {
            if stop.load(Ordering::Relaxed) {
                break;
            }
            let entry = match it.next() {
                Some(Ok(e)) => e,
                Some(Err(e)) => {
                    if visited % 4000 == 0 {
                        let _ = tx.send(ScanMsg::Progress(format!(
                            "skipped (denied?): {}",
                            e.path().map(|p| p.display().to_string()).unwrap_or_default()
                        )));
                    }
                    visited += 1;
                    continue;
                }
                None => break,
            };
            visited += 1;
            if visited % 1500 == 0 {
                let _ = tx.send(ScanMsg::Progress(format!(
                    "scanned {visited} entries · {found} found · at {}",
                    entry.path().display()
                )));
            }

            let name = entry.file_name().to_string_lossy().to_string();
            let is_dir = entry.file_type().is_dir();

            if name.starts_with(PREFIX) {
                let metadata = entry.metadata().ok();
                let modified = metadata.as_ref().and_then(|m| m.modified().ok());
                let size_bytes = if is_dir {
                    dir_size(entry.path(), stop)
                } else {
                    metadata.as_ref().map(|m| m.len()).unwrap_or(0)
                };
                let parent = entry
                    .path()
                    .parent()
                    .map(Path::to_path_buf)
                    .unwrap_or_default();
                let candidate = DeleteCandidate {
                    kind: CandidateKind::DeletePrefix,
                    path: entry.path().to_path_buf(),
                    display_name: name,
                    parent,
                    size_bytes,
                    modified,
                    is_dir,
                    selected: true,
                    note: String::new(),
                };
                found += 1;
                if tx.send(ScanMsg::Found(candidate)).is_err() {
                    return found;
                }
                if is_dir {
                    it.skip_current_dir();
                }
            } else if is_dir && SKIP_DIR_NAMES.iter().any(|s| *s == name.as_str()) {
                it.skip_current_dir();
            }
        }
    }
    found
}

fn scan_caches(tx: &Sender<ScanMsg>, stop: &Arc<AtomicBool>) -> usize {
    let mut found = 0;
    for target in caches::all_targets() {
        if stop.load(Ordering::Relaxed) {
            break;
        }
        let path = match expand(&target.path) {
            Some(p) if p.exists() => p,
            _ => continue,
        };
        let _ = tx.send(ScanMsg::Progress(format!(
            "measuring {}",
            path.display()
        )));
        let metadata = std::fs::symlink_metadata(&path).ok();
        let is_dir = metadata.as_ref().map(|m| m.is_dir()).unwrap_or(false);
        let modified = metadata.as_ref().and_then(|m| m.modified().ok());
        let size_bytes = if is_dir {
            dir_size(&path, stop)
        } else {
            metadata.as_ref().map(|m| m.len()).unwrap_or(0)
        };
        if size_bytes < target.min_bytes {
            continue;
        }
        let parent = path.parent().map(Path::to_path_buf).unwrap_or_default();
        let display_name = target.name.to_string();
        let candidate = DeleteCandidate {
            kind: target.kind,
            path: path.clone(),
            display_name,
            parent,
            size_bytes,
            modified,
            is_dir,
            selected: false,
            note: target.note.to_string(),
        };
        found += 1;
        if tx.send(ScanMsg::Found(candidate)).is_err() {
            return found;
        }
    }
    found
}

fn dir_size(path: &Path, stop: &Arc<AtomicBool>) -> u64 {
    let mut total = 0u64;
    for entry in WalkDir::new(path).follow_links(false).into_iter().flatten() {
        if stop.load(Ordering::Relaxed) {
            break;
        }
        if entry.file_type().is_file() {
            if let Ok(meta) = entry.metadata() {
                total = total.saturating_add(meta.len());
            }
        }
    }
    total
}

pub fn expand(s: &str) -> Option<PathBuf> {
    if let Some(rest) = s.strip_prefix("~/") {
        let home = dirs::home_dir()?;
        Some(home.join(rest))
    } else if s == "~" {
        dirs::home_dir()
    } else {
        Some(PathBuf::from(s))
    }
}

pub fn is_protected(path: &Path) -> bool {
    let s = path.to_string_lossy();
    if s == "/" {
        return true;
    }
    if let Some(home) = dirs::home_dir() {
        if path == home.as_path() {
            return true;
        }
    }
    PROTECTED_ROOTS.iter().any(|p| s.as_ref() == *p)
}
