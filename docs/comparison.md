# kube-saver and other Kubernetes tools

Choose by the data model and workflow you need. kube-saver offers local snapshots
with modeled CPU/memory costs and review files. It does not ingest cloud invoices
or maintain a historical usage model.

| Tool | Main role | Relationship to kube-saver |
|---|---|---|
| kube-saver | Local cost estimates, TUI, HTML snapshots, resource-change plans | Uses present metrics-server samples or estimated fallback |
| [k9s](https://github.com/derailed/k9s) | Terminal cluster navigation and operations | Useful alongside a cost-review tool |
| [Goldilocks](https://github.com/FairwindsOps/goldilocks) | Dashboard for VPA sizing recommendations | Uses VPA's recommendation model rather than kube-saver's snapshot heuristics |
| [VPA](https://github.com/kubernetes/autoscaler/tree/master/vertical-pod-autoscaler) | Resource recommendations and configurable updates | Can run recommendation-only or update modes; not always an automatic mutator |
| [OpenCost](https://github.com/opencost/opencost) | Ongoing Kubernetes cost allocation and cloud-cost monitoring | Open source and self-hostable; provides a broader allocation model |

OpenCost does not require a hosted SaaS account. A metrics stack or cluster
components are different requirements from a hosted service. Consult each
project's current installation docs before comparing deployment requirements.

## Use kube-saver when

- You want a local review of requests versus present usage with configured rates.
- You need a self-contained HTML snapshot for internal review.
- You want local candidate patch commands to review and translate into GitOps.

## Consider a different or complementary workflow when

- You need historical percentiles or ongoing automatic resource adjustments.
- You need cloud billing reconciliation, full infrastructure cost allocation,
  storage/network/GPU costs, or team chargeback.
- You need logs, exec, and cluster lifecycle operations from a terminal.

Reducing requests is not a measured cost saving. Evaluate representative load
and whether the change can reduce billed capacity. See [FAQ](faq.md) and
[safety](safety.md).
