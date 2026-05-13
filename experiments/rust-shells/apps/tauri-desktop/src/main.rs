#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

use serde::Serialize;
use serde_json::{Value, json};
use std::collections::BTreeMap;
use std::env;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::Duration;
use tauri::{AppHandle, Manager, State};
use trading_bot_core::{app_banner, service_api_route_path};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x08000000;

#[derive(Debug, Serialize)]
struct ServiceApiProxyResponse {
    ok: bool,
    status: u16,
    route_name: String,
    path: String,
    payload: Value,
    error: String,
}

#[derive(Default)]
struct ServiceProcessState {
    child: Mutex<Option<Child>>,
}

impl Drop for ServiceProcessState {
    fn drop(&mut self) {
        if let Ok(mut guard) = self.child.lock() {
            if let Some(mut child) = guard.take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
}

#[derive(Debug, Serialize)]
struct ServiceProcessResponse {
    ok: bool,
    running: bool,
    healthy: bool,
    managed: bool,
    pid: Option<u32>,
    base_url: String,
    message: String,
    error: String,
}

impl ServiceProcessResponse {
    fn ok(
        running: bool,
        healthy: bool,
        managed: bool,
        pid: Option<u32>,
        base_url: String,
        message: impl Into<String>,
    ) -> Self {
        Self {
            ok: true,
            running,
            healthy,
            managed,
            pid,
            base_url,
            message: message.into(),
            error: String::new(),
        }
    }

    fn err(
        running: bool,
        managed: bool,
        pid: Option<u32>,
        base_url: String,
        error: impl Into<String>,
    ) -> Self {
        Self {
            ok: false,
            running,
            healthy: false,
            managed,
            pid,
            base_url,
            message: String::new(),
            error: error.into(),
        }
    }
}

fn response_ok(
    route_name: &str,
    path: &str,
    status: u16,
    payload: Value,
) -> ServiceApiProxyResponse {
    ServiceApiProxyResponse {
        ok: (200..300).contains(&status),
        status,
        route_name: route_name.to_string(),
        path: path.to_string(),
        payload,
        error: String::new(),
    }
}

fn response_error(
    route_name: &str,
    path: &str,
    status: u16,
    error: impl Into<String>,
) -> ServiceApiProxyResponse {
    ServiceApiProxyResponse {
        ok: false,
        status,
        route_name: route_name.to_string(),
        path: path.to_string(),
        payload: json!({}),
        error: error.into(),
    }
}

fn is_loopback_host(host: &str) -> bool {
    matches!(host, "localhost" | "127.0.0.1" | "::1" | "[::1]")
}

fn normalize_bind_host(host: &str) -> String {
    let trimmed = host.trim();
    if trimmed.is_empty() {
        return "127.0.0.1".to_string();
    }
    if let Ok(url) = reqwest::Url::parse(trimmed) {
        return url.host_str().unwrap_or("127.0.0.1").to_string();
    }
    trimmed.trim_matches('/').to_string()
}

fn service_base_url(host: &str, port: u16) -> String {
    let host = normalize_bind_host(host);
    let display_host = if host == "::1" {
        "[::1]".to_string()
    } else {
        host
    };
    format!("http://{display_host}:{port}")
}

fn normalize_service_base_url(
    base_url: &str,
    allow_public_network_endpoint: bool,
) -> Result<reqwest::Url, String> {
    let normalized = if base_url.trim().is_empty() {
        "http://127.0.0.1:8000"
    } else {
        base_url.trim()
    };
    let parsed = reqwest::Url::parse(normalized)
        .map_err(|exc| format!("Invalid service API base URL: {exc}"))?;
    match parsed.scheme() {
        "http" | "https" => {}
        scheme => return Err(format!("Unsupported service API URL scheme: {scheme}")),
    }
    let host = parsed.host_str().unwrap_or_default();
    if !allow_public_network_endpoint && !is_loopback_host(host) {
        return Err(
            "Public service API endpoints are disabled. Use localhost/127.0.0.1 or enable the public endpoint control."
                .to_string(),
        );
    }
    Ok(parsed)
}

fn build_service_url(
    base_url: &str,
    route_name: &str,
    query: Option<BTreeMap<String, String>>,
    allow_public_network_endpoint: bool,
) -> Result<(String, String), String> {
    let route_path = service_api_route_path(route_name)
        .ok_or_else(|| format!("Unknown service API route: {route_name}"))?;
    let parsed_base = normalize_service_base_url(base_url, allow_public_network_endpoint)?;
    let mut url = parsed_base;
    url.set_path(route_path);
    if let Some(params) = query {
        {
            let mut pairs = url.query_pairs_mut();
            for (key, value) in params {
                pairs.append_pair(&key, &value);
            }
        }
    }
    Ok((url.to_string(), route_path.to_string()))
}

fn service_health_url(base_url: &str) -> Result<String, String> {
    let mut url = normalize_service_base_url(base_url, false)?;
    url.set_path("/health");
    url.set_query(None);
    Ok(url.to_string())
}

fn check_service_health(base_url: &str, api_token: &str) -> Result<(), String> {
    let url = service_health_url(base_url)?;
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .map_err(|exc| format!("Could not create health-check client: {exc}"))?;
    let mut request = client.get(url).header("Accept", "application/json");
    if !api_token.trim().is_empty() {
        request = request.bearer_auth(api_token.trim());
    }
    let response = request
        .send()
        .map_err(|exc| format!("Service health check failed: {exc}"))?;
    if response.status().is_success() {
        Ok(())
    } else {
        Err(format!(
            "Service health check returned HTTP {}",
            response.status().as_u16()
        ))
    }
}

fn managed_child_snapshot(state: &ServiceProcessState) -> (bool, Option<u32>) {
    let Ok(mut guard) = state.child.lock() else {
        return (false, None);
    };
    let Some(child) = guard.as_mut() else {
        return (false, None);
    };
    match child.try_wait() {
        Ok(None) => (true, Some(child.id())),
        Ok(Some(_)) | Err(_) => {
            *guard = None;
            (false, None)
        }
    }
}

fn push_candidate_ancestors(candidates: &mut Vec<PathBuf>, start: impl AsRef<Path>) {
    let start = start.as_ref();
    for ancestor in start.ancestors() {
        let root = ancestor.to_path_buf();
        if !candidates.iter().any(|item| item == &root) {
            candidates.push(root);
        }
    }
}

fn find_repo_root(app: &AppHandle) -> Option<PathBuf> {
    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Ok(current_dir) = env::current_dir() {
        push_candidate_ancestors(&mut candidates, current_dir);
    }
    if let Ok(current_exe) = env::current_exe() {
        if let Some(parent) = current_exe.parent() {
            push_candidate_ancestors(&mut candidates, parent);
        }
    }
    if let Ok(resource_dir) = app.path().resource_dir() {
        push_candidate_ancestors(&mut candidates, resource_dir);
    }
    candidates.into_iter().find(|root| {
        root.join("apps")
            .join("service-api")
            .join("main.py")
            .is_file()
    })
}

fn python_executable() -> String {
    env::var("TRADING_BOT_PYTHON")
        .or_else(|_| env::var("PYTHON"))
        .unwrap_or_else(|_| "python".to_string())
}

fn service_pythonpath(repo_root: &Path) -> String {
    let separator = if cfg!(windows) { ";" } else { ":" };
    let mut paths = vec![
        repo_root.to_string_lossy().to_string(),
        repo_root
            .join("Languages")
            .join("Python")
            .to_string_lossy()
            .to_string(),
    ];
    if let Ok(existing) = env::var("PYTHONPATH") {
        if !existing.trim().is_empty() {
            paths.push(existing);
        }
    }
    paths.join(separator)
}

fn wait_for_service_health(
    state: &ServiceProcessState,
    base_url: &str,
    api_token: &str,
) -> Result<(), String> {
    let mut last_error = String::new();
    for _ in 0..32 {
        match check_service_health(base_url, api_token) {
            Ok(()) => return Ok(()),
            Err(exc) => last_error = exc,
        }
        let (running, _) = managed_child_snapshot(state);
        if !running {
            return Err("Service process exited before /health became available.".to_string());
        }
        thread::sleep(Duration::from_millis(250));
    }
    Err(last_error)
}

#[tauri::command]
async fn service_api_request(
    base_url: String,
    api_token: String,
    route_name: String,
    method: String,
    payload: Option<Value>,
    query: Option<BTreeMap<String, String>>,
    allow_public_network_endpoint: bool,
) -> ServiceApiProxyResponse {
    let (url, route_path) =
        match build_service_url(&base_url, &route_name, query, allow_public_network_endpoint) {
            Ok(value) => value,
            Err(exc) => return response_error(&route_name, "", 0, exc),
        };
    let method = method.trim().to_uppercase();
    let timeout_secs = match route_name.as_str() {
        "llm_local_model_pull" => 3_600,
        "llm_local_model_delete" | "llm_local_model_start" => 120,
        _ => 8,
    };
    let client = match reqwest::Client::builder()
        .timeout(Duration::from_secs(timeout_secs))
        .build()
    {
        Ok(value) => value,
        Err(exc) => {
            return response_error(
                &route_name,
                &route_path,
                0,
                format!("Could not create HTTP client: {exc}"),
            );
        }
    };
    let mut request = match method.as_str() {
        "GET" => client.get(&url),
        "POST" => client.post(&url),
        "PATCH" => client.patch(&url),
        "PUT" => client.put(&url),
        _ => {
            return response_error(
                &route_name,
                &route_path,
                0,
                format!("Unsupported service API method: {method}"),
            );
        }
    }
    .header("Accept", "application/json");
    if !api_token.trim().is_empty() {
        request = request.bearer_auth(api_token.trim());
    }
    if matches!(method.as_str(), "POST" | "PATCH" | "PUT") {
        request = request.json(&payload.unwrap_or_else(|| json!({})));
    }
    let response = match request.send().await {
        Ok(value) => value,
        Err(exc) => {
            return response_error(
                &route_name,
                &route_path,
                0,
                format!("Service API request failed: {exc}"),
            );
        }
    };
    let status = response.status().as_u16();
    let text = match response.text().await {
        Ok(value) => value,
        Err(exc) => {
            return response_error(
                &route_name,
                &route_path,
                status,
                format!("Could not read service response: {exc}"),
            );
        }
    };
    let payload = if text.trim().is_empty() {
        json!({})
    } else {
        serde_json::from_str::<Value>(&text).unwrap_or_else(|_| json!({ "raw": text }))
    };
    let mut result = response_ok(&route_name, &route_path, status, payload);
    if !result.ok {
        let detail = result
            .payload
            .get("detail")
            .and_then(Value::as_str)
            .unwrap_or("Service API returned an error status.");
        result.error = detail.to_string();
    }
    result
}

#[tauri::command]
fn service_process_status(
    state: State<'_, ServiceProcessState>,
    host: String,
    port: u16,
    api_token: String,
) -> ServiceProcessResponse {
    let base_url = service_base_url(&host, port);
    let (running, pid) = managed_child_snapshot(&state);
    let healthy = check_service_health(&base_url, &api_token).is_ok();
    ServiceProcessResponse::ok(
        running || healthy,
        healthy,
        running,
        pid,
        base_url,
        if healthy {
            "Service API is reachable."
        } else if running {
            "Managed service process is running, but health is not ready."
        } else {
            "Service API is not running."
        },
    )
}

#[tauri::command]
fn start_service_api(
    app: AppHandle,
    state: State<'_, ServiceProcessState>,
    host: String,
    port: u16,
    api_token: String,
    load_config: bool,
) -> ServiceProcessResponse {
    let bind_host = normalize_bind_host(&host);
    let base_url = service_base_url(&bind_host, port);
    if !is_loopback_host(&bind_host) {
        return ServiceProcessResponse::err(
            false,
            false,
            None,
            base_url,
            "Tauri only auto-starts the local service on loopback hosts.",
        );
    }
    if check_service_health(&base_url, &api_token).is_ok() {
        let (running, pid) = managed_child_snapshot(&state);
        return ServiceProcessResponse::ok(
            true,
            true,
            running,
            pid,
            base_url,
            "Service API is already reachable.",
        );
    }
    let (already_running, pid) = managed_child_snapshot(&state);
    if already_running {
        match wait_for_service_health(&state, &base_url, &api_token) {
            Ok(()) => {
                return ServiceProcessResponse::ok(
                    true,
                    true,
                    true,
                    pid,
                    base_url,
                    "Managed service API is running.",
                );
            }
            Err(exc) => {
                return ServiceProcessResponse::err(true, true, pid, base_url, exc);
            }
        }
    }
    let Some(repo_root) = find_repo_root(&app) else {
        return ServiceProcessResponse::err(
            false,
            false,
            None,
            base_url,
            "Could not locate apps/service-api/main.py from the Tauri shell.",
        );
    };
    let service_script = repo_root.join("apps").join("service-api").join("main.py");
    let mut command = Command::new(python_executable());
    command
        .arg(service_script)
        .arg("--serve")
        .arg("--host")
        .arg(&bind_host)
        .arg("--port")
        .arg(port.to_string())
        .current_dir(&repo_root)
        .env("PYTHONPATH", service_pythonpath(&repo_root))
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    if !api_token.trim().is_empty() {
        command.arg("--api-token").arg(api_token.trim());
    }
    if load_config {
        command.arg("--load-config");
    }
    #[cfg(target_os = "windows")]
    command.creation_flags(CREATE_NO_WINDOW);

    let child = match command.spawn() {
        Ok(value) => value,
        Err(exc) => {
            return ServiceProcessResponse::err(
                false,
                false,
                None,
                base_url,
                format!("Could not launch Python service API: {exc}"),
            );
        }
    };
    let pid = Some(child.id());
    {
        let Ok(mut guard) = state.child.lock() else {
            return ServiceProcessResponse::err(
                true,
                true,
                pid,
                base_url,
                "Service process started, but Tauri state lock failed.",
            );
        };
        *guard = Some(child);
    }
    match wait_for_service_health(&state, &base_url, &api_token) {
        Ok(()) => ServiceProcessResponse::ok(
            true,
            true,
            true,
            pid,
            base_url,
            "Managed service API started.",
        ),
        Err(exc) => ServiceProcessResponse::err(true, true, pid, base_url, exc),
    }
}

#[tauri::command]
fn stop_service_api(
    state: State<'_, ServiceProcessState>,
    host: String,
    port: u16,
) -> ServiceProcessResponse {
    let base_url = service_base_url(&host, port);
    let Ok(mut guard) = state.child.lock() else {
        return ServiceProcessResponse::err(
            false,
            false,
            None,
            base_url,
            "Service process state lock failed.",
        );
    };
    let Some(mut child) = guard.take() else {
        return ServiceProcessResponse::ok(
            false,
            false,
            false,
            None,
            base_url,
            "No Tauri-managed service API process is running.",
        );
    };
    let pid = child.id();
    let kill_result = child.kill();
    let _ = child.wait();
    match kill_result {
        Ok(()) => ServiceProcessResponse::ok(
            false,
            false,
            true,
            Some(pid),
            base_url,
            "Managed service API stopped.",
        ),
        Err(exc) => ServiceProcessResponse::err(
            false,
            true,
            Some(pid),
            base_url,
            format!("Could not stop managed service API: {exc}"),
        ),
    }
}

fn main() {
    tauri::Builder::default()
        .manage(ServiceProcessState::default())
        .invoke_handler(tauri::generate_handler![
            service_api_request,
            service_process_status,
            start_service_api,
            stop_service_api
        ])
        .setup(|app| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.set_title(&app_banner("Tauri"));
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("failed to run Tauri desktop shell");
}
