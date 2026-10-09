# kube-saver v2.0.0

Kubernetes CPU and memory cost estimates, a terminal dashboard, local HTML/JSON
reports, and reviewable resource-change plans.

## Upgrade requirements

- Generated apply scripts require `KUBE_SAVER_APPLY_CONTEXT` and pass it to every
  patch. Review the target cluster before executing a script. Scripts stop on
  failure; earlier successful patches are not rolled back.
- A fully failed pod scan exits with code `4`. Partial scans retain usable data
  and label degraded results; automation must handle warnings and incomplete
  coverage.
- Context, namespace selection, exclusions, and custom pricing configuration now
  affect CLI scans as documented. Review existing configuration before upgrading.
- Recommendation guardrails can suppress candidates or change proposed values.
  Estimated, excluded, and multi-container sibling samples prevent actionable
  workload recommendations. Current samples do not establish historical peaks.
- Package and CLI version are now `2.0.0`. Historical `v1.8.0` artifacts reported
  `1.3.0`; old tags and releases are preserved.

## Improvements

- Runtime metrics collection, namespace/pod metric identities, and local JSON
  report output.
- Invalid, stale, future-dated, or incomplete metrics fall back to estimates.
  The default maximum sample age is 300 seconds; estimates do not produce
  actionable right-sizing recommendations.
- Namespace-limited scans and doctor checks, safer notification behavior when
  coverage is incomplete, and patches targeting named containers.
- Local review plans do not modify workloads or open GitHub pull requests.
- Artifact versions and checksums are validated before explicit release dispatch.
- [Searchable documentation](https://pooyanazad.github.io/kube-saver/) covers
  pricing, missing metrics, RBAC, recommendation safety, and GitOps review.

## Installation

Download `kube_saver-2.0.0-py3-none-any.whl` and `SHA256SUMS.txt` from this release.
Check the wheel's SHA256 against its entry in `SHA256SUMS.txt`, then install in a
Python 3.10+ virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install ./kube_saver-2.0.0-py3-none-any.whl
kube-saver version
```

PyPI availability has not been established. This release process publishes
GitHub wheel/source/checksum assets and then Docker Hub `v2.0.0` and `latest`
tags; it does not publish to PyPI. Docker publication is complete only when its
workflow job succeeds.

## Verification and limitations

[Main CI at b2f0fdf](https://github.com/pooyanazad/kube-saver/actions/runs/37931841554)
passed on 2026-10-09 UTC: Python 3.10–3.12 tests and wheel checks, Ruff, mypy,
build/checksum validation, and a Linux/amd64 kind report smoke test. The Python
3.12 log records 387 passing tests. The container reports version 2.0.0 against
Kubernetes 1.30.0; missing metrics-server verified request-based estimate mode.
The publication run must pass these checks again at its exact tagged commit.

Managed-cluster, live namespace Role, and representative-load sizing tests were
not run during release preparation because no such cluster access was available.
See [dated evidence](https://pooyanazad.github.io/kube-saver/support-evidence/).

Costs and savings are modeled estimates, not cloud billing. Review candidate
changes under representative load. Live scans require Kubernetes API connectivity
and credentials; generated HTML reports can be viewed offline. eBPF live probes
are not implemented. No performance or realized-savings benchmark is claimed.
