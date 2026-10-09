# Getting started

This guide walks you from a fresh install to your first kube-saver output on the four most common cluster types.

Requires Python 3.10+ and a reachable Kubernetes cluster with read permissions.
Setup time depends on cluster access, credentials, and metrics availability.

---

## 1. Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install kube-saver
```

From source (recommended for development):

```bash
git clone https://github.com/pooyanazad/kube-saver.git
cd kube-saver
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Install metrics-server in the cluster for measured CPU and memory usage. Without
it, kube-saver shows request-based estimates and does not generate actionable
right-sizing recommendations. eBPF capability detection is experimental; live
eBPF probes are not implemented in this release.

---

## 2. Validate your connection

Before running a full scan, verify kube-saver can reach your cluster and has the permissions it needs:

```bash
kube-saver doctor
```

`doctor` checks kubeconfig, context, cluster reachability, required RBAC, and
Metrics API availability. Missing metrics are optional warnings: request-based
estimates can still run. A passing check does not guarantee fresh samples for
every pod. See [CLI reference](cli-reference.md#kube-saver-doctor) and
[Troubleshooting](troubleshooting.md).

If scans use a configured context, pass that same name to `doctor --context`:

```bash
KUBE_SAVER_CONTEXT=staging-cluster kube-saver doctor --context staging-cluster
```

`doctor --context` overrides the configured context. Without that option, doctor
uses `KUBE_SAVER_CONTEXT` or `kubeconfig_context`, then the kubeconfig current context.

---

## 3. Run by environment

### Local cluster, kind / minikube / Docker Desktop

```bash
# Make sure your local cluster is running
kubectl cluster-info

# Launch the TUI
kube-saver
```

To try it locally, use any Kubernetes cluster with at least one workload that sets CPU and memory requests. Install metrics-server to see measured waste and right-sizing recommendations.

### AWS EKS

```bash
aws eks update-kubeconfig --name my-cluster --region us-east-1
kube-saver
```

When launched inside a pod, kube-saver can use the mounted Kubernetes service
account token. The service account needs Kubernetes RBAC read permissions; an
AWS IAM role alone does not grant those permissions.

### Generic kubeconfig

```bash
export KUBECONFIG=/path/to/kubeconfig
kube-saver
```

If your kubeconfig has multiple contexts, pass the one you want:

```bash
KUBE_SAVER_CONTEXT=staging-cluster kube-saver
```

### Restricted / read-only RBAC

You only need **list** and **get** permissions on a small set of resources. See [Safety & trust](safety.md#rbac) for the exact YAML.

---

## 4. Your first output

The fastest path to a real, shareable artifact:

```bash
# Self-contained HTML report (open it in any browser)
kube-saver report -o cost-report.html
# Open cost-report.html in your browser
```

The HTML file has no external assets, no CDN, and no JavaScript dependencies, it works offline, in an email attachment, and in a CI artifact.

If you want a TUI session:

```bash
# Key bindings:
#   1         namespace overview (default)
#   2         cost breakdown
#   3         recommendations
#   enter     drill into selected namespace
#   /         search / filter
#   r         refresh
#   q         quit
kube-saver
```

If metrics-server is unavailable, the cost figures represent an upper bound based on requests. They are not measured savings, and no right-sizing recommendations or spike alert is issued from those estimates.

If you want a PR-ready plan:

```bash
kube-saver pr-plan -d ./pr-files
ls ./pr-files
#   summary.md          human-readable summary
#   apply-patches.sh    ready-to-run patch script (does not auto-apply)
#   review.txt          every recommended change with reasoning
```

---

## 5. Daily / CI use

Add kube-saver to a cron job or CI pipeline:

```bash
# Daily Markdown summary; optional spike alert with complete measured coverage
kube-saver notify -d ./alerts --threshold 250
```

```bash
# JSON output for pipelines
kube-saver report -o report.html --json report.json
```

For a CI artifact with self-contained HTML:

```yaml
- name: Generate cost report
  run: |
    pip install kube-saver
    kube-saver report -o cost-report.html
- name: Upload
  uses: actions/upload-artifact@v4
  with:
    name: cost-report
    path: cost-report.html
```

---

## Next steps

- [Cost model and FAQ](faq.md), interpret estimates and recommendation limits
- [CLI reference](cli-reference.md), every command and flag
- [Configuration](configuration.md), change currency, pricing, alerts
- [Architecture](architecture.md), how the pieces fit together
- [Support matrix](support-matrix.md), what kube-saver supports
