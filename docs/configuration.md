# Configuration

Configuration is optional. Use it to select namespaces, context, modeled pricing,
currency, and supported collection settings. Review recommendation boundaries in
[Safety & trust](safety.md); parsed settings do not all control CLI behavior.

---

## Config file location

kube-saver merges config in this order, with later values taking precedence:

1. Built-in defaults
2. `~/.kube-saver/config.yaml`
3. `.kube-saver.yaml` in the current directory
4. Supported `KUBE_SAVER_*` environment variables

Generate a full default config:

```bash
python3 -c "from kube_saver.config import default_config_yaml; print(default_config_yaml())" > .kube-saver.yaml
```

---

## Pricing

### CPU and memory pricing

Prices are modeled USD rates per core-hour and GiB-hour, not live cloud quotes.
The example below matches the unknown-provider fallback. Provider-specific
assumptions differ. Monthly estimates use 730 hours; see the [FAQ](faq.md).

Custom CPU and memory rates can be supplied independently. A positive custom
rate replaces that dimension; zero, omitted, negative, non-numeric, and non-finite
rates retain the provider default. Numeric strings are accepted.

```yaml
pricing:
  cpu_per_core_hour_usd: 0.040    # fallback, ~$29.20/core/month
  memory_per_gb_hour_usd: 0.005   # fallback, ~$3.65/GiB/month
```

Override at runtime:

```bash
export KUBE_SAVER_CPU_PER_CORE=0.05
export KUBE_SAVER_MEM_PER_GB=0.006
```

### Currency

Display costs in a non-USD currency:

```yaml
currency: eur                      # usd, eur, gbp, aed, jpy, inr
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
cloud_provider: aws                # aws, gcp, azure, on-prem, unknown
provider_tier: general             # aws: general/t3/r5; gcp: general/e2_small
```

These select bundled pricing assumptions without contacting a cloud billing API.
Azure and on-prem use `general`. Unknown tiers fall back to the provider
`general` rate; an unknown provider uses $0.040/core-hour and $0.005/GiB-hour.

---

## Exclusions

Skip namespaces or specific workloads:

```yaml
exclude_namespaces:
  - kube-system
  - kube-public
  - kube-node-lease
exclude_labels:
  app.kubernetes.io/part-of: monitoring
exclude_annotations:
  kube-saver.io/ignore: "true"
```

For a Role limited to specific namespaces, set `namespace_filter` to those names. This avoids needing cluster-wide permission to list Namespace objects:

```yaml
namespace_filter:
  - my-app
```

---

## Alerts

Thresholds used by the TUI alert panel:

```yaml
alerts:
  warning_waste_ratio: 0.4       # warn at 40% waste
  critical_waste_ratio: 0.8      # critical at 80% waste
  warning_monthly_usd: 100
  critical_monthly_usd: 500
```

`notify --threshold` is a command option (default: 100 USD); it does not use
these TUI alert thresholds.

---

## Recommendation floors

These are top-level YAML keys (not a nested `safety` mapping):

```yaml
min_cpu_millicores: 100
min_memory_bytes: 134217728     # 128Mi
prod_cpu_floor_ratio: 0.5
prod_memory_floor_ratio: 0.5
aggressive_mode: false
```

The relative floors apply to every eligible workload in normal mode. Aggressive
mode skips relative floors, not absolute minimums. Only a YAML boolean `true`
(or a supported truthy environment value) enables it; quoted strings such as
`"false"` and other non-boolean YAML values retain normal-mode protection. CPU × 1.5 and memory × 1.2
remain fixed current-sample buffers. Invalid absolute floors use defaults;
relative floors use defaults if non-positive and cap at 1.0.

---

## Export defaults

```yaml
export:
  output_directory: ./kube-saver-exports
  dry_run: true
```

These are parsed configuration fields, not the CLI output defaults.
`pr-plan --dir` and `notify --dir` choose their directories, and both commands
write local files. `export.dry_run` does not suppress those writes.

---

## TUI

```yaml
tui:
  refresh_interval_seconds: 30
  compact_mode: false
```

---

## HTTP API server

```bash
kube-saver serve --bind 127.0.0.1 --port 8080
```

