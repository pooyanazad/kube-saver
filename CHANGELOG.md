# Changelog

## 2.0.0 — unreleased

This release candidate packages the runtime safety improvements and documentation
now present on `main`. Publication remains subject to owner approval.

### Upgrade notes

- Generated apply scripts require `KUBE_SAVER_APPLY_CONTEXT` and pass that context
  to every patch command. Set it to the reviewed target cluster before running a
  script. Scripts stop on the first failure; earlier patches are not rolled back.
- A fully failed pod scan exits with analysis-error code `4` instead of producing
  an empty successful report. Partial scans retain usable data, warn on stderr,
  and identify degraded results in HTML and JSON. Check automation that consumes
  exit codes or assumes every report is complete.
- CLI and TUI recommendations use the configured minimums and relative floors.
  Estimated, excluded, or multi-container sibling samples suppress workload
  recommendations. Differing sibling requests suppress the affected resource;
  busy collected siblings constrain consolidated recommendations. Expect fewer
  candidates or different proposed values than older builds.
- CLI scans honor configured context, namespace selection, exclusions, provider,
  and custom pricing rates. Previously ignored configuration can now affect
  selected workloads and modeled costs; review your configuration before use.
- The source version is now `2.0.0`. Historical GitHub releases, including
  `v1.8.0`, contained artifacts reporting `1.3.0`. Historical tags and releases
  remain unchanged; identify an installed build with `kube-saver version`.

### Improvements

- CLI reports collect runtime metrics and can also write JSON with `report --json`.
  Metrics are keyed by namespace and pod name. Missing, stale, invalid, incomplete,
  or future-dated samples fall back to estimates; the default maximum sample age
  is 300 seconds. Estimated samples do not produce right-sizing recommendations.
- Namespace-limited scans and doctor checks work with namespace Role permissions.
  Doctor reports missing metrics-server; API availability does not establish
  fresh metrics coverage for every workload.
- Spike notifications are suppressed when telemetry or the scan is incomplete.
- Resource patches target named containers. Review plans remain local files;
  generating a plan neither changes Kubernetes workloads nor opens a GitHub PR.
- Release checks require agreeing source, wheel, sdist, CLI, and tag versions,
  verify checksums, and bind publication to the tested commit. Release and Docker
  publication require an explicit manual main-branch dispatch.
- Searchable documentation is available at
  <https://pooyanazad.github.io/kube-saver/>, including pricing assumptions,
  missing-metrics interpretation, recommendation safety, RBAC, and GitOps review.

### Limits and verification

Costs and savings are modeled CPU/memory estimates, not cloud billing data.
Recommendations use current samples, not historical peaks or percentiles; review
them against representative load before changing resources. eBPF live collection
is not implemented. No hosted kube-saver or billing account is required, but live
scans need Kubernetes API connectivity and valid credentials.

CI exercises Python 3.10–3.12, wheel installation, and a Linux/amd64 container
against kind. The kind report smoke test does not establish measured right-sizing
coverage or support for every managed cluster. See the dated
[support evidence](docs/support-evidence.md) for verified scope and untested
environments; no new performance or cloud-billing benchmark is claimed.

The publishing workflow creates a GitHub release with wheel/sdist/checksum assets
and then pushes Docker Hub version and `latest` tags. It does not publish to PyPI.
