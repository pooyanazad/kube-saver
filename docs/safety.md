# Safety & trust

This document explains what kube-saver will never do, how it protects your workloads, and what you need to know before running it in a production environment.

---

## Design principles

1. **Read-only by default**, kube-saver never changes anything in your cluster unless you explicitly run the apply script from a PR plan. Even then, you review the script first.
2. **No required hosted backend**, scans contact your Kubernetes API. Kubeconfig credential plugins may also contact identity providers. Reports are written locally and can contain internal cluster names.
3. **Degrades safely**, if a runtime source is unavailable, kube-saver falls back to the next source instead of crashing.
4. **Review required**, current-sample heuristics produce candidates, not guarantees of workload safety (see below).

---

## What kube-saver will never do

- Auto-apply resource changes to your cluster
- Modify any Kubernetes object without your explicit action
- Send data to a third-party service or API
- Require a cloud account, token, or hosted backend
- Crash because metrics-server is unavailable
- Generate a right-sizing recommendation from request-only estimates

---

## Recommendation safety

The right-sizing engine applies these guardrails to the current metrics sample:

| Guardrail | What it prevents |
|---|---|
| **Measured usage required** | A missing sample for a collected sibling suppresses the workload plan |
| **Current-sample headroom** | CPU suggestions use 1.5× observed usage; memory uses 1.2× |
| **Configured resource floors** | CLI defaults: at least 100m CPU, 128Mi memory, and half of each current request |
| **Single-container workloads** | Pods with sidecars are skipped because pod metrics cannot be split safely |
| **Protected namespaces and exclusions** | Configured namespaces, labels, and annotations suppress recommendations |

The tool uses a current snapshot, not historical peak usage. Review recommendations against workload bursts and service objectives before applying the generated script.

Confidence labels come from utilization ratios, not statistical intervals; plans
include low, medium, and high confidence candidates. Workload consolidation takes
the largest suggestion across all collected sibling samples, including busy
replicas that would not generate their own candidate. A missing sample,
multi-container sibling, or excluded sibling suppresses the workload plan.
Values round upward to whole millicores and MiB to preserve sample headroom.

CPU × 1.5 and memory × 1.2 are fixed sample multipliers. Configured absolute
minimums apply in every mode. In normal mode, `prod_cpu_floor_ratio` and
`prod_memory_floor_ratio` apply to every eligible workload; no production
namespace is inferred. `aggressive_mode` skips those relative floors only.
The engine does not automatically protect StatefulSets or workloads with PVCs.
Configure exclusions for sensitive workloads. Even a complete scan is a current
snapshot, not proof that future replicas or future peaks are covered.

`pr-plan` creates local files, not a GitHub PR. Executing the patch script contacts
the Kubernetes API and can trigger a workload rollout. For GitOps, translate
reviewed changes into your managed manifests.

If you want to suppress recommendations for specific workloads, use the exclusion config:

```yaml
exclude_labels:
  app.kubernetes.io/part-of: database
exclude_annotations:
  kube-saver.io/ignore: "true"
```

---

<a id="rbac"></a>

## RBAC, minimum required permissions

kube-saver needs only **list** and **get** on a small set of resources. Here is the minimal RBAC manifest:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: kube-saver-reader
rules:
  - apiGroups: [""]
    resources: ["pods", "nodes", "namespaces"]
    verbs: ["list", "get"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets", "statefulsets", "daemonsets"]
    verbs: ["list", "get"]
  - apiGroups: ["metrics.k8s.io"]
    resources: ["pods", "nodes"]
    verbs: ["list", "get"]
```

To use it:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: kube-saver-reader-binding
subjects:
  - kind: ServiceAccount
    name: kube-saver
    namespace: kube-saver
roleRef:
  kind: ClusterRole
  name: kube-saver-reader
  apiGroup: rbac.authorization.k8s.io
```

For namespace-scoped access, use a `Role` / `RoleBinding` in each target namespace and set `namespace_filter` to those names. See [RBAC permissions](rbac.md#namespace-scoped-deployment).

> **Note:** The `metrics.k8s.io` group is only needed if metrics-server is running. kube-saver works without it, it just falls back to estimates.

---

## HTTP API

The built-in HTTP server (`kube-saver serve`) is:

- **Loopback-only by default** (`127.0.0.1`)
- **Read-only**, no mutation endpoints
- **No authentication**, because it is not designed to be exposed

If you need to expose it in a shared environment, put it behind a reverse proxy with auth and TLS. Do not bind it to `0.0.0.0` directly.

---

## Data sources and accuracy

kube-saver displays which runtime source it is using in every view. The accuracy tradeoff is:

| Source | Accuracy | When you get it |
|---|---|---|
| metrics-server | Good, cluster-aggregated CPU/memory | metrics-server running |
| Estimates | Request-based, not measured usage | metrics-server unavailable |

Falling back to estimates is not a bug. The TUI shows which source is active,
and estimated samples never produce right-sizing recommendations. eBPF live
collection is not implemented in this release.

---

## Secrets and sensitive data

kube-saver never logs or exports:

- Kubeconfig contents
- Tokens or credentials
- Pod environment variables
- Secret objects or their data

The `doctor` command reports the kubeconfig path, active context, and server version, but does not print credentials. Reports and plans contain namespace, pod, and workload names; review them before sharing or committing them.

---

## See also

- [Architecture](architecture.md)
- [Self-contained outputs](self-contained.md)
- [Troubleshooting](troubleshooting.md)
