mod app;
mod caches;
mod deleter;
mod scanner;
mod types;

use eframe::egui;

fn main() -> eframe::Result<()> {
    let opts = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([1100.0, 720.0])
            .with_min_inner_size([720.0, 480.0])
            .with_title("VoidSweep · _DELETE_ Sweeper"),
        ..Default::default()
    };
    eframe::run_native(
        "VoidSweep",
        opts,
        Box::new(|cc| Ok(Box::new(app::VoidSweepApp::new(cc)))),
    )
}
