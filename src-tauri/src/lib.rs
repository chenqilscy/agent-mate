// WorkBuddy desktop shell (Tauri 2). Borderless window (the app draws its own
// menubar); window controls + dragging come from the frontend via
// @tauri-apps/api. On startup we spawn the bundled Python backend as a sidecar
// (binaries/workbuddy-backend-<triple>.exe) and kill it when the app exits, so
// the whole thing is truly double-click-to-run.
use std::sync::Mutex;

use tauri::{Manager, RunEvent};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

/// Holds the backend sidecar child so we can terminate it on exit.
struct Backend(Mutex<Option<CommandChild>>);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(Backend(Mutex::new(None)))
        .setup(|app| {
            match app.handle().shell().sidecar("workbuddy-backend") {
                Ok(cmd) => match cmd.spawn() {
                    Ok((mut rx, child)) => {
                        app.state::<Backend>().0.lock().unwrap().replace(child);
                        // Drain the backend's stdout/stderr so a full pipe buffer
                        // never blocks the backend process.
                        tauri::async_runtime::spawn(async move {
                            while let Some(event) = rx.recv().await {
                                if let CommandEvent::Terminated(_) = event {
                                    break;
                                }
                            }
                        });
                    }
                    Err(e) => eprintln!("[workbuddy] backend spawn failed: {e}"),
                },
                Err(e) => eprintln!("[workbuddy] backend sidecar missing: {e}"),
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building WorkBuddy")
        .run(|app, event| {
            // Kill the backend when the app is exiting so it doesn't linger.
            if let RunEvent::ExitRequested { .. } = event {
                if let Some(child) = app.state::<Backend>().0.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        });
}
