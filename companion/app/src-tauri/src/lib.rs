mod commands;
mod sidecar;

use commands::{
    anchor_panel_to_bubble, get_ws_credentials, open_canvas, read_session_state,
    restart_sidecar, toggle_panel,
};
use sidecar::{kill_sidecar, spawn_sidecar, SidecarState};
use tauri::{Emitter, Manager, RunEvent};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_positioner::init())
        .plugin(tauri_plugin_store::Builder::default().build())
        .plugin(tauri_plugin_shell::init())
        .manage(SidecarState::new())
        .invoke_handler(tauri::generate_handler![
            get_ws_credentials,
            read_session_state,
            toggle_panel,
            restart_sidecar,
            open_canvas,
            anchor_panel_to_bubble,
        ])
        .setup(|app| {
            let state = app.state::<SidecarState>();

            // Spawn the Python sidecar — non-fatal if genesis not installed yet
            match spawn_sidecar(&state) {
                Ok(()) => {
                    eprintln!("[genesis-companion] sidecar started");
                }
                Err(e) => {
                    eprintln!("[genesis-companion] sidecar unavailable: {e}");
                    // Emit to frontend so it can show first-run instructions
                    if let Some(bubble) = app.get_webview_window("bubble") {
                        let _ = bubble.emit(
                            "genesis://sidecar-error",
                            serde_json::json!({ "message": e }),
                        );
                    }
                }
            }

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error building tauri app")
        .run(|app, event| {
            if let RunEvent::ExitRequested { .. } = event {
                // Kill Python sidecar on exit — prevents orphan processes
                let state = app.state::<SidecarState>();
                kill_sidecar(&state);
            }
        });
}
