# kube-saver

> **k9s-style TUI that shows you exactly where your Kubernetes money goes.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Kubernetes](https://img.shields.io/badge/kubernetes-%23326ce5.svg)](https://kubernetes.io/)
[![Status: Production](https://img.shields.io/badge/status-production-brightgreen.svg)](https://github.com/pooyanazad/kube-saver)

```
┌─ kube-saver ─────────────────────────────────────────────────────┐
│ Cluster: prod-us-east-1  │ Provider: AWS  │ CPU: 124/400 cores   │
├──────────────────────────────────────────────────────────────────┤
│ Total Monthly Waste: $2,847  │  Efficiency: 42%  │  Pods: 312    │
├──────────────────────────────────────────────────────────────────┤
│ Namespace          CPU Waste    Mem Waste    Monthly $   Score   │
│ default            45.2 cores   98 GB        $1,247     ██░░ 34  │
│ payments           12.8 cores   34 GB        $    642   ███░ 51  │
│ analytics           8.1 cores   22 GB        $    418   ███░ 58  │
│ staging             3.2 cores    9 GB        $    312   ████ 72  │
│ monitoring          0.8 cores    2 GB        $     89   █████ 91 │
└──────────────────────────────────────────────────────────────────┘
```

## What is kube-saver?

kube-saver is a **terminal-based tool** that shows you real-time, exactly how much money and resources are being wasted in your Kubernetes cluster. Think of it as **k9s but focused on cost and efficiency**.

### Who is this for?

kube-saver is built for:

- **Platform engineers** who manage Kubernetes clusters and want clear visibility into where compute budget is being wasted
- **DevOps teams** who need to communicate infrastructure cost to engineering stakeholders without relying on cloud dashboards alone
- **SREs and operators** who want a self-contained, scriptable tool that works in CI and local environments without external services
- **Startup teams** running Kubernetes on a budget who want to cut waste before it becomes a problem
- **Solo cluster operators** who want one fast tool to understand and report on cluster cost without complexity

### Who this is NOT for?

kube-saver is not a substitute for:

- Full cloud cost management platforms (it does not ingest billing data)
- Automated rightsizing engines that apply changes directly
- Tools that require a hosted service or account to function

## The Problem

- **40-60% of allocated CPU is never used**
- **50% of memory requests are over-provisioned**
- Engineers default to "2 CPU, 4GB RAM" and never change it
- Nobody correlates wasted CPU to wasted dollars in real time
- Existing tools (VPA, Goldilocks) are either too complex or too simple

### Why kube-saver is Different

- **k9s-style interactive TUI** — navigate clusters, namespaces, pods with keyboard
- **Real cost visibility** — shows actual $ waste, not just resource waste
- **Runtime source awareness** — uses eBPF when available, otherwise falls back to metrics-server or estimated data
- **Smart recommendations** — suggests optimal resource requests/limits
- **Safety guardrails** — avoids unsafe recommendations by design
- **Self-contained outputs** — no webhook URLs, no GitHub API calls, no CDN-hosted assets required

## Status

**Phase 6 completed locally**.

Implemented:
- Phase 1 foundation
- Phase 2 analyzers and recommendations
- Phase 3 TUI
- Phase 4 runtime collector fallback chain
- Phase 5 self-contained exporters and integrations
- Phase 6 test suite, server mode, and CI setup

Key result: kube-saver now works without depending on maintainer-owned external services.
Notifications are written to local Markdown files, PR output is generated as local review/apply artifacts, HTML reports are fully self-contained, and release artifacts are published through GitHub Actions only.

## Current Features

- Interactive TUI dashboard via `kube-saver` or `python -m kube_saver.cli`
- Click CLI subcommands: `tui`, `report`, `pr-plan`, `notify`, `serve`, `version`
- Cluster, namespace, and pod waste analysis
- Monthly and yearly cost estimation
- Multi-currency display
- Custom CPU and memory pricing
- Runtime metric fallback chain:
  - eBPF
  - metrics-server
  - estimated data
- YAML exporter
- Helm values exporter
- PR plan generator that writes local review/apply files
- Markdown notification output (daily summaries and spike alerts)
- Prometheus metrics formatter
- Self-contained HTML report generator with inline CSS charts
- JSON output builder
- Basic read-only HTTP API server mode

## Installation

For contribution and development workflow details, see [CONTRIBUTING.md](CONTRIBUTING.md).

### Local development install

```bash
git clone https://github.com/pooyanazad/kube-saver.git
cd kube-saver
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

### Minimal install

```bash
pip install -e .
```

### Optional eBPF support

```bash
pip install -e .[ebpf]
```

> Note: eBPF support also depends on host kernel capabilities and BCC availability.

## Quick Start

### Launch the TUI

```bash
source .venv/bin/activate
kube-saver
```

### CLI commands

```bash
kube-saver tui
kube-saver report -o kube-saver-report.html
kube-saver pr-plan -d ./kube-saver-pr
kube-saver notify -d ./kube-saver-notify --threshold 250
kube-saver serve -p 8080 -b 127.0.0.1
kube-saver version
```

### Generate default config YAML

```bash
python3 -c "from kube_saver.config import default_config_yaml; print(default_config_yaml())"
```

### Use JSON output helpers in automation

```bash
python3 - <<'PY2'
from kube_saver.exporters.json_output import build_json_report
print(build_json_report(cluster=None, resource_report=None, cost_report=None, recommendations=[]))
PY2
```

### Run the basic API server

```python
from kube_saver.server import build_server

server = build_server(lambda: {"status": "ok"}, port=8080)
server.serve_forever()
```

## Configuration

kube-saver lets you change both **currency** and **CPU/memory pricing** in a few lines — no code edits required.

### Change currency

Edit `~/.kube-saver/config.yaml` (or any `.kube-saver.yaml` in your project):

```yaml
currency: eur                  # usd, eur, gbp, aed, jpy, inr
exchange_rate_from_usd: 0.92   # 1 USD -> 0.92 EUR
```

Or set at runtime:

```bash
export KUBE_SAVER_CURRENCY=eur
export KUBE_SAVER_EXCHANGE_RATE_FROM_USD=0.92
```

### Change CPU or memory price

```yaml
pricing:
  cpu_per_core_hour_usd: 0.05     # default 0.040
  memory_per_gb_hour_usd: 0.006   # default 0.005
```

Or at runtime:

```bash
export KUBE_SAVER_CPU_PER_CORE=0.05
export KUBE_SAVER_MEM_PER_GB=0.006
```

### Other useful config sections

```yaml
cloud_provider: aws
provider_tier: general
exclude_namespaces:
  - kube-system
  - kube-public
alerts:
  warning_waste_ratio: 0.4
  critical_waste_ratio: 0.8
  warning_monthly_usd: 100
  critical_monthly_usd: 500
export:
  output_directory: ./kube-saver-exports
  dry_run: true
tui:
  refresh_interval_seconds: 30
  compact_mode: false
```

## Architecture

High-level flow:

1. **Collectors** gather cluster state and runtime data
2. **Analyzers** compute waste and health
3. **Pricing engine** converts waste to cost
4. **Recommendation engine** proposes safer resource values
5. **TUI and exporters** present the results

Main modules:

- `collectors/` — Kubernetes, metrics-server, runtime fallback, eBPF safety
- `analyzers/` — waste, cost, health, alerts
- `pricing/` — rates and currency display
- `recommenders/` — rightsizing suggestions
- `tui/` — Textual app and data loading
- `exporters/` — YAML, Helm, JSON, Prometheus, HTML, Markdown notifications, local PR plans
- `server.py` — basic read-only HTTP API mode

## Self-contained outputs

kube-saver is designed to remain useful even with no maintainer-operated service behind it.

- **Notifications**: written as Markdown files to a local directory
- **PR plans**: generated as local review files plus an `apply-patches.sh` helper
- **Reports**: HTML is fully self-contained with inline CSS charts, no CDN assets
- **Server**: local read-only HTTP endpoints for automation and inspection
- **Releases**: GitHub Actions publishes build artifacts to GitHub releases; no PyPI token is required

## Troubleshooting

### TUI opens but metrics are estimated

This usually means:
- metrics-server is not available, or
- eBPF is unavailable, so kube-saver fell back

Phase 4 intentionally degrades safely instead of crashing.

### eBPF is not being used

Common reasons:
- Python BCC bindings are not installed
- host kernel capabilities are missing
- tracefs/debugfs is unavailable
- root or extra capabilities may be required

### Kubernetes connection fails

Check:
- your kubeconfig context
- cluster reachability
- RBAC permissions
- whether the current environment should use kubeconfig or in-cluster config

### Tests

Run all tests:

```bash
source .venv/bin/activate
pytest tests -q
```

Run with coverage:

```bash
source .venv/bin/activate
pytest tests --cov=src/kube_saver --cov-report=term-missing -q
```

## Contributing

Contributions are welcome.

Suggested local workflow:

```bash
git checkout -b my-change
source .venv/bin/activate
pytest tests -q
ruff check src tests
mypy src
```

Please keep changes small, tested, and focused.

## CI/CD

GitHub Actions now runs:
- Ruff
- Mypy
- Pytest
- package build
- tagged release and Docker jobs

## Why?

Because **Kubernetes waste is real money**, and teams need a fast terminal tool to see it clearly.

## License

MIT — see [LICENSE](LICENSE)
