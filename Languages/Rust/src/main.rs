use trading_bot_core::{app_banner, supported_frameworks};

fn main() {
    println!("{}", app_banner("Rust workspace"));
    println!("Supported desktop shells:");
    for framework in supported_frameworks() {
        println!("- {framework}");
    }
}
