# Getting started

This guide walks you from a fresh install to your first kube-saver output on the four most common cluster types.

> **Time to first result:** under 5 minutes if you have `kubectl` access to any cluster.

---

## 1. Install

```bash
pip install kube-saver
```

From source (recommended for development):

```bash
git clone https://github.com/pooyanazad/kube-saver.git
cd kube-saver
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Optional eBPF support — gives the most accurate runtime data, but requires BCC bindings and host kernel capabilities:

```bash
pip install "kube-saver[ebpf]"
```

If eBPF is unavailable, kube-saver falls back automatically to metrics-server, then to safe estimates. You will see which source is being used in the TUI status bar and in every report.

---

## 2. Validate your connection

Before running a full scan, verify kube-saver can reach your cluster and has the permissions it needs:

```bash
kube-saver doctor
```

A successful run prints something like:

```text
[ok] kubeconfig context: kind-demo
[ok] cluster reachable
[ok] read pods (5/5 namespaces)
[ok] read nodes
[ok] metrics-server available (using as primary runtime source)
[ok] HTML report renderer
[ok] PR plan exporter
```

Any `[fail]` line tells you exactly what to fix. See [Troubleshooting](troubleshooting.md) for the common cases.

---

## 3. Run by environment

### Local cluster — kind / minikube / Docker Desktop

```bash
# Make sure your local cluster is running
kubectl cluster-info

# Launch the TUI
kube-saver
```

If you want demo data to play with, the repo ships a manifest at `demo/big-demo.yaml` that creates 7 namespaces with over-provisioned workloads — enough to populate the dashboard with realistic numbers.

### AWS EKS

```bash
aws eks update-kubeconfig --name my-cluster --region us-east-1
kube-saver
```

If you run inside an EKS node with IAM roles for service accounts, kube-saver will pick up the in-cluster config automatically when launched from inside a pod.

### Generic kubeconfig

```bash
export KUBECONFIG=/path/to/kubeconfig
kube-saver
```

If your kubeconfig has multiple contexts, pass the one you want:

```bash
kube-saver --context staging-cluster
```

### Restricted / read-only RBAC

You only need **list** and **get** permissions on a small set of resources. See [Safety & trust](safety.md#rbac) for the exact YAML.

---

## 4. Your first output

The fastest path to a real, shareable artifact:

```bash
# Self-contained HTML report (open it in any browser)
kube-saver report -o cost-report.html && open cost-report.html
```

The HTML file has no external assets, no CDN, and no JavaScript dependencies — it works offline, in an email attachment, and in a CI artifact.

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
# Daily markdown summary + spike alert written to ./alerts
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

- [CLI reference](cli-reference.md) — every command and flag
- [Configuration](configuration.md) — change currency, pricing, alerts
- [Architecture](architecture.md) — how the pieces fit together
