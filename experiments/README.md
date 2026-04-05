# Experiments

This directory holds non-primary implementation workspaces that are useful for
re-platforming, native runtime experiments, and framework evaluation.

- `native-cpp/`: Qt/C++ desktop preview and native re-platforming path
- `rust-shells/`: Rust shared-core workspace plus desktop shell experiments

These trees are intentionally separated from the primary Python product and the
top-level `apps/` clients so the repository communicates production surfaces
versus experimental ones more clearly.
