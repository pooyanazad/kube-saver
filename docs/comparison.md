# Comparison — kube-saver vs alternatives

kube-saver is not a replacement for every Kubernetes tool. It occupies a specific niche: **dollar-first, offline, shareable cost visibility**. This document explains where it fits relative to the tools teams usually compare it to.

---

## Head-to-head table

| Feature | kube-saver | k9s | Goldilocks | VPA | Kubecost / OpenCost |
|---|---|---|---|---|---|
| **Cost in dollars** | ✅ | ❌ | ❌ | ❌ | ✅ |
| **Fully offline** | ✅ | ✅ | ✅ | ✅ | ❌ (needs Prometheus) |
| **Self-contained HTML** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **k9s-style TUI** | ✅ | ✅ | ❌ | ❌ | ❌ |
| **Right-sizing recs** | ✅ | ❌ | ✅ | ✅ (live) | partial |
| **Local PR plan** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **No hosted service** | ✅ | ✅ | ✅ | ✅ | ❌ (SaaS option) |
| **Markdown alerts** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Multi-currency** | ✅ | ❌ | ❌ | ❌ | partial |

---

## kube-saver vs k9s

| | kube-saver | k9s |
|---|---|---|
| **Focus** | Cost visibility and recommendations | Cluster navigation and operations |
| **Dollar costs** | Yes — every view shows monthly cost | No |
| **Pod operations** | Read-only, recommendation-focused | Full pod lifecycle (logs, exec, delete) |
| **When to use** | "Where is our money going?" | "What is running right now and can I fix it?" |

k9s is an outstanding cluster navigator. kube-saver does not replace it. They complement each other: use k9s to operate, use kube-saver to audit cost.

---

## kube-saver vs Goldilocks

| | kube-saver | Goldilocks |
|---|---|---|
| **Focus** | Cost visibility + recommendations | Right-sizing recommendations only |
| **Dollar cost** | Yes | No |
| **Outputs** | HTML report, PR plan, TUI, alerts, JSON, Prometheus | Dashboard, VPA objects |
| **Offline** | Fully offline | Fully offline |
| **Data source** | eBPF → metrics-server → estimates | VPA recommender |

Goldilocks is a good right-sizing tool. kube-saver gives you the same recommendations **plus** dollar amounts, a self-contained report, and a PR plan you can drop into a CI pipeline.

---

## kube-saver vs VPA (Vertical Pod Autoscaler)

| | kube-saver | VPA |
|---|---|---|
| **Focus** | Audit and recommend | Live auto-resize |
| **Changes resources?** | No — generates a plan you review | Yes — mutates pod specs in-cluster |
| **Dollar cost** | Yes | No |
| **Risk model** | Zero — read-only, you apply changes | Medium — can disrupt workloads |
| **Self-contained output** | Yes | No — cluster-bound |

VPA and kube-saver work together: kube-saver shows you the dollar problem and generates a plan; VPA handles the live autoscaling once you are confident.

---

## kube-saver vs Kubecost / OpenCost

| | kube-saver | Kubecost / OpenCost |
|---|---|---|
| **Focus** | Self-contained local cost audit | Cluster-level cost allocation |
| **Infrastructure needed** | None | Prometheus (OpenCost) or hosted service (Kubecost) |
| **Cloud billing data** | No | Yes (when configured) |
| **Self-contained report** | Yes | Partial (Kubecost dashboard) |
| **Offline use** | Fully offline | Partially offline (OpenCost); Kubecost SaaS needs internet |
| **Cost model** | Resource-based estimate | Real cloud billing integration (when configured) |

Kubecost is the better tool if you need real cloud billing data and an always-on dashboard. kube-saver is the better tool if you want a fast, local, shareable snapshot that works in five minutes without any external infrastructure.

---

## When to use kube-saver

- You want a quick, honest dollar number for your cluster without setting up Prometheus
- You need a self-contained report you can email to a stakeholder
- You want right-sizing recommendations with a PR-ready plan
- You want to check cost in CI without adding a hosted service dependency
- You are evaluating whether your cluster needs more serious cost tooling

## When to use something else

- You need live autoscaling: use VPA or Karpenter
- You need real cloud billing data: use Kubecost
- You need a full cluster dashboard with logs, exec, and port-forward: use k9s or Lens
- You need multi-cluster fleet-wide cost reporting with team chargeback: use a commercial platform

---

## See also

- [Architecture](architecture.md)
- [Safety & trust](safety.md)
- [Getting started](getting-started.md)
