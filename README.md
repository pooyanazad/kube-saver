# kube-saver

> **k9s-style TUI that shows you exactly where your Kubernetes money goes.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Kubernetes](https://img.shields.io/badge/kubernetes-%23326ce5.svg)](https://kubernetes.io/)
[![Status: WIP](https://img.shields.io/badge/status-work%20in%20progress-orange.svg)](https://github.com/pooyanazad/kube-saver)

```
┌─ kube-saver ─────────────────────────────────────────────────────┐
│ Cluster: prod-us-east-1  │ Provider: AWS  │ CPU: 124/400 cores  │
├──────────────────────────────────────────────────────────────────┤
│ Total Monthly Waste: $2,847  │  Efficiency: 42%  │  Pods: 312   │
├──────────────────────────────────────────────────────────────────┤
│ Namespace          CPU Waste    Mem Waste    Monthly $   Score  │
│ default            45.2 cores   98 GB        $1,247     ██░░ 34 │
│ payments           12.8 cores   34 GB        $    642   ███░ 51 │
│ analytics           8.1 cores   22 GB        $    418   ███░ 58 │
│ staging             3.2 cores    9 GB        $    312   ████ 72 │
│ monitoring          0.8 cores    2 GB        $     89   █████ 91 │
└──────────────────────────────────────────────────────────────────┘
```

## What is kube-saver?

kube-saver is a **terminal-based tool** that shows you real-time, exactly how much money and resources are being wasted in your Kubernetes cluster. Think of it as **k9s but focused on cost and efficiency**.

### The Problem

- **40-60% of allocated CPU is never used**
- **50% of memory requests are over-provisioned**
- Engineers default to "2 CPU, 4GB RAM" and never change it
- Nobody correlates wasted CPU to wasted dollars in real time
- Existing tools (VPA, Goldilocks) are either too complex or too simple

### Why kube-saver is Different

- **k9s-style interactive TUI** — navigate clusters, namespaces, pods with keyboard
- **Real cost visibility** — shows actual $ waste, not just resource waste
- **eBPF-powered metrics** — captures real usage, not just metrics-server estimates
- **Smart recommendations** — suggests optimal resource requests/limits
- **Safety guardrails** — never breaks production workloads
- **GitOps integration** — generates PRs with optimized manifests

## Status

**Work in progress** — see [STEPS.md](STEPS.md) (local only) for the roadmap.

Current phase: **Foundation** (Steps 1-8 of 50)

## Planned Features

- [ ] Multi-cluster cost dashboard
- [ ] eBPF-based real-time metrics
- [ ] Smart resource recommendations
- [ ] YAML/Helm export with GitOps PR generation
- [ ] Slack/Teams/Prometheus integrations
- [ ] HTML reports for management

## Installation

```bash
pip install kube-saver
```

_(Not yet available — under development)_

## Quick Start

```bash
# Launch TUI against current kubeconfig context
kube-saver

# Generate waste report
kube-saver report

# Get optimization recommendations
kube-saver recommend
```

_(Not yet implemented)_

## Why?

Because **100% of Kubernetes clusters waste money**, and there is **no good tool** to show teams exactly how much. We combine:

- **Linux kernel power** (eBPF) for accurate metrics
- **Python ecosystem** for fast iteration
- **DevOps experience** for building tools DevOps engineers actually need

## Contributing

Contributions welcome! This is an early-stage project. See `STEPS.md` (local planning doc) for the full roadmap.

## License

MIT — see [LICENSE](LICENSE)