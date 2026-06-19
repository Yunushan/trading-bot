use trading_bot_core::{
    app_banner, cpp_entire_python_app_contract_parity_ready,
    cpp_entire_python_app_parity_ready, native_full_python_app_parity_ready,
    native_python_app_contract_parity_ready, native_python_app_parity_domains,
    rust_entire_python_app_contract_parity_ready, rust_entire_python_app_parity_ready,
    rust_native_runtime_capabilities, rust_native_trading_runtime_ready, supported_frameworks,
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
    println!(
        "Python app contract/catalog parity ready: {}",
        native_python_app_contract_parity_ready()
    );
    println!(
        "C++ Python app contract/catalog parity ready: {}",
        cpp_entire_python_app_contract_parity_ready()
    );
    println!(
        "Rust Python app contract/catalog parity ready: {}",
        rust_entire_python_app_contract_parity_ready()
    );
    println!(
        "Full standalone Python app parity ready: {}",
        native_full_python_app_parity_ready()
    );
    println!(
        "C++ full standalone Python app parity ready: {}",
        cpp_entire_python_app_parity_ready()
    );
    println!(
        "Rust full standalone Python app parity ready: {}",
        rust_entire_python_app_parity_ready()
    );
    println!("Python app contract parity audit:");
    for domain in native_python_app_parity_domains() {
        println!(
            "- {}: {} | C++ parity: {} | Rust parity: {}",
            domain.key, domain.title, domain.cpp_full_parity, domain.rust_full_parity
        );
    }
    println!("Native runtime capability gaps:");
    for capability in rust_native_runtime_capabilities() {
        println!(
            "- {}: {} | Rust: {}",
            capability.key, capability.title, capability.rust_status
        );
    }
}
