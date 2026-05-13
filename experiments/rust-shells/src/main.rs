use trading_bot_core::{
    app_banner, rust_native_runtime_capabilities, rust_native_trading_runtime_ready,
    supported_frameworks,
};

fn main() {
    println!("{}", app_banner("Rust workspace"));
    println!("Supported desktop shells:");
    for framework in supported_frameworks() {
        println!("- {framework}");
    }
    println!(
        "Native Rust trading runtime ready: {}",
        rust_native_trading_runtime_ready()
    );
    println!("Native runtime capability gaps:");
    for capability in rust_native_runtime_capabilities() {
        println!(
            "- {}: {} | Rust: {}",
            capability.key, capability.title, capability.rust_status
        );
    }
}
