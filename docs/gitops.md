---
title: GitOps review workflow
description: Review kube-saver local resource-change plans, translate approved requests into GitOps manifests, and validate workload behavior before rollout.
---

# Review right-sizing candidates with GitOps

`kube-saver pr-plan` scans the cluster and writes local review files. It does
not open a GitHub pull request, edit your GitOps repository, or apply changes.
The plan's cost reductions are modeled estimates, not verified bill savings.

## Generate and inspect a local plan

Use the same reviewed context for diagnostics and collection:

```bash
export KUBE_SAVER_CONTEXT=staging-cluster
kube-saver doctor --context "$KUBE_SAVER_CONTEXT"
kube-saver pr-plan -d ./pr-files
ls ./pr-files
```

Read `summary.md`, `review.txt`, `README.md`, and `apply-patches.sh`. Plans may
include low, medium, and high confidence candidates. Confidence is a
utilization-ratio heuristic; it is not evidence of historical coverage.
Empty plans can be valid: estimated samples, sidecars, exclusions, differing
sibling requests, or insufficient reducible waste can suppress candidates.
See [recommendation safety](safety.md) before accepting any value.

## Translate reviewed requests into the source of truth

1. Identify the named controller, namespace, and container in the plan. Confirm
   they match the current GitOps-managed workload and scanned cluster.
2. Compare the current sample with historical telemetry, startup demand,
   failover behavior, representative load, and service objectives. Check the
   [pricing assumptions](faq.md#are-the-costs-actual-cloud-charges) independently.
3. In a topic branch of your GitOps repository, edit only the reviewed
   container's CPU or memory **requests** in its manifest, Helm values, or
   Kustomize patch. Preserve other containers, limits, probes, and scheduling
   settings. kube-saver does not locate or update these source files for you.
4. Render and validate with that repository's existing tooling. Open a normal
   pull request containing the before/after values, telemetry window, rollback
   plan, and expected capacity effect. Redact internal names before sharing
   scan outputs publicly.
5. After approval, let your usual GitOps controller deploy to staging. Monitor
   latency, errors, throttling, memory pressure, restarts, and scaling under
   representative load. Roll back through the source repository if needed.

Reducing requests can free scheduling capacity while leaving node count and
cloud charges unchanged. Verify actual billing changes separately over
comparable periods.

## What the generated apply script does

Executing `apply-patches.sh` directly changes the live cluster and may trigger
a rollout; a GitOps controller may later revert that drift. For GitOps-managed
workloads, use the manifest review workflow above.

For a separately approved direct-patch workflow, the script requires
`KUBE_SAVER_APPLY_CONTEXT`, passes that context to each `kubectl patch`, uses
strategic merge patches for named containers in supported built-in controller
kinds, and stops on the first failed command. Earlier successful patches are
not rolled back automatically. Unsupported controller/container targets are
skipped. The script neither grants write RBAC nor verifies workload performance.

See [CLI reference](cli-reference.md#kube-saver-pr-plan) and
[RBAC and authentication](rbac.md) for collection requirements.
