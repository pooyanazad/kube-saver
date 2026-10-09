---
title: Dated support test evidence
description: Inspect recorded source revisions, Python checks, wheel smoke tests, and Docker kind evidence with
  explicit limits on measured and platform coverage.
---

# Dated support evidence

Evidence reviewed on **2026-10-08 and 2026-10-09 UTC**. These records describe the tested
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

## Independent PR review: 2026-10-09 UTC

The updated heads were reviewed against unchanged main `adef5ff`:

| Draft | Reviewed head | Verified result |
|---|---|---|
| Runtime #32 | `4284cfc98de98be7adc277364f801a13df42e7ea` | [CI 37896829917](https://github.com/pooyanazad/kube-saver/actions/runs/37896829917): lint, Python 3.10/3.11/3.12 tests, build, wheel and kind Docker smoke passed; Docker finished 07:06:06 UTC; publishing skipped |
| Release #33 | `98ee792854056f48e7d78884b0d4a86d8dcd2085` | [CI 37896499168](https://github.com/pooyanazad/kube-saver/actions/runs/37896499168): configured lint/tests/wheel matrix, Docker smoke and version/checksum validation passed; Docker finished 07:02:08 UTC; publishing skipped |

Local Python 3.12.14 checks passed 366 tests for #32 and 342 for #33, plus
Ruff and mypy. Local repositories exercised lightweight/annotated tags,
missing tags, and a moved remote tag. Tampered checksums, renamed/mismatched
artifacts, unsafe versions, invalid metrics, replica request skew, explicit
apply-context selection, and shell argument quoting have regression coverage.
The release workflow passed actionlint 1.7.12 and Bash syntax checks for all
31 rendered shell steps. The exported smoke image was uploaded in hosted CI;
GitHub/Docker publishing commands were deliberately not executed.

Local detached merge simulations of #32 then #33 and #33 then #32 both
completed without conflicts, produced the same tree, and passed 387 tests,
Ruff, and mypy. This verifies source compatibility, not a live combined release.
No measured workload sizing, load history, or managed-cluster evidence was
added by this review. The live kind smoke remains estimate-mode evidence.

## Still unverified

No live evidence was collected for macOS, ARM64, Windows/WSL2, alternate
container runtimes, managed-cloud clusters, live restricted Roles, measured
workload recommendations, or historical load safety. Prior unsupported test
claims have been removed from the [support matrix](support-matrix.md).
