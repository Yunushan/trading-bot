use crate::order_audit::redact_text;

pub const SERVICE_TERMINAL_COMMAND_TYPE: &str = "service-command";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ServiceLogEvent {
    pub sequence_id: u64,
    pub level: String,
    pub message: String,
    pub source: String,
    pub generated_at: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ServiceTerminalCommandResult {
    pub accepted: bool,
    pub command: String,
    pub exit_code: i32,
    pub output: String,
    pub source: String,
    pub created_at: String,
    pub command_type: &'static str,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RustLogsTerminalDiagnosticsBoundary {
    pub framework: &'static str,
    pub service_log_behavior: &'static str,
    pub terminal_behavior: &'static str,
    pub operational_owner: &'static str,
}

pub const RUST_LOGS_TERMINAL_DIAGNOSTICS_BOUNDARIES: &[RustLogsTerminalDiagnosticsBoundary] = &[
    RustLogsTerminalDiagnosticsBoundary {
        framework: "Tauri",
        service_log_behavior: "Fetches and formats canonical Python Service API /logs events.",
        terminal_behavior: "Delegates controlled terminal commands to the Python Service API terminal_run route.",
        operational_owner: "Python Service API",
    },
];

pub fn build_service_log_event(
    message: impl AsRef<str>,
    source: impl AsRef<str>,
    level: impl AsRef<str>,
    sequence_id: i64,
    generated_at: impl AsRef<str>,
) -> ServiceLogEvent {
    let level = level.as_ref().trim().to_lowercase();
    ServiceLogEvent {
        sequence_id: sequence_id.max(0) as u64,
        level: if level.is_empty() {
            "info".to_owned()
        } else {
            level
        },
        message: redact_text(message.as_ref()),
        source: normalized_source(source.as_ref(), "service"),
        generated_at: normalized_timestamp(generated_at.as_ref()),
    }
}

pub fn build_service_terminal_command_result(
    accepted: bool,
    command: impl AsRef<str>,
    output: impl AsRef<str>,
    source: impl AsRef<str>,
    exit_code: i32,
    created_at: impl AsRef<str>,
) -> ServiceTerminalCommandResult {
    ServiceTerminalCommandResult {
        accepted,
        command: redact_text(command.as_ref().trim()),
        exit_code,
        output: redact_text(output.as_ref()),
        source: normalized_source(source.as_ref(), "terminal"),
        created_at: normalized_timestamp(created_at.as_ref()),
        command_type: SERVICE_TERMINAL_COMMAND_TYPE,
    }
}

pub fn format_service_log_line(event: &ServiceLogEvent) -> String {
    format!(
        "{} [{}] {}: {}",
        event.generated_at,
        event.level.to_uppercase(),
        event.source,
        event.message
    )
    .trim()
    .to_owned()
}

fn normalized_source(value: &str, fallback: &str) -> String {
    let text = value.trim();
    if text.is_empty() {
        fallback.to_owned()
    } else {
        redact_text(text)
    }
}

fn normalized_timestamp(value: &str) -> String {
    let text = value.trim();
    if text.is_empty() {
        "1970-01-01T00:00:00+00:00".to_owned()
    } else {
        text.to_owned()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn service_log_event_matches_python_schema_and_redacts() {
        let event = build_service_log_event(
            "Connector failed with api_secret=super-secret-value",
            "service api_key=super-secret-value",
            "WARNING",
            -7,
            "2026-06-18T12:10:00+00:00",
        );

        assert_eq!(event.sequence_id, 0);
        assert_eq!(event.level, "warning");
        assert!(event.message.contains("<redacted>"));
        assert!(!event.message.contains("super-secret-value"));
        assert!(event.source.contains("<redacted>"));
        assert!(format_service_log_line(&event).contains("[WARNING]"));
    }

    #[test]
    fn terminal_result_matches_python_shape_and_redacts() {
        let result = build_service_terminal_command_result(
            true,
            "status api_key=super-secret-value",
            "Bearer super-secret-value\nstate=ready",
            "terminal token=super-secret-value",
            0,
            "2026-06-18T12:10:00+00:00",
        );

        assert!(result.accepted);
        assert_eq!(result.command_type, SERVICE_TERMINAL_COMMAND_TYPE);
        assert!(result.command.contains("<redacted>"));
        assert!(result.output.contains("Bearer <redacted>"));
        assert!(!result.source.contains("super-secret-value"));
    }

    #[test]
    fn tauri_shell_claims_terminal_delegation() {
        let tauri = RUST_LOGS_TERMINAL_DIAGNOSTICS_BOUNDARIES
            .iter()
            .find(|item| item.framework == "Tauri")
            .expect("tauri boundary");
        assert!(tauri.terminal_behavior.contains("terminal_run"));
        assert_eq!(RUST_LOGS_TERMINAL_DIAGNOSTICS_BOUNDARIES.len(), 1);
    }
}
