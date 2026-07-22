# Safety & trust

This document explains what kube-saver will never do, how it protects your workloads, and what you need to know before running it in a production environment.

---

## Design principles

1. **Read-only by default** — kube-saver never changes anything in your cluster unless you explicitly run the apply script from a PR plan. Even then, you review the script first.
2. **No data leaves your machine** — no telemetry, no analytics, no hosted service, no network calls other than to your Kubernetes API.
3. **Degrades safely** — if a runtime source is unavailable, kube-saver falls back to the next source instead of crashing.
4. **Recommends conservatively** — the recommendation engine avoids unsafe suggestions by design (see below).

---

## What kube-saver will never do

- Auto-apply resource changes to your cluster
- Modify any Kubernetes object without your explicit action
- Send data to a third-party service or API
- Require a cloud account, token, or hosted backend
- Crash because metrics-server is unavailable
- Recommend a resource value below what your pod is currently using in production

---

## Recommendation safety

The right-sizing engine applies these guardrails:

| Guardrail | What it prevents |
|---|---|
| **Floor: never below current usage** | Recommendations never suggest a value lower than the pod's peak observed usage |
| **Headroom buffer** | A configurable safety margin is added to observed usage (default: 20%) |
| **Stateful workload detection** | StatefulSets and pods with PVCs get a larger safety margin |
| **Critical namespace protection** | Namespaces matching your `critical_namespaces` config list get a larger buffer |
| **Minimum resource floor** | CPU and memory recommendations are clamped to minimums (50m CPU, 64Mi memory) |
| **Confidence score** | Every recommendation has a confidence level — only high-confidence ones appear in PR plans |

These guardrails are not optional. They are baked into the recommendation engine and cannot be disabled in config.

If you want to suppress recommendations for specific workloads, use the exclusion config:

```yaml
exclude_labels:
  - app.kubernetes.io/part-of: database
exclude_annotations:
  - kube-saver.io/ignore: "true"
```

---

## RBAC — minimum required permissions

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
    namespace: kube-system
roleRef:
  kind: ClusterRole
  name: kube-saver-reader
  apiGroup: rbac.authorization.k8s.io
```

For namespace-scoped access, replace `ClusterRole` / `ClusterRoleBinding` with `Role` / `RoleBinding` in each target namespace.

> **Note:** The `metrics.k8s.io` group is only needed if metrics-server is running. kube-saver works without it — it just falls back to estimates.

---

## HTTP API

The built-in HTTP server (`kube-saver serve`) is:

- **Loopback-only by default** (`127.0.0.1`)
- **Read-only** — no mutation endpoints
- **No authentication** — because it is not designed to be exposed

If you need to expose it in a shared environment, put it behind a reverse proxy with auth and TLS. Do not bind it to `0.0.0.0` directly.

---

## Data sources and accuracy

kube-saver displays which runtime source it is using in every view. The accuracy tradeoff is:

| Source | Accuracy | When you get it |
|---|---|---|
| eBPF | Highest — kernel-level, per-container CPU | BCC installed, root, host kernel access |
| metrics-server | Good — cluster-aggregated CPU/memory | metrics-server running |
| Estimates | Conservative — request-based only | Neither of the above available |

Falling back to estimates is not a bug. The TUI and reports always tell you which source is active so you can judge how much to trust the numbers.

---

## Secrets and sensitive data

kube-saver never logs or exports:

- Kubeconfig contents
- Tokens or credentials
- Pod environment variables
- Secret objects or their data

The `doctor` command redacts all connection metadata. The config dump command (`kube-saver config --show`) redacts sensitive fields before printing.

---

## See also

- [Architecture](architecture.md)
- [Self-contained outputs](self-contained.md)
- [Troubleshooting](troubleshooting.md)
