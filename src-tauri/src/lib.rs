// WorkBuddy desktop shell (Tauri 2). The window is borderless (decorations off)
// because the app draws its own Windows-style menubar; window controls
// (minimize/maximize/close) and dragging are driven from the frontend via the
// @tauri-apps/api window commands, gated by capabilities/default.json.
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running WorkBuddy");
}
