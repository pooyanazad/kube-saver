# CLI reference

Every command, flag, and code helper kube-saver exposes. If something is missing here, it does not exist.

## Commands

### `kube-saver` (default: TUI)

Launch the interactive terminal dashboard.

```bash
kube-saver
kube-saver tui
```

Key bindings inside the TUI:

| Key | Action |
|---|---|
| `1` | Namespace overview (default view) |
| `2` | Cost breakdown |
| `3` | Recommendations |
| `Enter` | Drill into the selected namespace or pod |
| `/` | Search / filter |
| `r` | Refresh data |
| `q` | Quit |

### `kube-saver report`

Generate a self-contained HTML executive report.

```bash
kube-saver report -o cost-report.html
```

| Flag | Description |
|---|---|
| `-o, --output PATH` | Output HTML file path (required) |
| `--json PATH` | Also write a JSON summary alongside the HTML |
| `--config PATH` | Use a non-default config file |

The HTML is fully portable — no CDN, no external assets, works in any browser offline.

### `kube-saver pr-plan`

Generate local PR plan files: human-readable summary, review file, and an apply script.

```bash
kube-saver pr-plan -d ./pr-files
```

| Flag | Description |
|---|---|
| `-d, --dir PATH` | Output directory (created if missing) |

Files produced:

| File | Purpose |
|---|---|
| `summary.md` | One-page summary of recommendations and savings |
| `review.txt` | Detailed change list with current vs. suggested values and reasoning |
| `apply-patches.sh` | Bash script with the recommended resource changes (does **not** auto-apply — review first) |
| `README.md` | Context and instructions for the reviewer |

### `kube-saver notify`

Write daily summary and spike alert Markdown files to disk.

```bash
kube-saver notify -d ./alerts --threshold 250
```

| Flag | Description |
|---|---|
| `-d, --dir PATH` | Output directory (created if missing) |
| `--threshold USD` | Monthly USD threshold above which a spike alert is written (default: 500) |

### `kube-saver serve`

Start the read-only HTTP API on loopback.

```bash
kube-saver serve -p 8080 -b 127.0.0.1
```

| Flag | Description |
|---|---|
| `-p, --port PORT` | TCP port (default: 8080) |
| `-b, --bind HOST` | Bind address (default: 127.0.0.1 — loopback only) |

The API is intentionally minimal: `GET /health` and `GET /report` (latest snapshot). It is not an OAuth-aware public API. If you bind it to `0.0.0.0` you are responsible for putting it behind a reverse proxy with auth — see [Safety & trust](safety.md#http-api).

### `kube-saver version`

Print the installed version and exit.

```bash
kube-saver version
```

---

## Python helpers

For automation that needs to embed kube-saver's outputs in another tool:

### Render a default config YAML

```bash
python3 -c "from kube_saver.config import default_config_yaml; print(default_config_yaml())"
```

### Build a JSON report from custom inputs

```python
from kube_saver.exporters.json_output import build_json_report

report = build_json_report(
    cluster=None,
    resource_report=None,
    cost_report=None,
    recommendations=[],
)
print(report)
```

### Run the API server programmatically

```python
from kube_saver.server import build_server

server = build_server(lambda: {"status": "ok"}, port=8080)
server.serve_forever()
```

---

## Exit codes

All commands use stable exit codes for automation:

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Generic failure (see stderr) |
| `2` | Invalid configuration |
| `3` | Cluster unreachable |
| `4` | Insufficient RBAC permissions |
| `5` | Runtime source unavailable (eBPF / metrics-server) — non-fatal; falls back to estimates |

---

## Global flags

These work on every subcommand:

| Flag | Description |
|---|---|
| `--config PATH` | Path to a config YAML |
| `--context NAME` | kubeconfig context to use |
| `--kubeconfig PATH` | Path to kubeconfig (same as `KUBECONFIG` env var) |
| `--log-level LEVEL` | `debug` / `info` / `warn` / `error` (default: `info`) |
| `--no-color` | Disable ANSI colors in output |
| `--help` | Show help for the current command |

---

## See also

- [Configuration](configuration.md)
- [Architecture](architecture.md)
- [Troubleshooting](troubleshooting.md)
