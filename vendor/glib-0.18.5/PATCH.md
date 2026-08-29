# glib 0.18.5 security backport

This directory is the published `glib 0.18.5` crates.io package, copied from
the Cargo registry cache without generated cache metadata. Its original
crates.io archive has SHA-256:

```text
233daaf6e83ae6a12a52055f568f9d7cf4671dabb78ff9560ab6da230ce00ee5
```

The only source change is the upstream fix for the unsound C out-parameter in
`src/variant_iter.rs`: the local pointer is mutable and `g_variant_get_child`
receives `&mut p`. The upstream fix was merged in gtk-rs-core commit
`05dff0ee696f9bcd8617cd48c4b812d046d440cb` (PR #1343).

The package version remains `0.18.5`; this is an auditable local backport, not
a claim that an upstream patched 0.18 release exists. Remove this directory
and the corresponding Cargo patch when the resolved Tauri/GTK dependency path
uses `glib >=0.20` or a released GTK4-compatible stack.
