// WorkBuddy desktop shell (Tauri 2). Borderless window (the app draws its own
// menubar); window controls + dragging come from the frontend via
// @tauri-apps/api. On startup we spawn the bundled Python backend as a sidecar
// and kill it on exit. A system tray keeps the app alive when the window is
// closed (X hides to tray; the tray's 退出 actually quits).
use std::sync::Mutex;

use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{Manager, RunEvent, WindowEvent};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

/// Holds the backend sidecar child so we can terminate it on exit.
struct Backend(Mutex<Option<CommandChild>>);

fn show_window(app: &tauri::AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.show();
        let _ = w.unminimize();
        let _ = w.set_focus();
    }
}

fn toggle_window(app: &tauri::AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        if w.is_visible().unwrap_or(false) {
            let _ = w.hide();
        } else {
            show_window(app);
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let mut builder = tauri::Builder::default().plugin(tauri_plugin_shell::init());

    // Desktop-only: auto-update + relaunch-after-update.
    #[cfg(desktop)]
    {
        builder = builder
            .plugin(tauri_plugin_updater::Builder::new().build())
            .plugin(tauri_plugin_process::init());
    }

    builder
        .manage(Backend(Mutex::new(None)))
        .setup(|app| {
            // ---- backend sidecar: spawn + drain its output ----
            match app.handle().shell().sidecar("workbuddy-backend") {
                Ok(cmd) => match cmd.spawn() {
                    Ok((mut rx, child)) => {
                        app.state::<Backend>().0.lock().unwrap().replace(child);
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

            // ---- system tray ----
            let show_i = MenuItem::with_id(app, "show", "显示 WorkBuddy", true, None::<&str>)?;
            let quit_i = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show_i, &quit_i])?;
            let _tray = TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("WorkBuddy")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => show_window(app),
                    "quit" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        toggle_window(tray.app_handle());
                    }
                })
                .build(app)?;

            // ---- close (X) hides to tray instead of quitting ----
            if let Some(window) = app.get_webview_window("main") {
                let w = window.clone();
                window.on_window_event(move |event| {
                    if let WindowEvent::CloseRequested { api, .. } = event {
                        api.prevent_close();
                        let _ = w.hide();
                    }
                });
            }

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building WorkBuddy")
        .run(|app, event| {
            // Kill the backend on a real quit (tray → 退出 → app.exit).
            if matches!(event, RunEvent::ExitRequested { .. } | RunEvent::Exit) {
                if let Some(child) = app.state::<Backend>().0.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        });
}
