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

**Cause:** Your kubeconfig identity does not have the required RBAC permissions.

**What to do:**

- Run `kube-saver doctor` to see which specific resource is denied.
- Apply the minimal RBAC manifest from [Safety & trust](safety.md#rbac).
- For read-only namespace-scoped access, use a `Role` + `RoleBinding` and set `namespace_filter` to the allowed namespaces.

---

## Recommended values look too high or too low

**Cause:** The recommendation engine uses a configurable headroom buffer (default: 20%) and a minimum resource floor.

**What to do:**

- Check which runtime source is active; estimates are less accurate than metrics-server.
- If a workload is intentionally bursty, annotate it with `kube-saver.io/ignore: "true"` to exclude it from recommendations.
- Review the current request and observed usage in the report before applying a plan. The recommendation engine currently uses fixed headroom factors.

---

## Report shows 0% efficiency for all namespaces

**Cause:** This means kube-saver detected zero runtime usage for every pod. This happens when:

- metrics-server is not running, AND
- the cluster has no pods making requests above the minimum floor

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
