# Support matrix and verification status

This matrix separates dated evidence from declared compatibility. **Unverified**
means no reproducible test record was collected for that environment; it is not
proof of incompatibility. Evidence was reviewed on 2026-10-08 UTC against
`adef5ff`. See [dated support evidence](support-evidence.md) for links and limits.

## Python and packaging

| Environment | Verification status | Evidence |
|---|---|---|
| Python 3.10, 3.11, 3.12 on Linux x86_64 | Unit tests and wheel CLI smoke checks passed | CI on 2026-10-08 UTC |
| Python 3.13 | Declared in package metadata; unverified here | No dated 3.13 run collected |
| Python < 3.10 | Not supported by package metadata | `requires-python = ">=3.10"` |
| Wheel and sdist build | Verified in CI and local audit | Source reports 1.3.0; release tag identity is separate |
| Current PyPI and Docker Hub tags | Unverified fresh-install state | Do not infer package version from a GitHub release tag |

## Operating systems and architectures

| Environment | Verification status |
|---|---|
| Ubuntu 24.04, x86_64 / linux/amd64 | Live Docker + kind smoke test passed |
| Other Linux distributions | Unverified live compatibility |
| Linux ARM64 | Unverified; current Docker workflow does not specify a multi-platform build |
| macOS Intel / Apple Silicon | Unverified; no dated run collected |
| Windows native / WSL2 | Unverified; no dated run collected |

## Containers and Kubernetes environments

| Environment | Verification status | Scope |
|---|---|---|
| Docker 28.0.4 + kind 0.23.0, Kubernetes 1.30.0 | Live smoke test passed | API access, HTML generation, doctor; no metrics-server |
| Kubernetes 1.27, 1.28, 1.29, other versions | Unverified | No dated run collected |
| Podman, containerd, CRI-O | Unverified | No dated application run collected |
| minikube, k3d/k3s, Docker Desktop Kubernetes | Unverified | No dated run collected |
| EKS, GKE, AKS, Rancher/RKE, OpenShift | Unverified | No dated managed-cluster run collected |
| Custom controllers / CRDs | Unverified | Read-only pod discovery does not establish arbitrary controller support |

The plan exporter emits patches for Deployments, StatefulSets, and DaemonSets.
Other workload kinds do not receive an executable patch. This is a source-code
boundary, not a claim that all three have been live-tested.

## Permissions and telemetry

| Scenario | Verification status |
|---|---|
| Broad read permissions in kind CI | Live API/report/doctor smoke evidence |
| Namespace Role + `namespace_filter` | Mocked collector/doctor regression tests; live Role deployment unverified |
| Restricted/denied resources | Mocked regression tests; live restricted identity unverified |
| Missing metrics-server | Live estimate-mode report and optional doctor warning verified |
| Fresh, missing, stale, and partial metrics samples | Mocked regression tests; measured workload sizing unverified in the collected live run |
| eBPF | Capability detection only; live probes are not implemented |

Read permissions are documented in [RBAC](rbac.md). `doctor` checks connection,
permissions and Metrics API availability; it does not establish every pod's
sample coverage or validate recommendations under representative load.

## Adding evidence

Record the UTC date, source SHA, package version, OS/architecture, Python,
Kubernetes version, identity/RBAC, metrics coverage, commands, exit codes, and
sanitized output or CI links. Separate a passing smoke check from workload/load
validation. Use the [release testing procedure](release-testing.md), and mark
skipped environments with a reason instead of filling them with PASS.
