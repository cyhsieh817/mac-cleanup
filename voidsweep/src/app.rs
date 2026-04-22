use std::path::PathBuf;
use std::sync::mpsc::{channel, Receiver};

use eframe::egui;
use egui_extras::{Column, TableBuilder};
use humansize::{format_size, BINARY};

use crate::deleter::{self, DeleteOutcome};
use crate::scanner::{self, ScanHandle, ScanMode, ScanMsg};
use crate::types::{DeleteCandidate, DeleteMode, SortKey};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Tab {
    Sweep,
    Caches,
}

impl Tab {
    fn label(&self) -> &'static str {
        match self {
            Tab::Sweep => "🪦  _DELETE_ Sweep",
            Tab::Caches => "🧹  Cache Cleanup",
        }
    }
    fn scan_mode(&self) -> ScanMode {
        match self {
            Tab::Sweep => ScanMode::DeletePrefix,
            Tab::Caches => ScanMode::Caches,
        }
    }
}

pub struct VoidSweepApp {
    tab: Tab,
    roots: Vec<PathBuf>,
    candidates: Vec<DeleteCandidate>,
    scanning: bool,
    scan_handle: Option<ScanHandle>,
    rx: Option<Receiver<ScanMsg>>,
    sort: SortKey,
    filter: String,
    mode: DeleteMode,
    status: String,
    confirm_open: bool,
    last_outcome: Option<DeleteOutcome>,
    log_lines: Vec<String>,
}

impl Default for VoidSweepApp {
    fn default() -> Self {
        let roots = default_roots();
        Self {
            tab: Tab::Sweep,
            roots,
            candidates: Vec::new(),
            scanning: false,
            scan_handle: None,
            rx: None,
            sort: SortKey::SizeDesc,
            filter: String::new(),
            mode: DeleteMode::Trash,
            status: "ready — pick a tab, configure roots, then Scan".to_string(),
            confirm_open: false,
            last_outcome: None,
            log_lines: Vec::new(),
        }
    }
}

fn default_roots() -> Vec<PathBuf> {
    let mut v = Vec::new();
    if let Some(home) = dirs::home_dir() {
        for sub in ["Documents", "Downloads", "Desktop", "Projects"] {
            let p = home.join(sub);
            if p.exists() {
                v.push(p);
            }
        }
    }
    if v.is_empty() {
        if let Some(h) = dirs::home_dir() {
            v.push(h);
        }
    }
    v
}

fn preset_roots() -> Vec<(String, PathBuf)> {
    let mut v: Vec<(String, PathBuf)> = Vec::new();
    if let Some(home) = dirs::home_dir() {
        for sub in ["Documents", "Downloads", "Desktop", "Library", "Projects"] {
            v.push((sub.to_string(), home.join(sub)));
        }
        v.push(("$HOME".to_string(), home));
    }
    // User-defined presets via env: VOIDSWEEP_PRESETS="Label1=/abs/path1:Label2=/abs/path2"
    if let Ok(env) = std::env::var("VOIDSWEEP_PRESETS") {
        for chunk in env.split(':') {
            if let Some((label, path)) = chunk.split_once('=') {
                let label = label.trim();
                let path = path.trim();
                if !label.is_empty() && !path.is_empty() {
                    if let Some(p) = scanner::expand(path) {
                        v.push((label.to_string(), p));
                    }
                }
            }
        }
    }
    v.into_iter().filter(|(_, p)| p.exists()).collect()
}

impl VoidSweepApp {
    pub fn new(_cc: &eframe::CreationContext<'_>) -> Self {
        Self::default()
    }

    fn push_log(&mut self, line: String) {
        if self.log_lines.len() > 200 {
            self.log_lines.drain(0..50);
        }
        self.log_lines.push(line);
    }

