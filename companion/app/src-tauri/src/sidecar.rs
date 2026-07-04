use std::io::{BufRead, BufReader};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

pub struct SidecarState {
    pub child: Mutex<Option<Child>>,
    pub token: Mutex<Option<String>>,
    pub port: u16,
}

impl SidecarState {
    pub fn new() -> Self {
        Self {
            child: Mutex::new(None),
            token: Mutex::new(None),
            port: 47291,
        }
    }
}

impl Default for SidecarState {
    fn default() -> Self {
        Self::new()
    }
}

/// Locate the `genesis` executable in PATH.
fn find_genesis() -> Option<String> {
    // Try `which genesis` / `where genesis`
    #[cfg(target_os = "windows")]
    let output = Command::new("where").arg("genesis").output().ok()?;
    #[cfg(not(target_os = "windows"))]
    let output = Command::new("which").arg("genesis").output().ok()?;

    if output.status.success() {
        let path = String::from_utf8_lossy(&output.stdout)
            .lines()
            .next()
            .unwrap_or("")
            .trim()
            .to_string();
        if !path.is_empty() {
            return Some(path);
        }
    }
    None
}

/// Kill any stale `genesis companion --serve` process still holding the port
/// from a previous run. Without this, our fresh sidecar can't bind 47291 and
/// the UI hangs connecting to an orphan whose token we don't have.
#[cfg(target_os = "windows")]
fn kill_stale_backends() {
    // WMImic: find python processes whose command line runs "companion --serve".
    let _ = Command::new("powershell")
        .args([
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | \
             Where-Object { $_.CommandLine -like '*companion*--serve*' } | \
             ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }",
        ])
        .output();
    std::thread::sleep(Duration::from_millis(400));
}

#[cfg(not(target_os = "windows"))]
fn kill_stale_backends() {
    let _ = Command::new("pkill")
        .args(["-f", "companion --serve"])
        .output();
    std::thread::sleep(Duration::from_millis(400));
}

/// Spawn `genesis companion --serve` and wait for `READY token=<hex>` on stdout.
/// Returns Err if genesis is not found or if the token is not received within 15s.
pub fn spawn_sidecar(state: &SidecarState) -> Result<(), String> {
    let genesis = find_genesis()
        .ok_or_else(|| "genesis not found in PATH — run: pip install genesis-architect-pro[companion]".to_string())?;

    // Clear any orphaned backend from a prior run before we bind the port.
    kill_stale_backends();

    let mut child = Command::new(&genesis)
        .args(["companion", "--serve"])
        .stdout(Stdio::piped())
        .stderr(Stdio::null()) // silence stderr in app context
        .spawn()
        .map_err(|e| format!("failed to spawn genesis: {e}"))?;

    let stdout = child
        .stdout
        .take()
        .ok_or("could not capture sidecar stdout")?;

    let reader = BufReader::new(stdout);
    let deadline = Instant::now() + Duration::from_secs(15);
    let mut token_found: Option<String> = None;

    for line in reader.lines() {
        if Instant::now() > deadline {
            break;
        }
        let line = line.map_err(|e| format!("stdout read error: {e}"))?;
        if let Some(rest) = line.strip_prefix("READY token=") {
            let tok = rest.trim().to_string();
            if tok.len() == 64 {
                token_found = Some(tok);
                break;
            }
        }
    }

    let token = token_found
        .ok_or_else(|| "sidecar did not emit READY token within 15s".to_string())?;

    *state.child.lock().unwrap() = Some(child);
    *state.token.lock().unwrap() = Some(token);

    Ok(())
}

/// Kill the sidecar process gracefully.
pub fn kill_sidecar(state: &SidecarState) {
    let mut guard = state.child.lock().unwrap();
    if let Some(mut child) = guard.take() {
        // Try SIGTERM first (Unix), then kill
        #[cfg(target_os = "windows")]
        {
            let _ = Command::new("taskkill")
                .args(["/PID", &child.id().to_string(), "/F"])
                .output();
        }
        #[cfg(not(target_os = "windows"))]
        {
            unsafe {
                libc::kill(child.id() as libc::pid_t, libc::SIGTERM);
            }
            std::thread::sleep(Duration::from_millis(500));
        }
        let _ = child.kill();
        let _ = child.wait();
    }
}
