# Configuration

All kube-saver configuration is optional. The tool has safe, production-friendly defaults. You only need a config file if you want to change pricing, currency, alerts, or defaults.

---

## Config file location

kube-saver looks for config in this order (first match wins):

1. `--config PATH` flag
2. `KUBE_SAVER_CONFIG` environment variable
3. `~/.kube-saver/config.yaml`
4. `.kube-saver.yaml` in the current directory

Generate a full default config:

```bash
python3 -c "from kube_saver.config import default_config_yaml; print(default_config_yaml())" > .kube-saver.yaml
```

---

## Pricing

### CPU and memory pricing

All prices are in USD per hour. Defaults are reasonable for general-purpose cloud nodes.

```yaml
pricing:
  cpu_per_core_hour_usd: 0.040    # default — ~$29/core/month
  memory_per_gb_hour_usd: 0.005   # default — ~$3.65/GB/month
```

Override at runtime:

```bash
export KUBE_SAVER_CPU_PER_CORE=0.05
export KUBE_SAVER_MEM_PER_GB=0.006
```

### Currency

Display costs in a non-USD currency:

```yaml
currency: eur                      # usd, eur, gbp, aed, jpy, inr, cad, aud
exchange_rate_from_usd: 0.92       # manual rate (not auto-fetched)
```

Override at runtime:

```bash
export KUBE_SAVER_CURRENCY=eur
export KUBE_SAVER_EXCHANGE_RATE_FROM_USD=0.92
```

---

## Cloud provider hints

```yaml
cloud_provider: aws                # aws, gcp, azure, generic
provider_tier: general             # general, compute_opt, memory_opt, spot
```

These are hints only — kube-saver does not contact your cloud account. They help it select reasonable default pricing for the pricing model you are running.

---

## Exclusions

Skip namespaces or specific workloads:

```yaml
exclude_namespaces:
  - kube-system
  - kube-public
  - kube-node-lease
exclude_labels:
  - app.kubernetes.io/part-of: monitoring
exclude_annotations:
  - kube-saver.io/ignore: "true"
```

---

## Alerts

Thresholds used by `kube-saver notify` and the TUI alert panel:

```yaml
alerts:
  warning_waste_ratio: 0.4       # warn at 40% waste
  critical_waste_ratio: 0.8      # critical at 80% waste
  warning_monthly_usd: 100
  critical_monthly_usd: 500
  spike_threshold_usd: 250       # used by --threshold in notify command
```

---

## Export defaults

```yaml
export:
  output_directory: ./kube-saver-exports
  dry_run: false
```

---

## TUI

```yaml
tui:
  refresh_interval_seconds: 30
  compact_mode: false
```

---

## HTTP API server

```yaml
server:
  host: 127.0.0.1                 # loopback only by default
  port: 8080
```

The server defaults to loopback. Do **not** change `host` to `0.0.0.0` unless you have a reverse proxy with auth in front of it. See [Safety & trust](safety.md#http-api).

---

## Environment variables

Every config key has a runtime environment variable override. Environment variables take precedence over config file values.

| Env var | Config key | Example |
|---|---|---|
| `KUBE_SAVER_CONFIG` | (config file path) | `/etc/kube-saver/config.yaml` |
| `KUBE_SAVER_CURRENCY` | `currency` | `eur` |
| `KUBE_SAVER_EXCHANGE_RATE_FROM_USD` | `exchange_rate_from_usd` | `0.92` |
| `KUBE_SAVER_CPU_PER_CORE` | `pricing.cpu_per_core_hour_usd` | `0.05` |
| `KUBE_SAVER_MEM_PER_GB` | `pricing.memory_per_gb_hour_usd` | `0.006` |
| `KUBE_SAVER_CLOUD_PROVIDER` | `cloud_provider` | `aws` |
| `KUBE_SAVER_PROVIDER_TIER` | `provider_tier` | `spot` |
| `KUBE_SAVER_LOG_LEVEL` | (global) | `debug` |
| `KUBECONFIG` | `--kubeconfig` flag | `~/.kube/config` |

---

## See also

- [Getting started](getting-started.md)
- [CLI reference](cli-reference.md)
- [Safety & trust](safety.md)