    fn drain_scan(&mut self) {
        let mut done = false;
        if let Some(rx) = &self.rx {
            let mut burst = 0;
            loop {
                match rx.try_recv() {
                    Ok(ScanMsg::Found(c)) => {
                        self.candidates.push(c);
                    }
                    Ok(ScanMsg::Progress(s)) => {
                        self.status = s.clone();
                    }
                    Ok(ScanMsg::Done(n)) => {
                        self.status = format!("scan complete — {n} candidate(s) found");
                        done = true;
                        break;
                    }
                    Ok(ScanMsg::Error(e)) => {
                        let line = format!("error: {e}");
                        self.status = line.clone();
                    }
                    Err(std::sync::mpsc::TryRecvError::Empty) => break,
                    Err(std::sync::mpsc::TryRecvError::Disconnected) => {
                        done = true;
                        break;
                    }
                }
                burst += 1;
                if burst > 200 {
                    break;
                }
            }
        }
        if done {
            self.scanning = false;
            self.rx = None;
            self.scan_handle = None;
            self.apply_sort();
            let final_status = self.status.clone();
            self.push_log(final_status);
        }
    }

    fn apply_sort(&mut self) {
        match self.sort {
            SortKey::SizeDesc => self.candidates.sort_by(|a, b| b.size_bytes.cmp(&a.size_bytes)),
            SortKey::AgeDesc => self.candidates.sort_by(|a, b| {
                b.age_days().unwrap_or(-1).cmp(&a.age_days().unwrap_or(-1))
            }),
            SortKey::PathAsc => self.candidates.sort_by(|a, b| a.path.cmp(&b.path)),
        }
    }

    fn start_scan(&mut self) {
        if self.scanning {
            return;
        }
        if matches!(self.tab, Tab::Sweep) && self.roots.is_empty() {
            self.status = "no scan roots — add at least one".into();
            return;
        }
        self.candidates.clear();
        self.last_outcome = None;
        let (tx, rx) = channel();
        let roots = if matches!(self.tab, Tab::Caches) {
            Vec::new()
        } else {
            self.roots.clone()
        };
        let handle = scanner::spawn_scan(self.tab.scan_mode(), roots, tx);
        self.scan_handle = Some(handle);
        self.rx = Some(rx);
        self.scanning = true;
        self.status = format!("scanning ({:?})…", self.tab);
        let log = self.status.clone();
        self.push_log(log);
    }

    fn stop_scan(&mut self) {
        if let Some(h) = &self.scan_handle {
            h.stop_flag.store(true, std::sync::atomic::Ordering::Relaxed);
        }
        self.status = "stopping…".to_string();
    }

    fn visible_indices(&self) -> Vec<usize> {
        let f = self.filter.to_lowercase();
        self.candidates
            .iter()
            .enumerate()
            .filter(|(_, c)| {
                f.is_empty()
                    || c.path.to_string_lossy().to_lowercase().contains(&f)
                    || c.display_name.to_lowercase().contains(&f)
            })
            .map(|(i, _)| i)
            .collect()
    }

    fn execute_delete(&mut self) {
        let items: Vec<(PathBuf, u64)> = self
            .candidates
            .iter()
            .filter(|c| c.selected)
            .map(|c| (c.path.clone(), c.size_bytes))
            .collect();
        if items.is_empty() {
            self.status = "nothing selected".into();
            return;
        }
        let outcome = deleter::execute(&items, self.mode);
        self.status = format!(
            "{} succeeded · {} failed · freed {}",
            outcome.successes.len(),
            outcome.failures.len(),
            format_size(outcome.freed_bytes, BINARY),
        );
        let success_set: std::collections::HashSet<String> =
            outcome.successes.iter().cloned().collect();
        for fail in &outcome.failures {
            self.log_lines
                .push(format!("FAIL  {}  — {}", fail.0, fail.1));
        }
        let final_status = self.status.clone();
        self.push_log(final_status);
        self.candidates
            .retain(|c| !success_set.contains(&c.path.display().to_string()));
        self.last_outcome = Some(outcome);
    }

    fn pick_root(&mut self) {
        if let Some(p) = rfd::FileDialog::new().pick_folder() {
            if !self.roots.contains(&p) {
                self.roots.push(p);
            }
        }
    }
}

