# Release QA: vX.Y.Z

- Release tag: vX.Y.Z
- Source revision: 0000000000000000000000000000000000000000
- Completed on: YYYY-MM-DD
- Operator: Full name or accountable team
- Outcome: approved

## Completed Checks

- [ ] Desktop visual flow: Record the desktop shell, configuration, strategy controls, charts, positions, and error-state result.
- [ ] Service API flow: Record `/readyz`, authenticated request, invalid-token, and unavailable-service result.
- [ ] LLM/local-model flow: Record disabled, cloud-token-missing, and local-model-unavailable behavior without exposing any secret.
- [ ] Release package: Record clean-machine install/start, provenance/SBOM verification, and uninstall result for every published asset family.

## Evidence

Link the relevant CI runs, packaged-asset checks, screenshots, and issue IDs here.
