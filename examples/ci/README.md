# CI examples

Two GitHub Actions workflow templates for a project that wants SUTH to gate
its PRs — copy both into *that project's* `.github/workflows/`, not suth's own
(suth has no preview-deploy URL of its own to audit).

- **`suth-baseline.yml`** — runs on push to `main`, audits main's stable URL,
  and publishes the resulting `session_id` as the `SUTH_BASELINE_SESSION_ID`
  repo variable.
- **`suth-pr-gate.yml`** — runs on every PR, audits that PR's preview deploy,
  compares against the stored baseline via `compare_runs`, and fails the
  check if the friction score regresses past `SUTH_REGRESSION_THRESHOLD`
  (default 5).

Both assume:
- `suth_config.json` lives at the target repo's root with a `ci` environment
  (see `suth-test-app/suth_config.json` for a working example).
- A `SUTH_OBJECTIVE` repo variable holding the objective text to test.
- A `SPECIFIC_API_KEY` secret for the shared `specific.dev` project these
  workflows provision Postgres/storage from.

Replace the `git clone .../suth.git` step with whatever your org actually
uses to distribute the harness (a published package, a git submodule, an
internal registry) once it has one — Phase 1–3 built it as a standalone repo
with no packaging/distribution story yet.
