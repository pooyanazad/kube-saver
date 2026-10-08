# kube-saver documentation

kube-saver estimates Kubernetes CPU and memory costs from resource requests,
metrics-server samples, and configured pricing rates. It runs locally and
produces a terminal dashboard, HTML reports, and reviewable resource-change plans.

| Task | Guide |
|---|---|
| Install and generate a first report | [Getting started](getting-started.md) |
| Understand costs, telemetry, and limitations | [Cost model and FAQ](faq.md) |
| Find supported commands and flags | [CLI reference](cli-reference.md) |
| Select a context or configure pricing | [Configuration](configuration.md) |
| Grant read permissions | [RBAC](rbac.md) |
| Review recommendations safely | [Safety and trust](safety.md) |
| Run in a container | [Deployment](deployment.md) |
| Diagnose connection or metrics problems | [Troubleshooting](troubleshooting.md) |
| Understand modules and data flow | [Architecture](architecture.md) |
| Compare workflows | [Comparison](comparison.md) |
| Inspect portable output formats | [Self-contained outputs](self-contained.md) |
| Review reported environment support | [Support matrix](support-matrix.md) |
| Inspect dated test records and limits | [Support evidence](support-evidence.md) |
| Prepare a release | [Release testing](release-testing.md) |
| Make your first contribution | [Contributing](../CONTRIBUTING.md) |

These docs describe the source checkout. Use `kube-saver version` and
`kube-saver --help` to identify the behavior of your installed package.
