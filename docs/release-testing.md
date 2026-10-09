# Pre-release environment testing

kube-saver needs to be tested against three different cluster environments
before each release. This guide explains what to test, how to set it up, and
how to record the results.

## Why three environments

| Environment        | What it catches                                           |
| ------------------ | --------------------------------------------------------- |
| Local cluster      | fast iteration, broken assumptions, edge cases            |
| Managed cloud      | API access, RBAC, configured pricing, network quirks     |
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
docker build -t kube-saver:test .
mkdir -p reports
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e KUBECONFIG=/tmp/kubeconfig \
  -v "$HOME/.kube/config:/tmp/kubeconfig:ro" \
  -v "$PWD/reports:/out" \
  kube-saver:test report -o /out/report.html
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
- `kube-saver notify --dir /tmp/notify` produces a summary; alerts additionally require complete measured coverage, no partial scan, and waste above the threshold

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

`doctor` should pass required checks. Optional missing-metrics warnings permit
estimate mode, but do not count as measured-workload validation. Fix required
failures before proceeding.

Run the verification:

```bash
./scripts/verify-install.sh
```

What to confirm beyond the local checks:

- API server reachable without timing out
- For measured sizing, metrics-server provides fresh samples for the test workloads; record coverage. Missing metrics verify estimate mode only.
- Modeled costs match configured rates and resource inputs; they are not cloud invoices.
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

Create `/tmp/restricted.kubeconfig` with the cluster endpoint and trusted CA, a
user that reads `/tmp/kube-saver-token` through `tokenFile`, and a current context
selecting that user. Do not retain administrator credentials in this file.
Tokens expire; generate a fresh one when needed. This file must exist before the
commands below; recording a mocked RBAC test is not a live Role test.

```bash
KUBECONFIG=/tmp/restricted.kubeconfig kube-saver doctor
KUBECONFIG=/tmp/restricted.kubeconfig ./scripts/verify-install.sh
```

What to confirm:

- `doctor` reports no permission errors for the selected namespace
- `report` exits 4 without writing an empty report when no namespace is readable
- `report` errors gracefully if we deny pod collection (`list pods`)
- The error message tells the user which RBAC verb is missing
- No crash, no stack trace, no silent failure

## Recording results

After running all three, post a comment on the release PR with the format:

```
### Pre-release test results

| Environment        | Result | Notes                          |
| ------------------ | ------ | ------------------------------ |
| kind               | PASS   | full report generated          |
| AWS EKS (us-east)  | NOT RUN | no cluster access; no claim   |
| restricted RBAC    | PASS   | doctor reports no missing verbs|
```

If anything fails, do not tag the release until it's fixed.

## What "PASS" actually means

- Every check in `verify-install.sh` is green
- `kube-saver doctor` passes required checks; optional warnings are recorded
- The generated HTML report opens in a browser without errors
- Resource inputs and modeled costs match the configured rates; coverage and limits are recorded
- No new exceptions appear on stderr during the CLI checks

## When to skip an environment

If the cloud environment is unavailable (account issue, billing, etc.),
post a note in the release PR saying which environment was skipped and why.
Do not silently skip.

Each record should include the UTC date, source SHA, artifact version, platform,
cluster version, RBAC identity, metrics coverage, commands and exit codes. The
table above is a reporting template, not a claim that those runs occurred.
See [dated support evidence](support-evidence.md) for collected results.
