"""kube-saver CLI entry point.

Launches the TUI by default.
"""

import sys


def main() -> int:
    """Launch the kube-saver TUI dashboard."""
    from kube_saver.config import load_config

    try:
        from kube_saver.tui.app import KubeSaverApp
    except ImportError as exc:
        print(f"Error: TUI dependencies missing: {exc}", file=sys.stderr)
        print("Install with: pip install kube-saver", file=sys.stderr)
        return 1

    config = load_config()
    app = KubeSaverApp(config)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
