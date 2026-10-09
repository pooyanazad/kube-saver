---
title: Troubleshooting Kubernetes scans and reports
description: Diagnose kube-saver authentication, RBAC, missing or stale metrics-server data, empty recommendations,
  partial reports, and installation errors.
---

# Troubleshooting

Common issues and how to fix them. If something is missing here, open an issue.

---

## TUI opens but all values show as estimates

**Cause:** metrics-server is unavailable, so kube-saver fell back to request-based estimates.

**What to do:**

- Check if metrics-server is running:
  ```bash
  kubectl get deployment metrics-server -n kube-system
  ```
- If it is not installed, install it:
  ```bash
  kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
  ```
- If metrics-server is running but kube-saver is not using it, check RBAC, you need `list` and `get` on `metrics.k8s.io` pods and nodes. See [Safety & trust](safety.md#rbac).

Falling back to estimates is not an error, kube-saver is still working. The TUI status bar shows which source is active.

---

## eBPF is not being used

Live eBPF probes are not implemented in this release. The eBPF module only
reports host capabilities and always falls through to metrics-server. Installing
BCC or running kube-saver as root will not enable eBPF metrics yet.

---

## Kubernetes connection fails

**Check in this order:**

1. Is your kubeconfig set?
   ```bash
   echo $KUBECONFIG
   kubectl config current-context
   ```

2. Can you reach the cluster?
   ```bash
   kubectl cluster-info
   ```

3. Does the context match what kube-saver is using?
   ```bash
   KUBE_SAVER_CONTEXT=<name> kube-saver doctor --context <name>
   ```

4. Do you have the required RBAC permissions? See [Safety & trust](safety.md#rbac).

---

## TUI shows blank screen or crashes on startup

**Cause:** Usually a terminal compatibility issue or a missing Textual dependency.

**What to do:**

- Make sure your terminal supports Unicode and at least 256 colors (iTerm2, Alacritty, kitty, GNOME Terminal, Windows Terminal all work).
- Try the non-TUI path first to confirm the tool is working:
  ```bash
  kube-saver report -o /tmp/test.html
  ```
- Reinstall from source to ensure all dependencies are correct:
  ```bash
  pip install -e ".[dev]"
  ```

---

## HTML report looks wrong in my browser

**Cause:** Very old browsers that do not support modern CSS may render incorrectly.

**What to do:**

- Open in a recent version of Chrome, Firefox, Safari, or Edge.
- The report uses only inline CSS and standard HTML, no JavaScript, no external assets. It should work in any browser from 2020 onward.

---

## "Insufficient permissions" or exit code 4

**Cause:** Required RBAC may be missing, or every pod read failed for another
reason. Exit code 4 represents an analysis failure; inspect stderr and `doctor`.

**What to do:**

- Run `kube-saver doctor` to see which specific resource is denied.
- Apply the minimal RBAC manifest from [Safety & trust](safety.md#rbac).
- For read-only namespace-scoped access, use a `Role` + `RoleBinding` and set `namespace_filter` to the allowed namespaces.

---

## Recommended values look too high or too low

**Cause:** The engine uses current-sample CPU × 1.5 and memory × 1.2, minimum
configured absolute and relative floors, and upward output rounding. CLI default
floors are 100m, 128Mi, and half of current requests. It does not model historical peaks.

**What to do:**

- Check sample coverage; estimated samples do not generate right-sizing recommendations.
- For bursty workloads, configure `exclude_annotations` with `kube-saver.io/ignore: "true"` and add that annotation to the pods. The annotation alone is not an automatic exclusion.
- Review the current request and observed usage in the report before applying a plan. The recommendation engine currently uses fixed headroom factors.

---

## Report shows 0% efficiency for all namespaces

**Cause:** Missing or stale samples are represented as estimated zero usage.
A 0% efficiency label can therefore mean missing telemetry, rather than idle
workloads. No minimum-request condition is needed for this fallback.

**What to do:**

- Install metrics-server (see above) to get real usage data.
- With estimates-only mode, efficiency is always 0% because there is no measured usage to compare against. This is expected behavior, not a bug.

---

## "No such file or directory" when running from source

**Cause:** You are not in the repository root, or the virtual environment is not activated.

**What to do:**

```bash
cd /path/to/kube-saver
source .venv/bin/activate
pip install -e ".[dev]"
kube-saver
```

---

## See also

- [Getting started](getting-started.md)
- [Safety & trust](safety.md)
- [CLI reference](cli-reference.md)