impl eframe::App for VoidSweepApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        if self.scanning {
            self.drain_scan();
            ctx.request_repaint_after(std::time::Duration::from_millis(120));
        }

        egui::TopBottomPanel::top("top").show(ctx, |ui| {
            ui.horizontal(|ui| {
                ui.heading("VoidSweep");
                ui.separator();
                for t in [Tab::Sweep, Tab::Caches] {
                    let selected = self.tab == t;
                    if ui
                        .selectable_label(selected, t.label())
                        .clicked()
                        && !self.scanning
                    {
                        self.tab = t;
                        self.candidates.clear();
                        self.status = format!("switched to {}", t.label());
                    }
                }
                ui.separator();
                if !self.scanning {
                    if ui.button("🔍  Scan").clicked() {
                        self.start_scan();
                    }
                } else if ui.button("⏹  Stop").clicked() {
                    self.stop_scan();
                }
                if ui.button("🧹  Clear results").clicked() {
                    self.candidates.clear();
                    self.status = "results cleared".into();
                }
            });

            if matches!(self.tab, Tab::Sweep) {
                ui.horizontal(|ui| {
                    ui.label("scan roots:");
                    if ui.button("➕ pick folder…").clicked() {
                        self.pick_root();
                    }
                    ui.label("|");
                    for (label, path) in preset_roots() {
                        if ui.small_button(format!("+ {label}")).clicked()
                            && !self.roots.contains(&path)
                        {
                            self.roots.push(path);
                        }
                    }
                });
                ui.horizontal_wrapped(|ui| {
                    let mut to_remove: Option<usize> = None;
                    for (i, r) in self.roots.iter().enumerate() {
                        ui.group(|ui| {
                            ui.label(
                                egui::RichText::new(r.display().to_string())
                                    .monospace()
                                    .small(),
                            );
                            if ui.small_button("✕").clicked() {
                                to_remove = Some(i);
                            }
                        });
                    }
                    if let Some(i) = to_remove {
                        self.roots.remove(i);
                    }
                });
            } else {
                ui.label(
                    egui::RichText::new(
                        "Cache Cleanup scans well-known dev caches in $HOME (npm, cargo, Xcode, Gradle, …). Roots are ignored.",
                    )
                    .small(),
                );
            }
        });

        egui::TopBottomPanel::bottom("bottom").show(ctx, |ui| {
            ui.horizontal(|ui| {
                ui.label("mode:");
                ui.radio_value(&mut self.mode, DeleteMode::Trash, "🗑 Trash (reversible)");
                ui.radio_value(&mut self.mode, DeleteMode::Permanent, "💀 Permanent");
                ui.separator();
                let selected: Vec<_> = self.candidates.iter().filter(|c| c.selected).collect();
                let sel_count = selected.len();
                let sel_bytes: u64 = selected.iter().map(|c| c.size_bytes).sum();
                ui.label(format!(
                    "selected: {} · {}",
                    sel_count,
                    format_size(sel_bytes, BINARY)
                ));
                ui.separator();
                let label = match self.mode {
                    DeleteMode::Trash => "Move to Trash",
                    DeleteMode::Permanent => "Delete Permanently",
                };
                let enabled = sel_count > 0;
                if ui
                    .add_enabled(enabled, egui::Button::new(format!("⚠ {label}")))
                    .clicked()
                {
                    self.confirm_open = true;
                }
            });
            ui.horizontal(|ui| {
                if self.scanning {
                    ui.add(egui::Spinner::new().size(14.0));
                }
                ui.label(egui::RichText::new(&self.status).monospace().small());
            });
            egui::CollapsingHeader::new("scan log")
                .default_open(false)
                .show(ui, |ui| {
                    egui::ScrollArea::vertical()
                        .max_height(120.0)
                        .stick_to_bottom(true)
                        .show(ui, |ui| {
                            for line in &self.log_lines {
                                ui.label(
                                    egui::RichText::new(line).monospace().small(),
                                );
                            }
                        });
                });
        });

        egui::CentralPanel::default().show(ctx, |ui| {
            ui.horizontal(|ui| {
                ui.label("filter:");
                ui.add(egui::TextEdit::singleline(&mut self.filter).desired_width(220.0));
                ui.separator();
                ui.label("sort:");
                let mut sort = self.sort;
                egui::ComboBox::from_id_salt("sort_combo")
                    .selected_text(sort.label())
                    .show_ui(ui, |ui| {
                        ui.selectable_value(&mut sort, SortKey::SizeDesc, "Size ↓");
                        ui.selectable_value(&mut sort, SortKey::AgeDesc, "Age ↓");
                        ui.selectable_value(&mut sort, SortKey::PathAsc, "Path ↑");
                    });
                if sort != self.sort {
                    self.sort = sort;
                    self.apply_sort();
                }
                ui.separator();
                let total_bytes: u64 = self.candidates.iter().map(|c| c.size_bytes).sum();
                ui.label(format!(
                    "{} candidates · total {}",
                    self.candidates.len(),
                    format_size(total_bytes, BINARY)
                ));
                ui.separator();
                if ui.small_button("select all visible").clicked() {
                    let visible = self.visible_indices();
                    for i in visible {
                        self.candidates[i].selected = true;
                    }
                }
                if ui.small_button("deselect all").clicked() {
                    for c in &mut self.candidates {
                        c.selected = false;
                    }
                }
            });
            ui.separator();

            let visible = self.visible_indices();
            let row_height = 22.0;

            TableBuilder::new(ui)
                .striped(true)
                .resizable(true)
                .cell_layout(egui::Layout::left_to_right(egui::Align::Center))
                .column(Column::exact(28.0))
                .column(Column::exact(28.0))
                .column(Column::initial(280.0).at_least(120.0))
                .column(Column::initial(80.0).at_least(60.0))
                .column(Column::initial(70.0).at_least(50.0))
                .column(Column::remainder().at_least(200.0))
                .column(Column::exact(70.0))
                .header(22.0, |mut header| {
                    header.col(|ui| { ui.strong("✓"); });
                    header.col(|ui| { ui.label(""); });
                    header.col(|ui| { ui.strong("Name"); });
                    header.col(|ui| { ui.strong("Size"); });
                    header.col(|ui| { ui.strong("Age (d)"); });
                    header.col(|ui| { ui.strong("Parent Directory"); });
                    header.col(|ui| { ui.strong("Action"); });
                })
                .body(|body| {
                    body.rows(row_height, visible.len(), |mut row| {
                        let idx = visible[row.index()];
                        let c = &mut self.candidates[idx];
                        row.col(|ui| { ui.checkbox(&mut c.selected, ""); });
                        row.col(|ui| {
                            ui.label(c.kind.icon());
                        });
                        row.col(|ui| {
                            let resp = ui.label(&c.display_name);
                            if !c.note.is_empty() {
                                resp.on_hover_text(format!(
                                    "{}\n{}",
                                    c.path.display(),
                                    c.note
                                ));
                            } else {
                                resp.on_hover_text(c.path.display().to_string());
                            }
                        });
                        row.col(|ui| {
                            ui.label(format_size(c.size_bytes, BINARY));
                        });
                        row.col(|ui| {
                            let txt = c.age_days().map(|d| d.to_string()).unwrap_or_else(|| "?".into());
                            ui.label(txt);
                        });
                        row.col(|ui| {
                            let parent = c.parent.display().to_string();
                            ui.add(egui::Label::new(
                                egui::RichText::new(&parent).monospace().small(),
                            ).truncate());
                        });
                        row.col(|ui| {
                            if ui.small_button("Reveal").clicked() {
                                deleter::reveal_in_finder(&c.path);
                            }
                        });
                    });
                });
        });

        if self.confirm_open {
            let mut close = false;
            let mut do_delete = false;
            let mode_label = match self.mode {
                DeleteMode::Trash => "Move to Trash",
                DeleteMode::Permanent => "PERMANENTLY DELETE",
            };
            let count = self.candidates.iter().filter(|c| c.selected).count();
            let size: u64 = self
                .candidates
                .iter()
                .filter(|c| c.selected)
                .map(|c| c.size_bytes)
                .sum();
            egui::Window::new("Confirm")
                .collapsible(false)
                .resizable(false)
                .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
                .show(ctx, |ui| {
                    ui.label(format!(
                        "{} {} item(s), reclaiming {}.",
                        mode_label,
                        count,
                        format_size(size, BINARY)
                    ));
                    if matches!(self.mode, DeleteMode::Permanent) {
                        ui.colored_label(egui::Color32::LIGHT_RED, "Permanent deletion is irreversible.");
                    }
                    ui.horizontal(|ui| {
                        if ui.button("Cancel").clicked() {
                            close = true;
                        }
                        if ui.button(format!("Confirm — {mode_label}")).clicked() {
                            do_delete = true;
                            close = true;
                        }
                    });
                });
            if do_delete {
                self.execute_delete();
            }
            if close {
                self.confirm_open = false;
            }
        }
    }
}
