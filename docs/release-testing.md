# Pre-release environment testing

kube-saver needs to be tested against three different cluster environments
before each release. This guide explains what to test, how to set it up, and
how to record the results.

## Why three environments

| Environment        | What it catches                                           |
| ------------------ | --------------------------------------------------------- |
| Local cluster      | fast iteration, broken assumptions, edge cases            |
| Managed cloud      | real API server, real RBAC, real pricing, network quirks  |
| Restricted RBAC    | what happens when permissions are not what we expect      |

If kube-saver only ever ran against `kind` with cluster-admin, we would ship
broken or surprising behavior to real users. Three environments catches that.

## 1. Local cluster

Use any of:

- `kind create cluster --name kube-saver-test`
- `minikube start --profile kube-saver-test`
- `k3d cluster create kube-saver-test`
- Docker Desktop's built-in cluster

Install:

```bash
pip install kube-saver
```

Or test the wheel directly:

```bash
pip install dist/kube_saver-*.whl
```

Or test the Docker image:

```bash
docker pull pooyanazad/kube-saver:latest
docker run --rm -v $HOME/.kube/config:/home/kube/.kube/config:ro \
  pooyanazad/kube-saver:latest report -o /tmp/report.html
```

Run the full verification:

```bash
./scripts/verify-install.sh
```

What to confirm:

- `verify-install.sh` exits 0
- `kube-saver tui` launches and renders without errors
- `kube-saver report -o /tmp/report.html` produces a report > 1KB
- `kube-saver report --json /tmp/report.json` is valid JSON
- `kube-saver pr-plan --dir /tmp/pr` produces patches when measured usage supports recommendations
- `kube-saver notify --dir /tmp/notify` produces a summary, and an alert when measured waste exceeds the threshold

## 2. Managed cloud cluster

Pick one of AWS EKS, GCP GKE, or Azure AKS. This is the closest we get to a
real production environment.

```bash
# Example: AWS EKS
aws eks update-kubeconfig --region us-east-1 --name production-test
kubectl get nodes
```

Install kube-saver as you would for a real operator:

```bash
pip install kube-saver
kube-saver doctor
```

`doctor` should report all-green. If any check fails, fix it before going
further.

Run the verification:

```bash
./scripts/verify-install.sh
```

What to confirm beyond the local checks:

- API server reachable without timing out
- `metrics-server` is installed and reporting real numbers (otherwise kube-saver falls back to estimates, that's fine, just confirm it)
- Real cost numbers appear in the report (not all zeros)
- Recommendations make sense for the workloads running there

Clean up any test namespaces you created. Do not leave `kube-saver` running
in production accidentally.

## 3. Restricted RBAC environment

This is the most likely place for surprises. Real users do not run as
cluster-admin, so we should not either.

Use `manifests/namespace-scoped-rbac.yaml` with `MY-NAMESPACE` replaced by the test namespace. Set the same name under `namespace_filter` in `.kube-saver.yaml`. Apply it locally on `kind`:

```bash
kubectl apply -f manifests/namespace-scoped-rbac.yaml
kubectl create token kube-saver -n MY-NAMESPACE > /tmp/kube-saver-token
```

Use the restricted context:

```bash
KUBECONFIG=/tmp/restricted.kubeconfig kube-saver doctor
KUBECONFIG=/tmp/restricted.kubeconfig ./scripts/verify-install.sh
```

What to confirm:

- `doctor` reports no permission errors for the selected namespace
- `report` exits 4 without writing an empty report when no namespace is readable
- `report` errors gracefully if we deny a specific resource (`get pods`)
- The error message tells the user which RBAC verb is missing
- No crash, no stack trace, no silent failure

## Recording results

After running all three, post a comment on the release PR with the format:

```
### Pre-release test results

| Environment        | Result | Notes                          |
| ------------------ | ------ | ------------------------------ |
| kind               | PASS   | full report generated          |
| AWS EKS (us-east)  | PASS   | real pricing, 7 namespaces     |
| restricted RBAC    | PASS   | doctor reports no missing verbs|
```

If anything fails, do not tag the release until it's fixed.

## What "PASS" actually means

- Every check in `verify-install.sh` is green
- `kube-saver doctor` reports all-green on at least one environment
- The generated HTML report opens in a browser without errors
- A real cluster's cost numbers look right (sanity check, not a gold master)
- No new exceptions appear on stderr during the CLI checks

## When to skip an environment

If the cloud environment is unavailable (account issue, billing, etc.),
post a note in the release PR saying which environment was skipped and why.
Do not silently skip.
