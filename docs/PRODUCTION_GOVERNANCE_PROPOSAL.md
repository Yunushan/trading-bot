# Proposed repository and release governance

**Prepared:** 2026-09-23. **Observed source:** `8700725f4e76a49bd195d6d2ba99e3ff3c792b67` on `main`. This is a reviewable PRD-001 settings proposal, not evidence that the settings have been applied or tested.

## Observed state

- The public GitHub branch API reports `main` as `protected=false`; the effective branch-rules API and repository ruleset list return no rules. The latest observed CI, CodeQL and Supply Chain Security runs at this SHA succeeded, but successful checks do not enforce a merge policy.
- The public `production` environment response lists no protection rules and `can_admins_bypass=true`. The deployment workflow uses that environment, requires a protected semantic-version tag and published stable release, and checks an exact commit before rollout.
- `.github/CODEOWNERS` assigns all paths to `@Yunushan`. The public API does not reveal a second authorized reviewer. Administrator-only protection and secret-scanning settings could not be read with the available unauthenticated session; a repository administrator must export and verify them.

## Proposed controls for the first release scope

1. Create an **active `main` branch ruleset** requiring a pull request, at least one review by a person other than the author, dismissal of stale approvals after code changes, resolved conversations, and passing checks from the GitHub Actions app. Block direct pushes, force pushes and deletion. Require linear history if the maintainers use squash/rebase merges. Set no routine bypass; record a named, audited emergency procedure before enabling any exceptional bypass.
2. Initially require these observed, unconditional pull-request job names: `Workflow Lint`, `Python Quality`, `Web Dashboard Quality`, `Mobile Client Quality`, `Native C++ Smoke`, `Rust Smoke`, `Python Dependency Audit`, `Node Dependency Audit (apps/web-dashboard)`, `Node Dependency Audit (apps/mobile-client)`, `Rust Dependency Audit`, `Container Image Audit`, and all four `CodeQL (...)` checks. Also require the new `Secret Scan` CI job after its first pull-request run proves the exact check name. Confirm each exact name and GitHub Actions source on a new test pull request before saving the ruleset. Keep the `CI`, Supply Chain Security and CodeQL pull-request triggers unconditional for required jobs. Their push path filters do not determine whether a pull request check runs.
3. Add an **active release-tag ruleset** for `v*`: block update and deletion of an existing release tag, restrict creation to the approved release process, and keep the workflow's semantic-version and protected-ref checks. Document how a bad release is revoked and superseded; do not silently retarget a published tag.
4. Add `production` environment protection: named primary and backup release approvers, prevention of self-review, no administrator bypass, and deployment limited to approved protected release refs. Keep deployment credentials only in that protected environment. Assign an incident owner and a person authorized to invoke the rollback workflow.
5. Verify repository secret scanning and push protection in administrator settings, or implement a reviewed enforced scan. Export sanitized evidence of the final main/tag/environment settings and the named owners into the release acceptance packet.

The maintainer must identify a real reviewer and release approvers before setting review requirements; using the author as the only reviewer would either fail to enforce independent review or lock out normal changes. Risk policy, trading account, execution host and operating scope also remain operator decisions.

## Acceptance drill after authorization

1. Record the ruleset and environment export with the applied timestamp and effective rule IDs. Confirm a new pull request with a deliberately failing required check cannot merge and that a green, independently reviewed pull request can merge. Check a documentation-only pull request as well, so no required check remains pending because of a path filter.
2. Attempt a direct push, force push, and protected-tag update from a non-bypass account in a safe test setup; each must be denied. Test the approved release-tag creation path and confirm `github.ref_protected=true` in the release workflow.
3. Run a non-production deployment approval/rollback rehearsal with no production credentials or cluster mutation. Verify that a self-review and an unapproved ref cannot access the protected environment.

The settings change and drills need repository administrator access and an explicit operator decision. No setting was changed while preparing this proposal.

## GitHub behavior referenced

- [Required status checks and skipped workflows](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks)
- [Available repository ruleset controls](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)
- [Deployment review and self-review controls](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/review-deployments)
