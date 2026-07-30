# RBAC & permissions

The minimum set of Kubernetes API permissions kube-saver needs to operate.

---

## Minimum required permissions

kube-saver is **read-only**. It needs `list` and `get` on these resources:

| API group          | Resources                                              | Verbs        |
|--------------------|--------------------------------------------------------|--------------|
| `""` (core)        | `pods`, `nodes`, `namespaces`                          | `list`, `get`|
| `apps`             | `deployments`, `replicasets`, `statefulsets`, `daemonsets` | `list`, `get`|
| `metrics.k8s.io`   | `pods`, `nodes`                                        | `list`, `get`|

> The `metrics.k8s.io` permission is optional. If metrics-server is unavailable, kube-saver falls back to request-based estimates automatically.

---

## Cluster-scoped deployment

Use a `ClusterRole` when you want a single kube-saver instance to scan the entire cluster.

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
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: kube-saver-reader
subjects:
  - kind: ServiceAccount
    name: kube-saver
    namespace: kube-saver
roleRef:
  kind: ClusterRole
  name: kube-saver-reader
  apiGroup: rbac.authorization.k8s.io
```

Apply it:

```bash
kubectl apply -f manifests/cluster-scoped.yaml
```

---

## Namespace-scoped deployment

Use a `Role` + `RoleBinding` per namespace when you want to limit kube-saver to specific namespaces.

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: kube-saver
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: kube-saver
  namespace: kube-saver
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: kube-saver-reader
  namespace: MY-NAMESPACE
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["list", "get"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets", "statefulsets", "daemonsets"]
    verbs: ["list", "get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: kube-saver-reader
  namespace: MY-NAMESPACE
subjects:
  - kind: ServiceAccount
    name: kube-saver
    namespace: kube-saver
roleRef:
  kind: Role
  name: kube-saver-reader
  apiGroup: rbac.authorization.k8s.io
```

> Replace `MY-NAMESPACE` with each target namespace. The `nodes` and `namespaces` resources are cluster-scoped, so namespace-scoped scans cannot report node-level or cluster-wide totals.

---

## Verifying permissions

Run `kube-saver doctor` to check whether your current context has the required access:

```bash
kube-saver doctor
```

It runs `SelfSubjectAccessReview` checks and reports exactly which permissions are missing.

---

## See also

- [Safety & trust](safety.md) — what kube-saver recommends (and what it never does)
- [Getting started](getting-started.md) — step-by-step for EKS, kind, kubeconfig
- [Troubleshooting](troubleshooting.md) — common permission errors
