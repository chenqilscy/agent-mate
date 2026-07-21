// AgentMate desktop shell (Tauri 2). The application uses a borderless window
// without reserving a custom title-bar row. On startup we spawn the bundled Python backend as a sidecar
// and kill it on exit. A system tray keeps the app alive when the window is
// closed (X hides to tray; the tray's 退出 actually quits).
use std::sync::Mutex;
use std::time::Duration;

use serde::Serialize;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, RunEvent, WindowEvent};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;
use tauri_plugin_updater::UpdaterExt;
use url::Url;

/// Holds the backend sidecar child so we can terminate it on exit.
struct Backend(Mutex<Option<CommandChild>>);

#[derive(Serialize)]
struct DesktopUpdateResult {
    status: &'static str,
    current_version: String,
    version: Option<String>,
    notes: Option<String>,
    release_id: Option<String>,
    rollback: bool,
    forced: bool,
}

fn update_endpoint(base: &str, channel: &str) -> Result<Url, String> {
    if channel != "stable" && channel != "beta" {
        return Err("update channel must be stable or beta".into());
    }
    let parsed = Url::parse(base.trim()).map_err(|_| "invalid update endpoint")?;
    let local_debug = cfg!(debug_assertions)
        && matches!(parsed.host_str(), Some("localhost" | "127.0.0.1" | "::1"));
    if parsed.scheme() != "https" && !local_debug {
        return Err("production update endpoint must use https".into());
    }
    let root = parsed.as_str().trim_end_matches('/');
    Url::parse(&format!(
        "{root}/api/desktop-updates/{channel}/{{{{target}}}}/{{{{arch}}}}/{{{{current_version}}}}"
    ))
    .map_err(|_| "invalid update endpoint path".into())
}

#[cfg(test)]
mod tests {
    use super::update_endpoint;

    #[test]
    fn desktop_update_endpoint_requires_https_and_known_channel() {
        let url = update_endpoint("https://updates.example.com/", "stable").unwrap();
        assert!(url.as_str().contains("/api/desktop-updates/stable/"));
        assert!(update_endpoint("http://updates.example.com", "stable").is_err());
        assert!(update_endpoint("https://updates.example.com", "nightly").is_err());
    }
}

#[tauri::command]
async fn check_desktop_update(
    app: AppHandle,
    endpoint: String,
    channel: String,
    device_id: String,
    install: bool,
) -> Result<DesktopUpdateResult, String> {
    if device_id.len() < 8
        || device_id.len() > 160
        || !device_id
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || "._:-".contains(c))
    {
        return Err("invalid update device id".into());
    }
    let url = update_endpoint(&endpoint, &channel)?;
    let updater = app
        .updater_builder()
        // The signed Server manifest is authoritative for an explicit rollback.
        .version_comparator(|current, release| release.version != current)
        .endpoints(vec![url])
        .map_err(|e| e.to_string())?
        .header("X-AgentMate-Device", &device_id)
        .map_err(|e| e.to_string())?
        .timeout(Duration::from_secs(20))
        .build()
        .map_err(|e| e.to_string())?;
    let current_version = app.package_info().version.to_string();
    let Some(update) = updater.check().await.map_err(|e| e.to_string())? else {
        return Ok(DesktopUpdateResult {
            status: "latest",
            current_version,
            version: None,
            notes: None,
            release_id: None,
            rollback: false,
            forced: false,
        });
    };
    let version = update.version.clone();
    let notes = update.body.clone();
    let release_id = update
        .raw_json
        .get("release_id")
        .and_then(|v| v.as_str())
        .map(ToOwned::to_owned);
    let rollback = update
        .raw_json
        .get("rollback")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    let forced = update
        .raw_json
        .get("forced")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    if install {
        update
            .download_and_install(|_, _| {}, || {})
            .await
            .map_err(|e| e.to_string())?;
        app.restart();
    }
    Ok(DesktopUpdateResult {
        status: "available",
        current_version,
        version: Some(version),
        notes,
        release_id,
        rollback,
        forced,
    })
}

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
        .invoke_handler(tauri::generate_handler![check_desktop_update])
        .setup(|app| {
            // ---- backend sidecar: spawn + drain its output ----
            match app.handle().shell().sidecar("agentmate-backend") {
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
                    Err(e) => eprintln!("[agentmate] backend spawn failed: {e}"),
                },
                Err(e) => eprintln!("[agentmate] backend sidecar missing: {e}"),
            }

            // ---- system tray ----
            let show_i = MenuItem::with_id(app, "show", "显示 AgentMate", true, None::<&str>)?;
            let quit_i = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show_i, &quit_i])?;
            let _tray = TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("AgentMate")
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
        .expect("error while building AgentMate")
        .run(|app, event| {
            // Kill the backend on a real quit (tray → 退出 → app.exit).
            if matches!(event, RunEvent::ExitRequested { .. } | RunEvent::Exit) {
                if let Some(child) = app.state::<Backend>().0.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        });
}
