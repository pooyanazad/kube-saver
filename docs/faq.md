# Kubernetes cost estimation: kube-saver FAQ

## What is kube-saver?

kube-saver is an MIT-licensed Kubernetes resource-cost analyzer with a Python CLI
and terminal dashboard. It reads cluster resource requests and metrics-server
usage and generates cost estimates, HTML reports, local notifications, and
resource-change plans.

## Are the costs actual cloud charges?

No. The pricing engine models CPU and memory using configurable hourly rates:

```text
monthly estimate = 730 * (
    CPU millicores / 1000 * CPU rate per core-hour
    + memory bytes / 1024**3 * memory rate per GiB-hour
)
```

The configuration key is named `memory_per_gb_hour_usd`, but the implementation
uses 1024**3 bytes (GiB). Default provider rates are bundled assumptions, not
live price quotes. See [configuration](configuration.md) to supply your own rates.

For illustration only, 500m CPU and 1 GiB at $0.040/core-hour and $0.005/GiB-hour
produce `730 * (0.5 * 0.040 + 1 * 0.005) = $18.25/month`. This is model arithmetic,
not a benchmark or a prediction of bill savings.

The model does not ingest cloud invoices or account for all storage, network,
GPU, control-plane, discounts, or commitment costs. Reducing requests does not
necessarily reduce node count or the cloud bill.

## Does kube-saver work without metrics-server?

It runs with estimated samples and does not generate actionable right-sizing
recommendations from those samples. Missing usage is represented as zero in the
current analyzer, so displayed waste may equal all requested capacity. A 0%
efficiency label in this mode does not prove that a workload is idle.

Even when some metrics are available, check coverage: a missing or stale sample
for an individual pod is treated as estimated. The default maximum sample age
is 300 seconds. `doctor` probes Metrics API availability, but does not verify
coverage or freshness for every pod. Partial pod scans warn on stderr, include
a notice in HTML, and set `degraded` in report JSON. A fully failed pod scan
exits with code 4 instead of writing an empty successful report. See [troubleshooting](troubleshooting.md).

## Does it collect historical usage or eBPF metrics?

The current recommendation path uses present metrics-server samples. It does not
build a historical peak or percentile model. The eBPF module performs capability
detection only; live probes are not implemented.

## Does it change my cluster or open pull requests?

Scanning and generating files do not change workloads. `kube-saver pr-plan`
writes local review files and a shell script with `kubectl patch` commands.
Running that script yourself changes the cluster. It does not update your GitOps
source of truth or create a GitHub PR. Translate reviewed changes into your
managed manifests when using GitOps.

## How reliable are recommendations?

They are candidates for investigation, based on current samples. The engine
skips workloads with estimated, excluded, or multi-container collected siblings.
It uses CPU × 1.5 and memory × 1.2, rounding upward. CLI defaults also retain
100m CPU, 128Mi memory, and half of each current request. Absolute minimums
and relative floors are configurable; aggressive mode skips relative floors.
Workload consolidation considers all collected sibling samples, including busy
replicas without independent candidates. This does not protect against future
peaks or prove coverage of replicas outside the snapshot. Confidence labels are utilization-ratio heuristics,
not statistical confidence intervals. See [safety](safety.md).

## Can it run offline?

Generated HTML reports can be opened offline. Live scans need Kubernetes API
access and credential acquisition may require other network access, depending
on your kubeconfig. There is no required hosted kube-saver account or service.
Installation also requires packages unless they are already available locally.

## How does it differ from OpenCost or VPA?

kube-saver focuses on local snapshots and portable review files. OpenCost provides
ongoing cost allocation and cloud-cost integrations. Goldilocks uses VPA
recommendations; VPA has configurable recommendation and update modes. These are
different data and operational models. See [comparison](comparison.md).
