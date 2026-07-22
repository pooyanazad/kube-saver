# Self-contained outputs

kube-saver is designed to remain useful even with no maintainer-operated service behind it. Every output works offline, needs no external dependency, and is safe to email or commit.

---

## Design guarantee

If the kube-saver repository disappeared tomorrow, every release artifact and every file kube-saver has already generated would continue to work exactly as before. There is no hosted service, no CDN dependency, and no external API call in any output format.

---

## Output inventory

### HTML report (`kube-saver report`)

- Fully self-contained: inline CSS, no JavaScript, no CDN, no hosted assets
- Works offline in any browser
- Safe to email as an attachment or commit to a repository
- Contains the full waste breakdown, cost table, and recommendation list as of the generation time
- The report is a snapshot — it does not fetch live data

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

Two Markdown files written per run:

| File | Content |
|---|---|
| `daily-summary-{date}.md` | Namespace-level waste, cost, and efficiency table |
| `spike-alert-{date}.md` | Only written when a namespace exceeds your configured monthly USD threshold |

These files are designed to be consumed by:

- A cron job that emails them to a team
- A CI pipeline that archives them as artifacts
- A Git-based ops workflow that commits them for audit

### JSON / YAML / Helm values

Standard formats, no external dependencies:

- `--json PATH` on the report command writes a JSON summary
- `kube-saver export --format yaml` writes a YAML snapshot
- `kube-saver export --format helm` writes Helm values for the recommended resource changes

### Prometheus metrics

Standard Prometheus exposition format at `GET /metrics` when the HTTP server is running, or via the `kube-saver metrics` command. Ready to be scraped by any Prometheus-compatible system.

### HTTP API (`kube-saver serve`)

- Loopback-only by default (`127.0.0.1`)
- Read-only endpoints
- No authentication (because it is not designed to be public)
- See [Safety & trust](safety.md#http-api) if you need to expose it behind a proxy

---

## Why no hosted service

Most cost tools need a hosted dashboard, a Prometheus stack, or a cloud billing integration. kube-saver deliberately avoids all three:

- **Faster to try** — no account, no API key, no infrastructure to set up
- **Works anywhere** — local clusters, air-gapped environments, CI runners, laptops
- **No data leaves your machine** — important for regulated and security-conscious environments
- **No single point of failure** — if we go offline, nothing in your workflow breaks
- **No supply chain risk from hosted dependencies** — no CDN to go down, no API to change

The tradeoff: kube-saver gives you a snapshot, not a live dashboard. It tells you where the waste is right now and gives you a plan to fix it. It does not replace live monitoring or autoscaling.

---

## See also

- [Architecture](architecture.md)
- [Safety & trust](safety.md)
- [CLI reference](cli-reference.md)
