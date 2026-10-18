# gtk3-macros 0.18.2 macro error helper backport

This directory preserves the published crates.io `gtk3-macros 0.18.2` package
and its MIT license. The original archive SHA-256 is:

```text
52ff3c5b21f14f0736fed6dcfc0bfb4225ebf5725f3c0209edeec181e4d73e9d
```

The local changes replace only the `proc_macro_error` source imports and the
`proc-macro-error` dependency in both Cargo manifests. The replacement is the
published `proc-macro-error3 =3.1.1`, with default features disabled and
`syn2-error` enabled. All macro branches, generated tokens, attributes, messages,
and upstream tests remain unchanged. The original extra blank license EOF line
is removed to satisfy the repository whitespace gate; glib-macros also trims
one documentation-only trailing-whitespace line. Package identities stay truthful.

The replacement archive SHA-256 is
`8f0d4471b3436c22106b21913b1dda531558918ae9b7ec55d58aa84b43552233`;
its attribute companion has SHA-256
`9e564d14133360e1ae169ffde5da25881b5fa47261665b8e5713c212c27799da`.
Publication source: [upstream commit](https://github.com/gamma0987/proc-macro-error3/commit/0f0e21bb2a46509c923b87459c6be314bc0cabb5).

This removes the unmaintained error helper from Tauri's GTK3 dependency path;
it does not claim that GTK3 itself is maintained. Qualification uses stable
Rust 1.95.0. The fork requires an explicit feature for nightly diagnostics;
nightly behavior is not qualified here. Native Linux original/candidate GLib
and GTK consumer results are recorded in `docs/PRODUCTION_HANDOFF.md`.

Remove this backport and its Cargo patch when the resolved upstream macro
packages no longer require the unmaintained helper, or Tauri adopts GTK4.
