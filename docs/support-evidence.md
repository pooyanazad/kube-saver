# Dated support evidence

Evidence reviewed on **2026-10-08 UTC**. These records describe the tested
commit, not every future release or platform. Logs may expire; retain sanitized
artifacts when conducting future tests.

## Latest main: adef5ff

[CI run 37856985522](https://github.com/pooyanazad/kube-saver/actions/runs/37856985522)
completed successfully at 2026-10-08 23:03:15 UTC for
`adef5ff8f14037567584cbce16b8e75feed3df69`.

| Check | Dated result | Primary record |
|---|---|---|
| Unit suite, Python 3.10 / 3.11 / 3.12 | Passed; 3.12 log reports 321 tests | [3.10](https://github.com/pooyanazad/kube-saver/actions/runs/37856985522/job/113583416163), [3.11](https://github.com/pooyanazad/kube-saver/actions/runs/37856985522/job/113583416459), [3.12](https://github.com/pooyanazad/kube-saver/actions/runs/37856985522/job/113583416312) |
| Wheel CLI smoke, Python 3.10.22 / 3.11.17 / 3.12.15 | Passed; version/help and graceful missing-kubeconfig checks | [3.10](https://github.com/pooyanazad/kube-saver/actions/runs/37856985522/job/113583637808), [3.11](https://github.com/pooyanazad/kube-saver/actions/runs/37856985522/job/113583637806), [3.12](https://github.com/pooyanazad/kube-saver/actions/runs/37856985522/job/113583637732) |
| Docker build and live kind report/doctor | Passed, 23:03:14 UTC | [Docker job](https://github.com/pooyanazad/kube-saver/actions/runs/37856985522/job/113583637673) |

The Docker log records Ubuntu 24.04.5 LTS x86_64, Docker 28.0.4, kind 0.23.0,
`kindest/node:v1.30.0`, API server 1.30.0, and CLI `kube-saver 1.3.0`.
It used host networking and a host-user override to write a bind-mounted report.
The generated HTML was 3,458 bytes. Size is a smoke check, not a quality or
performance benchmark.

Metrics-server returned HTTP 404; doctor reported an optional warning and all
required checks passed. This demonstrates API access and estimate-mode report
creation, not measured sizing, meaningful workload savings, interactive TUI
behavior, the revised Job/fsGroup example, or namespace Role authorization.

## Audit fixes: local checks

On 2026-10-08 UTC, Python 3.12.14 checks for runtime draft
[#32](https://github.com/pooyanazad/kube-saver/pull/32) passed 336 tests, Ruff and
mypy (38 source files). The final built wheel was compared byte-for-byte with
all runtime Python source files. Release draft
[#33](https://github.com/pooyanazad/kube-saver/pull/33) passed 328 tests, Ruff and
mypy (39 files), plus matching/mismatching checks using real wheel/sdist artifacts
and an installed-wheel CLI.

These local tests use mocks for Kubernetes interactions. No Docker, kubectl,
kind, or managed-cluster access was available in the audit environment. PR CI
results must be assessed separately at the actual draft commit.

Hosted CI was then verified for both draft commits on 2026-10-08 UTC:

| Draft | Checked head SHA | Result and scope |
|---|---|---|
| Runtime #32 | `53e561a8beef8c7991ab76bd3800a4ed52546025` | [CI 37858854506](https://github.com/pooyanazad/kube-saver/actions/runs/37858854506): lint/tests on the configured Python matrix, wheel checks, and kind Docker smoke passed; last smoke job completed 23:22:34 UTC |
| Release #33 | `549090d74fe037a3fe90d3691be520f67dfc6873` | [CI 37859289333](https://github.com/pooyanazad/kube-saver/actions/runs/37859289333): lint/tests, wheel/kind smoke and release-check passed; last smoke job completed 23:27:00 UTC; publishing jobs skipped |

Applying the runtime, release, and documentation patches together locally also
passed 343 tests, Ruff, and mypy (39 files) with no patch conflicts. This is a
combined working-tree check, not a deployed release or live load test.

## Still unverified

No live evidence was collected for macOS, ARM64, Windows/WSL2, alternate
container runtimes, managed-cloud clusters, live restricted Roles, measured
workload recommendations, or historical load safety. Prior unsupported test
claims have been removed from the [support matrix](support-matrix.md).
