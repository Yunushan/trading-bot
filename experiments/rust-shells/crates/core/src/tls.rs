use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Duration;

use anyhow::{Context, Result, anyhow, bail};
use reqwest::blocking::{Client, ClientBuilder};
use rustls::ClientConfig;
use rustls::RootCertStore;
use rustls_pki_types::CertificateDer;
use rustls_pki_types::pem::PemObject;
use tungstenite::Connector;

/// Optional PEM CA bundle used when an operator's network adds a trusted
/// inspection root that is not present in the process/system root store.
///
/// The bundle is additive: system roots remain trusted, certificate hostname
/// verification remains enabled, and an unreadable/invalid bundle is fatal.
pub(crate) const EXTRA_CA_BUNDLE_ENV: &str = "TRADING_BOT_RUST_CA_BUNDLE";
const COMPATIBLE_CA_BUNDLE_ENVS: [&str; 3] =
    ["SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"];

pub(crate) fn build_http_client(timeout: Duration, user_agent: &str) -> Result<Client> {
    let mut builder =
        add_native_root_certificates(Client::builder().timeout(timeout).user_agent(user_agent))?;
    if let Some(path) = configured_extra_ca_bundle()? {
        for certificate in load_pem_certificates(&path)? {
            let certificate =
                reqwest::Certificate::from_der(certificate.as_ref()).with_context(|| {
                    format!("parse extra Rust CA certificate from {}", path.display())
                })?;
            builder = builder.add_root_certificate(certificate);
        }
    }
    builder.build().context("build Rust HTTP client")
}

fn add_native_root_certificates(mut builder: ClientBuilder) -> Result<ClientBuilder> {
    // Keep REST and WebSocket trust stores aligned. The reqwest feature also
    // loads native roots, but adding them explicitly makes the behavior stable
    // across Windows, macOS, and Linux certificate-store implementations.
    let native = rustls_native_certs::load_native_certs();
    for certificate in native.certs {
        let certificate = reqwest::Certificate::from_der(certificate.as_ref())
            .context("parse native Rust CA certificate")?;
        builder = builder.add_root_certificate(certificate);
    }
    Ok(builder)
}

pub(crate) fn websocket_connector_from_env() -> Result<Option<Connector>> {
    let Some(path) = configured_extra_ca_bundle()? else {
        return Ok(None);
    };
    let extra_certificates = load_pem_certificates(&path)?;
    let mut root_store = RootCertStore::empty();
    let native = rustls_native_certs::load_native_certs();
    let (native_added, _) = root_store.add_parsable_certificates(native.certs);
    for certificate in extra_certificates {
        root_store
            .add(certificate)
            .map_err(|error| anyhow!(error))
            .with_context(|| format!("add extra Rust CA certificate from {}", path.display()))?;
    }
    if native_added == 0 && root_store.is_empty() {
        bail!("no usable system or configured CA certificates available for Rust WebSocket TLS");
    }
    let config = ClientConfig::builder()
        .with_root_certificates(root_store)
        .with_no_client_auth();
    Ok(Some(Connector::Rustls(Arc::new(config))))
}

fn configured_extra_ca_bundle() -> Result<Option<PathBuf>> {
    for variable in std::iter::once(EXTRA_CA_BUNDLE_ENV).chain(COMPATIBLE_CA_BUNDLE_ENVS) {
        let Some(value) = std::env::var_os(variable) else {
            continue;
        };
        if value.to_string_lossy().trim().is_empty() {
            continue;
        }
        return Ok(Some(PathBuf::from(value)));
    }
    Ok(None)
}

fn load_pem_certificates(path: &Path) -> Result<Vec<CertificateDer<'static>>> {
    let pem =
        fs::read(path).with_context(|| format!("open extra Rust CA bundle {}", path.display()))?;
    parse_pem_certificates(&pem)
        .with_context(|| format!("read extra Rust CA bundle {}", path.display()))
}

fn parse_pem_certificates(pem: &[u8]) -> Result<Vec<CertificateDer<'static>>> {
    let certificates = CertificateDer::pem_slice_iter(pem)
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("parse PEM CA bundle")?;
    if certificates.is_empty() {
        bail!("PEM CA bundle does not contain an X.509 certificate");
    }
    Ok(certificates)
}

#[cfg(test)]
mod tests {
    use super::{EXTRA_CA_BUNDLE_ENV, parse_pem_certificates};

    #[test]
    fn extra_ca_bundle_name_is_stable_for_operator_configuration() {
        assert_eq!(EXTRA_CA_BUNDLE_ENV, "TRADING_BOT_RUST_CA_BUNDLE");
    }

    #[test]
    fn empty_extra_ca_bundle_is_rejected() {
        let error = parse_pem_certificates(&[]).expect_err("empty bundle must fail");
        assert!(error.to_string().contains("X.509 certificate"));
    }
}
