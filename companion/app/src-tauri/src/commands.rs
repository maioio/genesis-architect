use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;
use tauri::{AppHandle, Emitter, Manager, PhysicalPosition, PhysicalSize, State};

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

/// Restart the Python sidecar (e.g. after crash).
#[tauri::command]
pub fn restart_sidecar(app: AppHandle, state: State<SidecarState>) -> Result<(), String> {
    kill_sidecar(&state);
    *state.token.lock().unwrap() = None;
    spawn_sidecar(&state)?;
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

/// Which screen edge the dock clings to.
#[derive(Serialize, Deserialize, Clone, Copy, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum DockSide {
    Left,
    Right,
}

/// Dock the companion window to a screen edge at a given logical size, then
/// snap it flush against that edge (vertically centered). This is the single
/// source of truth for the window's geometry — the collapsed rail and the
/// expanded panel are just two different `width`/`height` calls to it.
///
/// Replaces the old bubble+panel two-window positioning math, which drifted
/// because it guessed the bubble's location instead of measuring the screen.
#[tauri::command]
pub fn dock_to_edge(
    app: AppHandle,
    side: DockSide,
    width: u32,
    height: u32,
) -> Result<(), String> {
    let win = app
        .get_webview_window("dock")
        .ok_or("dock window not found")?;

    let scale = win.scale_factor().map_err(|e| e.to_string())?;
    let monitor = win
        .current_monitor()
        .map_err(|e| e.to_string())?
        .ok_or("no monitor for window")?;
    let mon_pos = monitor.position();
    let mon_size = monitor.size();

    // Convert requested logical size to physical pixels for this monitor.
    let phys_w = (width as f64 * scale).round() as u32;
    let phys_h = (height as f64 * scale).round() as u32;

    // A small breathing gap from the very edge so the rounded corners read.
    let gap = (12.0 * scale).round() as i32;

    let x = match side {
        DockSide::Right => {
            mon_pos.x + mon_size.width as i32 - phys_w as i32 - gap
        }
        DockSide::Left => mon_pos.x + gap,
    };
    // Vertically centered on the monitor.
    let y = mon_pos.y + ((mon_size.height as i32 - phys_h as i32) / 2).max(0);

    win.set_size(PhysicalSize::new(phys_w, phys_h))
        .map_err(|e| e.to_string())?;
    win.set_position(PhysicalPosition::new(x, y))
        .map_err(|e| e.to_string())?;
    Ok(())
}

/// Slide the dock almost entirely off the screen edge, leaving only a thin
/// `peek` sliver on-screen to click and bring it back. This is the "hide it
/// to the side" affordance — the window stays alive and connected, just out
/// of the way and invisible over your work.
#[tauri::command]
pub fn set_hidden(
    app: AppHandle,
    side: DockSide,
    hidden: bool,
    width: u32,
    height: u32,
    peek: u32,
) -> Result<(), String> {
    let win = app
        .get_webview_window("dock")
        .ok_or("dock window not found")?;

    let scale = win.scale_factor().map_err(|e| e.to_string())?;
    let monitor = win
        .current_monitor()
        .map_err(|e| e.to_string())?
        .ok_or("no monitor for window")?;
    let mon_pos = monitor.position();
    let mon_size = monitor.size();

    let phys_w = (width as f64 * scale).round() as i32;
    let phys_h = (height as f64 * scale).round() as u32;
    let peek_px = (peek as f64 * scale).round() as i32;
    let gap = (12.0 * scale).round() as i32;

    let y = mon_pos.y + ((mon_size.height as i32 - phys_h as i32) / 2).max(0);

    let x = if hidden {
        // Push the window off-edge, leaving only `peek` px on-screen.
        match side {
            DockSide::Right => mon_pos.x + mon_size.width as i32 - peek_px,
            DockSide::Left => mon_pos.x + peek_px - phys_w,
        }
    } else {
        match side {
            DockSide::Right => mon_pos.x + mon_size.width as i32 - phys_w - gap,
            DockSide::Left => mon_pos.x + gap,
        }
    };

    win.set_position(PhysicalPosition::new(x, y))
        .map_err(|e| e.to_string())?;
    Ok(())
}
