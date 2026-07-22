# kube-saver

> **See exactly where your Kubernetes money goes — then fix it.**

A fast, offline, self-contained Kubernetes cost analyzer.
Works from your kubeconfig alone — no cloud account, no SaaS signup, no hosted service.
Turns invisible cluster waste into visible dollar amounts you can act on in one command.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Kubernetes](https://img.shields.io/badge/kubernetes-%23326ce5.svg)](https://kubernetes.io/)
[![Status: Production](https://img.shields.io/badge/status-production-brightgreen.svg)](https://github.com/pooyanazad/kube-saver)

---

## What you get

```
┌─ kube-saver ─────────────────────────────────────────────────────┐
│ Total Monthly Waste: $406.79 │ Efficiency: 0% │ Pods: 21         │
├──────────────────────────────────────────────────────────────────┤
│ Namespace    CPU Waste   Mem Waste   Monthly $                   │
│ prod         9750m       12032Mi     $327.59                     │
│ staging      2100m        2048Mi      $68.62                     │
│ data           90m         256Mi       $3.83                     │
│ dev           100m         128Mi       $3.38                     │
│ monitoring     50m         128Mi       $3.38                     │
└──────────────────────────────────────────────────────────────────┘
```

- **Real dollar amounts** for every namespace, workload, and pod — not just millicores
- **Interactive TUI** — k9s-style keyboard navigation, cost and recommendation views
- **Self-contained HTML report** — open in any browser, email as-is, no CDN
- **Local PR plans** — review and apply right-sizing changes without touching a cloud API
- **Markdown spike alerts** — daily summaries written to local files, no webhook needed
- **Three runtime sources**: eBPF → metrics-server → safe estimates

---

## Screenshots

<p align="center">
  <img src="docs/screenshots/dashboard.png" alt="kube-saver TUI dashboard" width="780" />
</p>
<p align="center"><em>Namespace overview — wastes, pods, and monthly cost at a glance.</em></p>

<p align="center">
  <img src="docs/screenshots/cost.png" alt="kube-saver cost breakdown" width="780" />
</p>
<p align="center"><em>Per-namespace cost breakdown with CPU and memory waste.</em></p>

<p align="center">
  <img src="docs/screenshots/recommendations.png" alt="kube-saver recommendations" width="780" />
</p>
<p align="center"><em>Actionable right-sizing recommendations with savings per workload.</em></p>

---

## Quick start

```bash
pip install kube-saver
```

```bash
# Interactive TUI — opens immediately
kube-saver

# Self-contained HTML report
kube-saver report -o cost-report.html && open cost-report.html

# Local PR plan with review and apply files
kube-saver pr-plan -d ./pr-files
```

Time to first result: **under 5 minutes** if you have `kubectl` access to any cluster.
See the [full getting started guide](docs/getting-started.md) for kind, EKS, Docker Desktop, and generic kubeconfig.

---

## Before / after example

```
prod/auth-svc        cpu-request  1000m  → 50m      save ~$25/mo per replica
prod/auth-svc        mem-request  2.0Gi  → 64Mi     save ~$15/mo per replica
staging/staging-api  cpu-request   300m  → 50m      save ~$7/mo per replica
```

Real output from the demo cluster: **40 high-confidence recommendations, $373.03/mo potential savings** — see the [recommendations screenshot](docs/screenshots/recommendations.png).

---

## Why kube-saver instead of …

| Feature | **kube-saver** | k9s | Goldilocks | VPA | Kubecost |
|---|---|---|---|---|---|
| Cost in dollars | ✅ | ❌ | ❌ | ❌ | ✅ |
| Fully offline | ✅ | ✅ | ✅ | ✅ | ❌ needs Prometheus |
| Self-contained HTML report | ✅ | ❌ | ❌ | ❌ | ❌ |
| Interactive TUI | ✅ | ✅ | ❌ | ❌ | ❌ |
| Right-sizing recommendations | ✅ | ❌ | ✅ | ✅ live | partial |
| Local PR plan generator | ✅ | ❌ | ❌ | ❌ | ❌ |
| Works without hosted service | ✅ | ✅ | ✅ | ✅ | ❌ |

kube-saver's niche: **dollar-first, offline, shareable**.
It does not replace live autoscaling — it gives you the number and the plan.

---

## Who this is for

- **Platform engineers** who need to know where compute budget is leaking
- **DevOps / SRE teams** who have to communicate cost without a cloud dashboard
- **Startup teams** running Kubernetes on a tight budget
- **Solo cluster operators** who want one fast, scriptable tool

**Who this is NOT for:**
Teams that need live automated right-sizing (use VPA), billing-data ingestion (use a full cloud cost platform), or a hosted SaaS.

---

## How it stays independent

kube-saver has **no hosted service, no account, and no external dependency**:

- HTML reports are fully self-contained (inline CSS, no CDN, works offline)
- Notifications are written to local Markdown files
- PR plans are local review/apply files — no cloud API
- The HTTP API is loopback-only by default
- Releases are published via GitHub Actions — no PyPI token needed

If this repo disappeared tomorrow, every release artifact still works.

---

## Documentation

| Document | What's inside |
|---|---|
| [Getting started](docs/getting-started.md) | First-run guide for kind, EKS, Docker Desktop, generic kubeconfig |
| [CLI reference](docs/cli-reference.md) | Every command, flag, JSON helper, server mode |
| [Configuration](docs/configuration.md) | Currency, pricing, env vars, all config keys |
| [Architecture](docs/architecture.md) | Module map, data flow, runtime source chain |
| [Comparison](docs/comparison.md) | Detailed comparison vs k9s, Goldilocks, VPA, Kubecost |
| [Safety & trust](docs/safety.md) | What kube-saver will never do, RBAC, recommendation boundaries |
| [Self-contained outputs](docs/self-contained.md) | Why no hosted service, output guarantees |
| [Troubleshooting](docs/troubleshooting.md) | Common issues and fixes |

---

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for workflow.

```bash
git checkout -b my-change
source .venv/bin/activate
pytest tests -q
ruff check src tests
mypy src
```

## License

MIT — see [LICENSE](LICENSE).
