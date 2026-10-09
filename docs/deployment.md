---
title: Containers and CI deployment
description: Run kube-saver with mounted kubeconfig, in-cluster credentials, persistent report output, and CI artifacts
  while understanding container authentication limits.
---

# Running kube-saver inside a container

Three options for running kube-saver with the official Docker image, depending on where your kubeconfig lives.

The image is at `pooyanazad/kube-saver` on Docker Hub. The container runs as an unprivileged `kube-saver` user.

---

## Option 1: Mount your local kubeconfig

The simplest case: you have a kubeconfig on your machine and you run kube-saver locally in a container.

```bash
mkdir -p reports
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e KUBECONFIG=/tmp/kubeconfig \
  -v "$HOME/.kube/config:/tmp/kubeconfig:ro" \
  -v "$PWD/reports:/out" \
  pooyanazad/kube-saver:latest \
  report -o /out/report.html

docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e KUBECONFIG=/tmp/kubeconfig \
  -v "$HOME/.kube/config:/tmp/kubeconfig:ro" \
  pooyanazad/kube-saver:latest \
  doctor
```

The first command preserves `reports/report.html` on the host after `--rm`
removes the container. On Linux/macOS, `--user` matches the host directory owner;
`KUBECONFIG` is explicit because the user override can change home discovery.
The doctor example uses the same UID and explicit path so it can read a
host kubeconfig with owner-only permissions.

Kubeconfigs that reference certificate files need those files mounted too.
Exec credential plugins such as `aws`, `gcloud`, or `kubelogin` must be available
inside the container; the base image does not install them. Use a suitable image
or run natively. Local cluster endpoints on `127.0.0.1` also need a network path
from the container (the CI smoke test uses host networking on Linux).

> Mount kubeconfig with `:ro` (read-only). Credential plugins may need access to
> other files or writable caches; inspect their requirements separately.

### Mounting multiple kubeconfig files

If you use a merged kubeconfig or split contexts across files:

```bash
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$HOME/.kube/config:/tmp/kubeconfig:ro" \
  -v "$HOME/.kube/extra-config:/tmp/extra-kubeconfig:ro" \
  -e KUBECONFIG=/tmp/kubeconfig:/tmp/extra-kubeconfig \
  pooyanazad/kube-saver:latest \
  doctor
```

---

## Option 2: In-cluster auth (running as a pod)

If kube-saver itself runs inside a Kubernetes pod, it picks up the service account token mounted at `/var/run/secrets/kubernetes.io/serviceaccount/`. No kubeconfig is needed.

### Apply the RBAC

Use the cluster-scoped manifest:

```bash
kubectl apply -f manifests/cluster-scoped-rbac.yaml
```

For a namespace-scoped role, replace `MY-NAMESPACE` in the manifest, apply it, and set the same name in `.kube-saver.yaml` as `namespace_filter`. The config file must be available inside the container at `/app/.kube-saver.yaml`:

```bash
kubectl apply -f manifests/namespace-scoped-rbac.yaml
```

### Run as a Job

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: kube-saver-report
  namespace: kube-saver
spec:
  template:
    spec:
      serviceAccountName: kube-saver
      securityContext:
        fsGroup: 2000
      restartPolicy: Never
      containers:
        - name: kube-saver
          image: pooyanazad/kube-saver:latest
          args: ["report", "-o", "/out/report.html"]
          volumeMounts:
            - name: out
              mountPath: /out
      volumes:
        - name: out
          emptyDir: {}
```

The image's built-in user is non-root and the entrypoint is `kube-saver`.
`fsGroup` grants that process access to the mounted output volume. The example
uses ephemeral `emptyDir` storage; it does not export the report off the pod.
Use persistent storage or an artifact-copy step for retention. For namespace
Roles, the Job namespace and service account must match the RoleBinding.

### Cross-cloud in-cluster auth

On EKS, GKE, AKS, or a local cluster, in-cluster access uses the mounted
Kubernetes service account token plus Kubernetes RBAC. Cloud workload identity
annotations grant cloud API access when configured; they do not replace the
RoleBinding required here. The client uses an available kubeconfig first and
otherwise loads in-cluster credentials. An explicit `KUBECONFIG` must reference
an existing file.

---

## Option 3: CI / GitHub Actions

A native CI example, after setting up Python 3.10+ with `actions/setup-python`.
Here `KUBECONFIG_YAML` is a secret containing kubeconfig **contents**;
`KUBECONFIG` must point to the file written on the runner:

```yaml
- name: Prepare kubeconfig
  env:
    KUBECONFIG_YAML: ${{ secrets.KUBECONFIG }}
  run: |
    umask 077
    printf '%s' "$KUBECONFIG_YAML" > "$RUNNER_TEMP/kubeconfig"
    echo "KUBECONFIG=$RUNNER_TEMP/kubeconfig" >> "$GITHUB_ENV"

- name: Install kube-saver
  run: python -m pip install kube-saver

- name: Generate report
  run: kube-saver report -o cost-report.html
```

The runner still needs network access, valid credentials and read permissions.
If your kubeconfig uses an exec plugin, install it on the runner. Archive the
report using your CI artifact mechanism after reviewing who can access it.

---

## Troubleshooting in containers

| Symptom | Likely cause | Fix |
|---|---|---|
| `kubeconfig not found` | Mount path wrong | Mount to `/home/kube-saver/.kube/config:ro` |
| `Forbidden: pods is forbidden` | Service account missing RBAC | Apply the manifests from `manifests/` |
| Doctor prints 401/403 | Token expired or wrong context | Refresh the kubeconfig and retry |
| Empty metrics | metrics-server not running | Install metrics-server, or accept estimates |
| TUI flickers / no TTY | Missing `-it` flags | Add `-it` for the TUI command only |

---

## See also

- [RBAC permissions](rbac.md) — what to grant your service account
- [Getting started](getting-started.md) — local and managed cluster setup
- [Support matrix](support-matrix.md) — container runtime compatibility
