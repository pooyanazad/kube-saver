# Contributing to kube-saver

Thanks for contributing to kube-saver.

This project aims to stay practical, self-contained, and production-oriented. Contributions should improve reliability, clarity, and operator usefulness without adding unnecessary service dependencies.

## Documentation

Before opening an issue or PR, check the docs:

- **[Getting started](docs/getting-started.md)** — install, first run, environment setup
- **[CLI reference](docs/cli-reference.md)** — every command and flag
- **[Configuration](docs/configuration.md)** — config keys and environment variables
- **[Architecture](docs/architecture.md)** — module map and data flow
- **[Troubleshooting](docs/troubleshooting.md)** — common issues and fixes
- **[Comparison](docs/comparison.md)** — vs k9s, Goldilocks, VPA, Kubecost
- **[Safety & trust](docs/safety.md)** — RBAC, recommendation boundaries, trust model

## Principles

- Keep the tool self-contained where possible.
- Prefer small, focused changes over broad rewrites.
- Preserve existing CLI and output behavior unless a change is intentional and documented.
- Verify changes with linting, typing, and tests before opening a pull request.
- Avoid introducing maintainer-owned external service requirements for core functionality.

## Development setup

```bash
git clone https://github.com/pooyanazad/kube-saver.git
cd kube-saver
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Project layout

- `src/kube_saver/collectors/` — Kubernetes and runtime data collection
- `src/kube_saver/analyzers/` — waste, health, alerts, and cost analysis
- `src/kube_saver/recommenders/` — recommendation generation
- `src/kube_saver/exporters/` — reports, notifications, local PR plans, structured output
- `src/kube_saver/tui/` — Textual application and data loading
- `src/kube_saver/server.py` — read-only HTTP API
- `tests/` — automated test suite

## Versioning

kube-saver uses a single source of truth for the application version:

- `src/kube_saver/version.py`

When preparing a release, update `VERSION` in that file first. Package metadata, CLI output, TUI status text, and API versioning are wired to that source.

## Quality checks

Run all required checks before submitting a change:

```bash
source .venv/bin/activate
ruff check src tests --no-cache
mypy src
pytest tests -q
python -m build --sdist --wheel
```

If your change affects Docker packaging, also verify:

```bash
docker build -t kube-saver:local .
docker run --rm kube-saver:local version
```

## Pull requests

Only the following contribution types are expected to be approved:

- changes that address an existing open issue
- critical bug fixes that protect correctness, reliability, or release quality

Pull requests outside those categories may be closed without merge.

Please keep pull requests:

- focused on one logical change
- clearly titled
- backed by updated tests when behavior changes
- small enough to review comfortably

A good pull request description should explain:

- what changed
- why it changed
- how it was verified
- any operational or release impact

## Coding guidelines

- Match the existing code style and naming.
- Keep public behavior stable unless there is a good reason to change it.
- Prefer explicit, readable code over clever code.
- Add or update tests for bug fixes and user-visible behavior changes.
- Keep release and packaging behavior reproducible.

## Reporting issues

Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.yml) when opening an issue. It captures the version, cluster type, command, and error output needed to reproduce the problem.

For questions, use the [question template](.github/ISSUE_TEMPLATE/question.yml) or start a [GitHub Discussion](https://github.com/pooyanazad/kube-saver/discussions).

When opening an issue, include:

- kube-saver version (`kube-saver version`)
- Python version
- Kubernetes context/environment
- exact command used
- expected behavior
- actual behavior
- relevant logs or screenshots

## Agent and automation

kube-saver supports programmatic use from Python scripts and CI pipelines. See:

- [CLI reference](docs/cli-reference.md) for all commands and exit codes
- [Getting started](docs/getting-started.md#5-daily--ci-use) for CI examples
- [JSON output helpers](docs/cli-reference.md#python-helpers) for embedding in automation

## Security

Do not include secrets, kubeconfig credentials, tokens, or sensitive cluster data in issues or pull requests.

If you discover a security-sensitive problem, report it privately through the repository owner instead of posting full exploit details publicly.
