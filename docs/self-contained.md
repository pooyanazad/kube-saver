# Self-contained outputs

kube-saver produces portable report and review files without a maintainer-operated
service. Reading an HTML report works offline; scanning, serving fresh data, or
executing patch commands requires Kubernetes API access. Review internal cluster
names before sharing or committing generated files.

---

## Design guarantee

Generated HTML uses inline assets and does not call a hosted service. Local
Markdown and JSON remain readable with standard tools. Running the application
still requires its Python dependencies, credentials, and cluster access; release
artifacts are not a guarantee of compatibility with future environments.

---

## Output inventory

### HTML report (`kube-saver report`)

- Fully self-contained: inline CSS, no JavaScript, no CDN, no hosted assets
- Works offline in any browser
- Review for internal cluster names before emailing or committing
- Contains the full waste breakdown, cost table, and recommendation list as of the generation time
- The report is a snapshot, it does not fetch live data

### PR plan files (`kube-saver pr-plan`)

All files are written to a local directory you specify:

| File | Format | Purpose |
|---|---|---|
| `summary.md` | Markdown | One-page summary for human reviewers |
| `review.txt` | Plain text | Every recommended change with current vs. suggested value and reasoning |
| `apply-patches.sh` | Bash script | Ready-to-run commands to apply the recommended resource changes |
| `README.md` | Markdown | Context and instructions for the reviewer |

The `apply-patches.sh` script is **not auto-executed**. It is a file you review, test, and run yourself. kube-saver will never mutate your cluster without your explicit action.

### Notifications (`kube-saver notify`)

A daily summary and, when eligible, a spike alert:

| File | Content |
|---|---|
| `daily-summary-{date}.md` | Namespace-level waste, cost, and efficiency table |
| `spike-alert-{date}.md` | Written above `notify --threshold` (default $100/month), with complete measured metrics and no partial scan |

These files are designed to be consumed by:

- A cron job that emails them to a team
- A CI pipeline that archives them as artifacts
- A Git-based ops workflow that commits them for audit

### JSON

Standard JSON, no hosted dependency:

- `--json PATH` on the report command writes a JSON summary

### HTTP API (`kube-saver serve`)

- Loopback-only by default (`127.0.0.1`)
- Read-only endpoints
- No authentication (because it is not designed to be public)
- See [Safety & trust](safety.md#http-api) if you need to expose it behind a proxy

---

## Why no hosted service

There is no required kube-saver account, hosted dashboard, or CDN for reports.
Install the package, grant Kubernetes read permissions, and use metrics-server
for measured usage. Air-gapped installations need the package and dependencies
available locally; credential acquisition depends on the kubeconfig.

The report is a snapshot with modeled CPU/memory costs. It does not replace
continuous monitoring, invoice reconciliation, or autoscaling. See the
[cost model and FAQ](faq.md) for what the numbers mean.

---

## See also

- [Architecture](architecture.md)
- [Safety & trust](safety.md)
- [CLI reference](cli-reference.md)
