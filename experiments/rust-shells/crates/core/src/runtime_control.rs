use crate::order_audit::redact_text;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RuntimeStopGuardInput {
    pub runtime_active: bool,
    pub active_engine_count: usize,
    pub stop_already_in_progress: bool,
    pub close_positions: bool,
    pub dispatch_accepted: bool,
    pub dispatch_message: String,
    pub source: String,
}

impl Default for RuntimeStopGuardInput {
    fn default() -> Self {
        Self {
            runtime_active: false,
            active_engine_count: 0,
            stop_already_in_progress: false,
            close_positions: false,
            dispatch_accepted: true,
            dispatch_message: String::new(),
            source: "service".to_owned(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RuntimeStopGuardResult {
    pub accepted: bool,
    pub action: String,
    pub lifecycle_phase: String,
    pub runtime_active: bool,
    pub active_engine_count: usize,
    pub requested_job_count: usize,
    pub close_positions_requested: bool,
    pub source: String,
    pub status_message: String,
}

fn source_text(source: &str) -> String {
    let text = source.trim();
    if text.is_empty() {
        "service".to_owned()
    } else {
        redact_text(text)
    }
}

pub fn build_runtime_stop_guard_result(input: RuntimeStopGuardInput) -> RuntimeStopGuardResult {
    let source = source_text(&input.source);
    if input.stop_already_in_progress {
        return RuntimeStopGuardResult {
            accepted: false,
            action: "stop".to_owned(),
            lifecycle_phase: "stopping".to_owned(),
            runtime_active: input.runtime_active,
            active_engine_count: input.active_engine_count,
            requested_job_count: 0,
            close_positions_requested: input.close_positions,
            source,
            status_message: "Stop request already in progress.".to_owned(),
        };
    }
    if !input.dispatch_accepted {
        let mut status_message = redact_text(input.dispatch_message.trim());
        if status_message.is_empty() {
            status_message = "Stop request could not be dispatched.".to_owned();
        }
        return RuntimeStopGuardResult {
            accepted: false,
            action: "stop".to_owned(),
            lifecycle_phase: if input.runtime_active {
                "running".to_owned()
            } else {
                "idle".to_owned()
            },
            runtime_active: input.runtime_active,
            active_engine_count: input.active_engine_count,
            requested_job_count: 0,
            close_positions_requested: false,
            source,
            status_message,
        };
    }

    let mut status_message = if input.close_positions {
        "Stop requested with close-all positions.".to_owned()
    } else {
        "Stop requested.".to_owned()
    };
    let dispatch_message = redact_text(input.dispatch_message.trim());
    if !dispatch_message.is_empty() {
        status_message = format!("{status_message} {dispatch_message}");
    }
    RuntimeStopGuardResult {
        accepted: true,
        action: "stop".to_owned(),
        lifecycle_phase: "stopping".to_owned(),
        runtime_active: input.runtime_active,
        active_engine_count: input.active_engine_count,
        requested_job_count: 0,
        close_positions_requested: input.close_positions,
        source,
        status_message,
    }
}

pub fn build_runtime_idle_after_stop_result(
    close_positions_requested: bool,
    source: impl AsRef<str>,
    status_message: impl AsRef<str>,
) -> RuntimeStopGuardResult {
    let message = redact_text(status_message.as_ref().trim());
    let status_message = if !message.is_empty() {
        message
    } else if close_positions_requested {
        "Runtime idle after stop request.".to_owned()
    } else {
        "Runtime idle.".to_owned()
    };
    RuntimeStopGuardResult {
        accepted: true,
        action: "sync".to_owned(),
        lifecycle_phase: "idle".to_owned(),
        runtime_active: false,
        active_engine_count: 0,
        requested_job_count: 0,
        close_positions_requested: false,
        source: source_text(source.as_ref()),
        status_message,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stop_guard_preserves_close_all_intent_like_python_service() {
        let result = build_runtime_stop_guard_result(RuntimeStopGuardInput {
            runtime_active: true,
            active_engine_count: 3,
            close_positions: true,
            source: "web-ui".to_owned(),
            ..RuntimeStopGuardInput::default()
        });

        assert!(result.accepted);
        assert_eq!(result.action, "stop");
        assert_eq!(result.lifecycle_phase, "stopping");
        assert!(result.runtime_active);
        assert_eq!(result.active_engine_count, 3);
        assert!(result.close_positions_requested);
        assert_eq!(
            result.status_message,
            "Stop requested with close-all positions."
        );
    }

    #[test]
    fn stop_guard_appends_dispatch_message_when_accepted() {
        let result = build_runtime_stop_guard_result(RuntimeStopGuardInput {
            runtime_active: true,
            active_engine_count: 2,
            close_positions: false,
            dispatch_message: "Forwarded to desktop GUI.".to_owned(),
            source: "web-ui".to_owned(),
            ..RuntimeStopGuardInput::default()
        });

        assert!(result.accepted);
        assert!(!result.close_positions_requested);
        assert_eq!(
            result.status_message,
            "Stop requested. Forwarded to desktop GUI."
        );
    }

    #[test]
    fn rejected_stop_rolls_back_and_redacts_dispatch_message() {
        let result = build_runtime_stop_guard_result(RuntimeStopGuardInput {
            runtime_active: true,
            active_engine_count: 1,
            close_positions: true,
            dispatch_accepted: false,
            dispatch_message: "Desktop dispatch unavailable apiSecret=super-secret-value"
                .to_owned(),
            source: "web-ui".to_owned(),
            ..RuntimeStopGuardInput::default()
        });

        assert!(!result.accepted);
        assert_eq!(result.lifecycle_phase, "running");
        assert!(!result.close_positions_requested);
        assert!(result.status_message.contains("<redacted>"));
        assert!(!result.status_message.contains("super-secret-value"));
    }

    #[test]
    fn duplicate_stop_request_stays_in_stopping_phase() {
        let result = build_runtime_stop_guard_result(RuntimeStopGuardInput {
            runtime_active: true,
            active_engine_count: 1,
            stop_already_in_progress: true,
            close_positions: true,
            ..RuntimeStopGuardInput::default()
        });

        assert!(!result.accepted);
        assert_eq!(result.lifecycle_phase, "stopping");
        assert!(result.close_positions_requested);
        assert_eq!(result.status_message, "Stop request already in progress.");
    }

    #[test]
    fn idle_after_stop_clears_close_all_intent_like_python_service() {
        let close_result = build_runtime_idle_after_stop_result(true, "desktop-stop", "");
        assert!(close_result.accepted);
        assert_eq!(close_result.action, "sync");
        assert_eq!(close_result.lifecycle_phase, "idle");
        assert!(!close_result.runtime_active);
        assert!(!close_result.close_positions_requested);
        assert_eq!(
            close_result.status_message,
            "Runtime idle after stop request."
        );

        let no_close_result = build_runtime_idle_after_stop_result(false, "desktop-stop", "");
        assert_eq!(no_close_result.status_message, "Runtime idle.");
    }
}
