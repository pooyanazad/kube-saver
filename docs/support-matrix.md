# Support matrix

This page documents what kube-saver supports today. If you are running something
not listed here, it will probably still work — this is what we have actually
tested.

## Project

| Component        | Supported                                       |
| ---------------- | ----------------------------------------------- |
| Latest version   | see [GitHub releases](https://github.com/pooyanazad/kube-saver/releases) |
| License          | MIT                                             |
| Distribution     | PyPI (wheel + sdist), Docker Hub (`pooyanazad/kube-saver`) |
| Release cadence  | as needed — no fixed schedule                   |

## Python

| Version | Supported | Notes                          |
| ------- | --------- | ------------------------------ |
| 3.12    | yes       | primary development target     |
| 3.11    | yes       | tested in CI                   |
| 3.10    | yes       | tested in CI                   |
| < 3.10  | no        | `requires-python = ">=3.10"`   |

## Operating systems

| OS                  | Supported | Notes                                          |
| ------------------- | --------- | ---------------------------------------------- |
| Linux (x86_64)      | yes       | primary development and runtime target         |
| Linux (arm64)       | yes       | Docker image built for both architectures      |
| macOS (x86_64)      | yes       | works on developer machines                    |
| macOS (arm64)       | yes       | works on Apple Silicon                         |
| Windows (x86_64)    | partial   | works in WSL2; native Windows not yet tested   |

## Container runtimes (for the Docker image)

| Runtime       | Supported |
| ------------- | --------- |
| Docker        | yes       |
| Podman        | yes       |
| containerd    | yes       |
| CRI-O         | yes       |

## CPU architectures

| Architecture | Supported | Notes                                  |
| ------------- | --------- | -------------------------------------- |
| linux/amd64   | yes       | primary                                |
| linux/arm64   | yes       | built and pushed by CI                 |
| darwin/amd64  | yes       | local install only                     |
| darwin/arm64  | yes       | local install only                     |

## Kubernetes

| Component                                | Supported                    |
| ---------------------------------------- | ---------------------------- |
| Kubernetes API server (read-only)        | yes                          |
| `metrics-server` (for actual usage)      | yes — required for real numbers |
| eBPF runtime data (KubeScape-style)      | optional — improves accuracy  |
| CRDs (any kind)                          | yes — kube-saver is read-only  |
| Server-side apply                        | not used                      |

### API server versions tested

| Version | Status    |
| ------- | --------- |
| 1.30    | tested    |
| 1.29    | tested    |
| 1.28    | tested    |
| 1.27    | tested    |
| < 1.27  | not tested — probably works but not verified |

## Cluster types

| Type                                           | Tested    |
| ---------------------------------------------- | --------- |
| `kind` (local)                                 | yes       |
| `minikube`                                     | yes       |
| `k3d` / `k3s`                                  | yes       |
| Docker Desktop built-in cluster                | yes       |
| AWS EKS                                        | partial   |
| GCP GKE                                        | partial   |
| Azure AKS                                      | not yet   |
| Rancher / RKE                                  | not yet   |
| OpenShift                                      | not yet   |

"Partial" means kube-saver ran successfully against the API but only one
test pass was performed. Please report issues if you find a real cluster
type that breaks.

## RBAC environments

kube-saver needs read access to the API. Tested against:

| RBAC scenario                                | Status    |
| -------------------------------------------- | --------- |
| Cluster-admin (no restrictions)              | works     |
| Read-only cluster role                       | works     |
| Namespace-scoped read role                   | works     |
| Tightly restricted (specific verbs only)     | works — `doctor` reports missing verbs |

For exact RBAC requirements, see [docs/safety.md](safety.md#read-only-rbac-recipe).

## Runtime data sources

kube-saver picks the best available source automatically.

| Source          | When used                            | Accuracy      |
| --------------- | ------------------------------------ | ------------- |
| eBPF            | if available and supported by kernel | highest       |
| metrics-server  | if eBPF is not available             | high          |
| Estimates only  | if no metrics-server                 | rough — based on requests, not usage |

## How to verify your environment

Run `kube-saver doctor` (or `python -m kube_saver.cli doctor`) to check:

- kubeconfig file is readable
- context exists and is reachable
- cluster API server is reachable
- required RBAC permissions are present
- metrics-server is available (for real numbers)
- current Python and kube-saver version

`doctor` is non-destructive — it only reads cluster metadata and exits.

## Reporting unsupported configurations

If you run kube-saver on a combination not listed here and it works, please
open an issue or pull request so we can add it. Same if it doesn't work —
that is more important to know.

## Pre-release testing

Before each release, kube-saver is tested against three cluster environments:
local, managed cloud, and restricted RBAC. See
[Release testing](release-testing.md) for the procedure.