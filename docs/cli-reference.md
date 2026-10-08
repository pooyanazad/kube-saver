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
| `-o, --output PATH` | Output HTML file path (default: `kube-saver-report.html`) |
| `--json PATH` | Also write a JSON summary alongside the HTML |

A completely failed pod scan exits with code 4 and writes no report. A partial scan writes a report with a warning and marks the JSON as degraded.

The HTML is fully portable, no CDN, no external assets, works in any browser offline.

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
| `apply-patches.sh` | Bash script with the recommended resource changes (does **not** auto-apply, review first) |
| `README.md` | Context and instructions for the reviewer |

### `kube-saver notify`

Write daily summary and spike alert Markdown files to disk.

```bash
kube-saver notify -d ./alerts --threshold 250
```

| Flag | Description |
|---|---|
| `-d, --dir PATH` | Output directory (created if missing) |
| `--threshold USD` | Monthly USD threshold above which a spike alert is written (default: 100) |

Spike alerts require current usage metrics for every scanned pod and a complete scan. The daily summary still records request-based estimates when metrics are unavailable.

### `kube-saver serve`

Start the read-only HTTP API on loopback.

```bash
kube-saver serve -p 8080 -b 127.0.0.1
```

| Flag | Description |
|---|---|
| `-p, --port PORT` | TCP port (default: 8080) |
| `-b, --bind HOST` | Bind address (default: 127.0.0.1, loopback only) |
| `--expose` | Confirm binding to a non-loopback address |

The API provides `GET /healthz`, `/readyz`, `/api/v1/report`, and `/openapi.json`. Each report request scans the cluster. It is not an OAuth-aware public API. Binding to a non-loopback address requires `--expose`; put it behind a reverse proxy with auth, see [Safety & trust](safety.md#http-api).

### `kube-saver version`

Print the installed version and exit.

```bash
kube-saver version
```

### `kube-saver doctor`

Check kubeconfig, connectivity, and RBAC. Use `--context NAME` to check a specific context. If `namespace_filter` is configured, RBAC checks target those namespaces. Missing metrics permissions are reported as optional because request-based estimates still work.

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
| `3` | Cluster unreachable or API authentication failed |
| `4` | Analysis or pod collection failed |

---

## Context and configuration

The CLI has no global options. Set these environment variables before a command, or use the config files described in [Configuration](configuration.md):

| Setting | Description |
|---|---|
| `KUBE_SAVER_CONTEXT` | kubeconfig context for scans and the TUI |
| `KUBECONFIG` | kubeconfig file path |
| `~/.kube-saver/config.yaml` | User config file |
| `.kube-saver.yaml` | Project config file |

`doctor` alone accepts `-c, --context` to check a named context. Every command accepts `--help`.

---

## See also

- [Configuration](configuration.md)
- [Architecture](architecture.md)
- [Troubleshooting](troubleshooting.md)