These are CLI options, not config keys. The server defaults to loopback. See [Safety & trust](safety.md#http-api) before exposing it.

---

## Kubernetes API timeouts

kube-saver supplies HTTP timeouts to collector and doctor API reads. These
bound connection/read waits; they are not a wall-clock deadline for an entire
scan, credential plugin, or retry sequence. Three knobs are available; all
are optional and have defaults.

```yaml
timeouts:
  connect_seconds: 10       # TCP connect deadline per request
  read_seconds: 30          # read deadline per request
  operation_seconds: 60     # HTTP timeout passed to list/get calls
```

### Safe defaults and rationale

| Key | Default | Why this value |
|---|---|---|
| `connect_seconds` | `10` | Long enough for a cold TLS handshake to a managed control plane (EKS/GKE/AKS) over a typical corporate link, short enough to fail fast on a dead endpoint. |
| `read_seconds` | `30` | Covers large namespace listings on busy clusters while still bounding hung responses. |
| `operation_seconds` | `60` | HTTP timeout passed to list/get requests, including Metrics API reads. This is not an overall scan deadline. |

Invalid values (zero, negative, non-numeric, `NaN`, `inf`) are silently replaced with the defaults — kube-saver never runs with timeouts disabled.

### Environment overrides

```bash
export KUBE_SAVER_TIMEOUT_CONNECT=5
export KUBE_SAVER_TIMEOUT_READ=20
export KUBE_SAVER_TIMEOUT_OPERATION=45
```

Environment variables override config-file values; CLI flags are not provided because timeouts are rarely changed per-invocation. Lower these values for tight CI budgets; raise them only if a large, slow cluster is producing spurious timeouts.

### Where timeouts apply

Timeouts are applied consistently across:

- `K8sClient` collectors (cluster info, namespaces, pods, node→pod maps)
- metrics-server collection (per-call operation timeout)
- `kube-saver doctor` (version check and RBAC self-subject access reviews)
- the HTTP API server and TUI, which both use the same `K8sClient` path

A partial pod scan returns usable data with a warning. If all pod reads fail,
the report commands exit with code 4 rather than writing an empty successful
report. Other resource failures can leave metadata unavailable.

---

## Environment variables

The configuration loader accepts the variables below. They take precedence over
config-file values. `doctor --context` overrides the configured context;
without that option, doctor checks the same configured context as scans.

| Env var | Config key | Example |
|---|---|---|
| `KUBE_SAVER_CURRENCY` | `currency` | `eur` |
| `KUBE_SAVER_EXCHANGE_RATE_FROM_USD` | `exchange_rate_from_usd` | `0.92` |
| `KUBE_SAVER_CPU_PER_CORE` | `pricing.cpu_per_core_hour_usd` | `0.05` |
| `KUBE_SAVER_MEM_PER_GB` | `pricing.memory_per_gb_hour_usd` | `0.006` |
| `KUBE_SAVER_PROVIDER` | `cloud_provider` | `aws` |
| `KUBE_SAVER_TIER` | `provider_tier` | `t3` |
| `KUBE_SAVER_CONTEXT` | `kubeconfig_context` | `staging` |
| `KUBE_SAVER_TIMEOUT_CONNECT` | `timeouts.connect_seconds` | `5` |
| `KUBE_SAVER_TIMEOUT_READ` | `timeouts.read_seconds` | `20` |
| `KUBE_SAVER_TIMEOUT_OPERATION` | `timeouts.operation_seconds` | `45` |
| `KUBE_SAVER_REFRESH_SECS` | `tui.refresh_interval_seconds` | `30` |
| `KUBE_SAVER_MAX_METRIC_AGE_SECONDS` | `runtime.max_metric_age_seconds` | `300` |
| `KUBE_SAVER_RETRY_MAX_ATTEMPTS` | `retries.max_attempts` | `3` |
| `KUBE_SAVER_RETRY_INITIAL_BACKOFF` | `retries.initial_backoff_ms` | `200` |
| `KUBE_SAVER_RETRY_MAX_BACKOFF` | `retries.max_backoff_ms` | `5000` |
| `KUBE_SAVER_AGGRESSIVE_MODE` | `safety.aggressive_mode` (skips relative floors, retains absolute floors) | `false` |
| `KUBECONFIG` | Kubernetes client config path | `~/.kube/config` |

---

## See also

- [Getting started](getting-started.md)
- [CLI reference](cli-reference.md)
- [Safety & trust](safety.md)
