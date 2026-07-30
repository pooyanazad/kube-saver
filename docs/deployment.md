# Running kube-saver inside a container

Three options for running kube-saver with the official Docker image, depending on where your kubeconfig lives.

The image is at `pooyanazad/kube-saver` on Docker Hub. The `kube-saver` user runs as UID 65532 inside the container.

---

## Option 1: Mount your local kubeconfig

The simplest case: you have a kubeconfig on your machine and you run kube-saver locally in a container.

```bash
docker run --rm \
  -v "$HOME/.kube/config:/home/kube-saver/.kube/config:ro" \
  pooyanazad/kube-saver:latest \
  report -o /tmp/report.html

docker run --rm \
  -v "$HOME/.kube/config:/home/kube-saver/.kube/config:ro" \
  pooyanazad/kube-saver:latest \
  doctor
```

The mount path `/home/kube-saver/.kube/config` matches the image's default `KUBECONFIG` location.

> Always mount `:ro` (read-only). kube-saver never modifies your kubeconfig.

### Mounting multiple kubeconfig files

If you use a merged kubeconfig or split contexts across files:

```bash
docker run --rm \
  -v "$HOME/.kube/config:/home/kube-saver/.kube/config:ro" \
  -v "$HOME/.kube/extra-config:/home/kube-saver/.kube/extra-config:ro" \
  -e KUBECONFIG=/home/kube-saver/.kube/config:/home/kube-saver/.kube/extra-config \
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

Or the namespace-scoped one for limited access:

```bash
kubectl apply -f manifests/namespace-scoped-rbac.yaml -n my-app
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

The image's built-in user is non-root and the entrypoint is `kube-saver`. No special security context is required beyond the service account.

### Cross-cloud in-cluster auth

| Provider              | Auth source                                                          |
|-----------------------|----------------------------------------------------------------------|
| EKS (IRSA)            | Service account annotated with `eks.amazonaws.com/role-arn`          |
| GKE (Workload Identity) | Service account annotated with `iam.gke.io/gcp-service-account`     |
| AKS (Workload Identity) | Service account annotated with `azure.workload.identity/client-id`  |
| On-prem / kind        | Static token in the pod's service account mount                       |

If you already have a kubeconfig on disk, you can also pass it via `KUBECONFIG` to override in-cluster auth.

---

## Option 3: CI / GitHub Actions

A typical CI step that runs `kube-saver report` against a test cluster:

```yaml
- name: Run kube-saver
  env:
    KUBECONFIG: ${{ secrets.KUBECONFIG }}
  run: |
    docker run --rm \
      -v "$KUBECONFIG:/home/kube-saver/.kube/config:ro" \
      -v "$PWD:/out" \
      pooyanazad/kube-saver:latest \
      report -o /out/cost-report.html
```

Or install from PyPI and run natively:

```yaml
- name: Install kube-saver
  run: pip install kube-saver

- name: Generate report
  env:
    KUBECONFIG: ${{ secrets.KUBECONFIG }}
  run: kube-saver report -o cost-report.html
```

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