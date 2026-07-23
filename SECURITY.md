# Security Policy

kube-saver is a read-only CLI tool that queries your Kubernetes cluster metadata
and cost estimates. It does not send data anywhere, has no server component, and
requires no authentication beyond your existing kubeconfig.

## Supported Versions

Only the latest stable release receives security updates.

| Version | Supported          |
| ------- | ------------------ |
| 1.x     | :white_check_mark: |
| < 1.0   | :x:                |

## What we consider a security vulnerability

- Data exfiltration from the cluster (kube-saver reading or leaking secrets,
  credentials, or private config)
- Arbitrary code execution via malicious input, config files, or plugin loading
- Privilege escalation via RBAC misconfiguration introduced by kube-saver's
  recommendations

**Not** security vulnerabilities:
- High resource usage on large clusters (use resource limits)
- Information disclosure about resource waste (by design — kube-saver's purpose)
- Denial of service via a misconfigured or unresponsive metrics-server
  (kube-saver handles this gracefully and falls back to estimates)

## How to report a vulnerability

1. **Do not open a public GitHub issue** for a security vulnerability.
2. Send a private report via one of:
   - GitHub **Private vulnerability reporting** (recommended): go to
     `https://github.com/pooyanazad/kube-saver/security/advisories/new`
   - Email: **TODO: Add security contact email**

Please include:
- kube-saver version
- Kubernetes environment (kind, EKS, GKE, etc.)
- Steps to reproduce
- Any affected config files or manifests

## Expected response time

- **Initial acknowledgment**: within 48 hours
- **Severity assessment**: within 5 business days
- **Fix timeline**: depends on severity — critical issues get an immediate patch;
  low-severity issues are addressed in the next scheduled release

## Scope

kube-saver uses your existing kubeconfig credentials. The security of those
credentials is outside kube-saver's scope — protect your kubeconfig as you
would any other sensitive credential.

kube-saver makes no network requests except to the Kubernetes API server
specified in your kubeconfig context. It does not contact any external service
except (optionally) the public AWS EC2 pricing API when using real pricing.
