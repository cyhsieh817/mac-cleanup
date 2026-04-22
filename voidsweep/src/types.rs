use std::path::PathBuf;
use std::time::SystemTime;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CandidateKind {
    DeletePrefix,
    PackageCache,
    DevArtifact,
    LogTemp,
}

impl CandidateKind {
    pub fn icon(&self) -> &'static str {
        match self {
            CandidateKind::DeletePrefix => "🪦",
            CandidateKind::PackageCache => "📦",
            CandidateKind::DevArtifact => "🛠",
            CandidateKind::LogTemp => "📜",
        }
    }
}

#[derive(Debug, Clone)]
pub struct DeleteCandidate {
    pub kind: CandidateKind,
    pub path: PathBuf,
    pub display_name: String,
    pub parent: PathBuf,
    pub size_bytes: u64,
    pub modified: Option<SystemTime>,
    #[allow(dead_code)]
    pub is_dir: bool,
    pub selected: bool,
    pub note: String,
}

impl DeleteCandidate {
    pub fn age_days(&self) -> Option<i64> {
        let m = self.modified?;
        let now = SystemTime::now();
        let dur = now.duration_since(m).ok()?;
        Some((dur.as_secs() / 86_400) as i64)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SortKey {
    SizeDesc,
    AgeDesc,
    PathAsc,
}

impl SortKey {
    pub fn label(&self) -> &'static str {
        match self {
            SortKey::SizeDesc => "Size ↓",
            SortKey::AgeDesc => "Age ↓",
            SortKey::PathAsc => "Path ↑",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DeleteMode {
    Trash,
    Permanent,
}
