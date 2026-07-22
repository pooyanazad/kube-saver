# Troubleshooting

Common issues and how to fix them. If something is missing here, open an issue.

---

## TUI opens but all values show as estimates

**Cause:** Neither eBPF nor metrics-server is available, so kube-saver fell back to request-based estimates.

**What to do:**

- Check if metrics-server is running:
  ```bash
  kubectl get deployment metrics-server -n kube-system
  ```
- If it is not installed, install it:
  ```bash
  kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
  ```
- If metrics-server is running but kube-saver is not using it, check RBAC — you need `list` and `get` on `metrics.k8s.io` pods and nodes. See [Safety & trust](safety.md#rbac).

Falling back to estimates is not an error — kube-saver is still working. The TUI status bar shows which source is active.

---

## eBPF is not being used

**Cause:** BCC bindings are not installed, or the process does not have the required kernel capabilities.

**What to do:**

- Install BCC:
  ```bash
  pip install "kube-saver[ebpf]"
  ```
  This requires `bcc-tools` and kernel headers on the host.
- Run with root or the required capabilities:
  ```bash
  sudo kube-saver
  ```
- Check that `tracefs` and `debugfs` are mounted:
  ```bash
  mount | grep -E "tracefs|debugfs"
  ```
- If running inside a container, the container needs `privileged: true` or explicit `SYS_ADMIN` / `SYS_PTRACE` capabilities, plus the host's `/sys/kernel/debug` and `/sys/kernel/tracing` mounted.

If eBPF is not available, kube-saver falls back to metrics-server automatically. This is safe and expected.

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
   kube-saver --context <name>
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
- The report uses only inline CSS and standard HTML — no JavaScript, no external assets. It should work in any browser from 2020 onward.

---

## "Insufficient permissions" or exit code 4

**Cause:** Your kubeconfig identity does not have the required RBAC permissions.

**What to do:**

- Run `kube-saver doctor` to see which specific resource is denied.
- Apply the minimal RBAC manifest from [Safety & trust](safety.md#rbac).
- For read-only namespace-scoped access, use a `Role` + `RoleBinding` instead of a `ClusterRole`.

---

## Recommended values look too high or too low

**Cause:** The recommendation engine uses a configurable headroom buffer (default: 20%) and a minimum resource floor.

**What to do:**

- Check which runtime source is active — estimates are less accurate than metrics-server or eBPF.
- If a workload is intentionally bursty, annotate it with `kube-saver.io/ignore: "true"` to exclude it from recommendations.
- Adjust the headroom buffer in config if your workloads need more or less margin:
  ```yaml
  recommendations:
    headroom_buffer_ratio: 0.3   # 30% headroom instead of 20%
  ```

---

## Report shows 0% efficiency for all namespaces

**Cause:** This means kube-saver detected zero runtime usage for every pod. This happens when:

- metrics-server is not running, AND
- eBPF is not available, AND
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
