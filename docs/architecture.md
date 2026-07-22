# Architecture

A short overview of how kube-saver collects data, computes waste, and produces outputs.

---

## Data flow

```
Kubernetes API ─┐
metrics-server  ─┤──> Collectors ──> Analyzers ──> Pricing engine
eBPF (optional) ─┘         │              │              │
                           ▼              ▼              ▼
                      ┌──────────────────────────────────────┐
                      │         Cost + waste snapshot         │
                      └───────┬──────────┬──────────┬────────┘
                              ▼          ▼          ▼
                            TUI       Report     PR plan / notify
```

1. **Collectors** query the Kubernetes API for pods, nodes, and resource requests.
   If metrics-server is available they collect runtime usage.
   If eBPF is available they collect per-pod CPU usage from the kernel.
   If neither is available they fall back to safe estimates based on requests.
2. **Analyzers** compute waste (requested minus used), cluster health, and namespace efficiency.
3. **Pricing engine** converts waste into monthly and yearly dollar amounts using your configured pricing model.
4. **Recommendation engine** proposes right-sizing suggestions with safety guards (see [Safety & trust](safety.md)).
5. **Exporters** format the snapshot into whichever output you requested.

---

## Runtime source chain

kube-saver uses the first available source in this order:

| Priority | Source | Accuracy | Requires |
|---|---|---|---|
| 1 | eBPF | Per-container CPU, kernel-level | BCC bindings + root + host kernel |
| 2 | metrics-server | Cluster-aggregated usage | metrics-server running |
| 3 | Estimates | Request-based only | Nothing extra |

The source is shown in the TUI status bar and in every generated report.
Falling back is **not an error** — it is by design. kube-saver degrades gracefully instead of crashing.

---

## Module map

| Directory | Purpose |
|---|---|
| `src/kube_saver/collectors/` | Kubernetes API, metrics-server, eBPF, runtime source selector |
| `src/kube_saver/analyzers/` | Waste, cost, health, alerts |
| `src/kube_saver/pricing/` | Pricing model, currency, exchange rates |
| `src/kube_saver/recommenders/` | Right-sizing suggestion engine |
| `src/kube_saver/tui/` | Textual TUI app, data loading, screen rendering |
| `src/kube_saver/exporters/` | HTML, JSON, YAML, Helm, Prometheus, Markdown, PR plan, notifications |
| `src/kube_saver/server.py` | Read-only HTTP API (loopback default) |
| `src/kube_saver/config.py` | Config loading, validation, default generation |
| `src/kube_saver/cli.py` | Typer CLI entry point |

---

## Output guarantees

All outputs are designed to be self-contained and dependency-free:

| Output | External dependencies |
|---|---|
| HTML report | None — inline CSS, no CDN, no JS |
| JSON / YAML / Helm values | None — standard formats |
| Prometheus metrics | None — standard exposition format |
| PR plan files | None — plain Markdown and Bash |
| Notifications | None — plain Markdown |
| HTTP API | Loopback only by default; no external auth |

See [Self-contained outputs](self-contained.md) for the design rationale.

---

## See also

- [Getting started](getting-started.md)
- [Configuration](configuration.md)
- [CLI reference](cli-reference.md)
