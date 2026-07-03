use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;
use tauri::{AppHandle, Emitter, Manager, State};

use crate::sidecar::{kill_sidecar, spawn_sidecar, SidecarState};

#[derive(Serialize, Deserialize)]
pub struct WsCredentials {
    pub port: u16,
    pub token: String,
}

/// Return the WebSocket port + auth token for the frontend.
#[tauri::command]
pub fn get_ws_credentials(state: State<SidecarState>) -> Option<WsCredentials> {
    let token = state.token.lock().unwrap().clone()?;
    Some(WsCredentials {
        port: state.port,
        token,
    })
}

/// Read .genesis/gde_session.json for the given project directory.
#[tauri::command]
pub fn read_session_state(project_dir: String) -> Result<serde_json::Value, String> {
    let path = Path::new(&project_dir)
        .join(".genesis")
        .join("gde_session.json");
    let raw = fs::read_to_string(&path)
        .map_err(|e| format!("cannot read session state: {e}"))?;
    serde_json::from_str(&raw).map_err(|e| format!("invalid JSON: {e}"))
}

/// Toggle Panel window visibility.
#[tauri::command]
pub fn toggle_panel(app: AppHandle) -> Result<(), String> {
    let panel = app
        .get_webview_window("panel")
        .ok_or("panel window not found")?;

    if panel.is_visible().unwrap_or(false) {
        panel.hide().map_err(|e| e.to_string())
    } else {
        panel.show().map_err(|e| e.to_string())?;
        panel.set_focus().map_err(|e| e.to_string())
    }
}

/// Restart the Python sidecar (e.g. after crash).
#[tauri::command]
pub fn restart_sidecar(
    app: AppHandle,
    state: State<SidecarState>,
) -> Result<(), String> {
    kill_sidecar(&state);
    *state.token.lock().unwrap() = None;
    spawn_sidecar(&state)?;
    // Notify frontend that sidecar is back
    app.emit("genesis://sidecar-restarted", ())
        .map_err(|e| e.to_string())?;
    Ok(())
}

/// Open the Canvas workspace HTML in the default browser.
#[tauri::command]
pub fn open_canvas(project_dir: String) -> Result<(), String> {
    let path = Path::new(&project_dir)
        .join(".genesis")
        .join("workspace.html");
    if !path.exists() {
        return Err("workspace.html not found — run `genesis ui` first".to_string());
    }
    let url = format!("file://{}", path.display());
    open::that(url).map_err(|e| e.to_string())
}

/// Show the panel at a specific anchor position relative to the bubble.
#[tauri::command]
pub fn anchor_panel_to_bubble(
    app: AppHandle,
    bubble_x: i32,
    bubble_y: i32,
) -> Result<(), String> {
    let panel = app
        .get_webview_window("panel")
        .ok_or("panel window not found")?;

    // Position panel to the left of the bubble (assuming bubble is bottom-right)
    let panel_x = bubble_x - 395;
    let panel_y = bubble_y - 620;
    let panel_x = panel_x.max(8);
    let panel_y = panel_y.max(8);

    panel
        .set_position(tauri::PhysicalPosition::new(panel_x, panel_y))
        .map_err(|e| e.to_string())?;
    panel.show().map_err(|e| e.to_string())?;
    panel.set_focus().map_err(|e| e.to_string())
}
