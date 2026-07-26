## Summary

<!--
Briefly describe the purpose of this PR. What problem does it solve?
If the change is visual, a screenshot or screen recording is welcome.
-->

## Related

<!--
Fixes #ISSUE
Relates to #ISSUE
If none, write: None.
-->

None.

## Changes

<!--
List the concrete changes in this PR. Be specific — mention files,
functions, and the logic you added or modified. If the diff is large,
group related changes into a few bullet points.

Example:
- `src/kube_saver/doctor.py` — new `kube-saver doctor` subcommand with six diagnostic checks
- `.github/workflows/ci.yml` — added `smoke-docker` job that builds and runs the image against kind
-->

-

## Checklist

### Before merge
- [ ] `pytest -q` passes (158 tests)
- [ ] `ruff check src tests` passes
- [ ] `mypy src` passes
- [ ] Manual smoke test completed (describe below)

### If applicable
- [ ] CLI help text, error messages, or output format changed — docs updated
- [ ] Breaking change — version bump and migration note included

## Verification

<!--
How did you test this? Commands + expected output. Example:

```
$ docker build -t kube-saver:test .
$ docker run --rm -e KUBECONFIG=/tmp/kubeconfig \
    -v ~/.kube/config:/tmp/kubeconfig:ro \
    kube-saver:test doctor
kubeconfig: /tmp/kubeconfig
  ✓ kubeconfig — found at /tmp/kubeconfig
  ✓ context — active context is 'kind-kind'
  ✓ cluster reachable — server reports v1.33.0
$ echo $?
0
```
-->

```
```

## Release impact

<!--
Will users see any difference? New flags, changed defaults, removed
features, output format changes? If nothing user-facing, write: None.
-->

None.

## Post-merge

<!--
Steps needed after merge: deploy, announce, backport, etc.
If none, write: None.
-->

None.
