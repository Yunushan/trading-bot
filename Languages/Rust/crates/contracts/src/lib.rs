use serde::{Deserialize, Serialize};

pub const WORKSPACE_NAME: &str = "Trading Bot Rust Workspace";

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct AppIdentity {
    pub workspace: String,
    pub shell: String,
}

impl AppIdentity {
    pub fn new(shell: impl Into<String>) -> Self {
        Self {
            workspace: WORKSPACE_NAME.to_string(),
            shell: shell.into(),
        }
    }
}
