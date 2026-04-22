use crate::types::CandidateKind;

pub struct CacheTarget {
    pub kind: CandidateKind,
    pub name: &'static str,
    pub path: &'static str,
    pub note: &'static str,
    pub min_bytes: u64,
}

const MB: u64 = 1024 * 1024;

const PACKAGE_CACHES: &[(&str, &str)] = &[
    ("npm", "~/.npm"),
    ("yarn", "~/.yarn/cache"),
    ("pnpm", "~/.pnpm-store"),
    ("Bun", "~/.bun/install/cache"),
    ("CocoaPods", "~/Library/Caches/CocoaPods"),
    ("Composer", "~/.composer/cache"),
    ("Gem", "~/.gem"),
    ("Go Build", "~/Library/Caches/go-build"),
    ("Pip", "~/Library/Caches/pip"),
    ("uv", "~/Library/Caches/uv"),
    ("Cargo registry", "~/.cargo/registry"),
    ("Turborepo", "~/Library/Caches/turbo"),
    ("Homebrew", "~/Library/Caches/Homebrew"),
];

const DEV_ARTIFACTS: &[(&str, &str)] = &[
    ("Xcode DerivedData", "~/Library/Developer/Xcode/DerivedData"),
    ("Xcode Archives", "~/Library/Developer/Xcode/Archives"),
    ("iOS DeviceSupport", "~/Library/Developer/Xcode/iOS DeviceSupport"),
    ("Simulator Caches", "~/Library/Developer/CoreSimulator/Caches"),
    ("Gradle caches", "~/.gradle/caches"),
    ("Maven repository", "~/.m2/repository"),
    ("Android cache", "~/.android/cache"),
];

const LOG_TARGETS: &[(&str, &str, u64)] = &[
    ("App caches", "~/Library/Caches", 100 * MB),
    ("User logs", "~/Library/Logs", 50 * MB),
];

pub fn all_targets() -> Vec<CacheTarget> {
    let mut v = Vec::new();
    for (name, path) in PACKAGE_CACHES {
        v.push(CacheTarget {
            kind: CandidateKind::PackageCache,
            name,
            path,
            note: "package manager cache",
            min_bytes: MB,
        });
    }
    for (name, path) in DEV_ARTIFACTS {
        v.push(CacheTarget {
            kind: CandidateKind::DevArtifact,
            name,
            path,
            note: "dev tool artifact",
            min_bytes: MB,
        });
    }
    for (name, path, min_bytes) in LOG_TARGETS {
        v.push(CacheTarget {
            kind: CandidateKind::LogTemp,
            name,
            path,
            note: "logs/temp",
            min_bytes: *min_bytes,
        });
    }
    v
}
