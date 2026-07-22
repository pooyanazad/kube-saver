"""Capture Textual screenshots of the kube-saver TUI for docs/demo use.

Usage:
    python scripts/capture_tui.py [screen] [out.svg [out.png]]

Screens:
    dashboard         default; the namespace overview (key 1)
    cost              cost breakdown view (key 2)
    recommendations   actionable recommendations (key 3)
    namespace         detail view for the first namespace (Enter on a row)
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Make repo importable when run from anywhere
repo_root = Path(__file__).resolve().parent
sys.path.insert(0, str(repo_root))


async def _load_and_render(app, screen, config) -> None:
    """Eagerly load data on the main thread and refresh visible widgets."""
    from kube_saver.tui.data import load_data as _load_data  # noqa: E402
    from kube_saver.tui.app import SummaryBar  # noqa: E402

    new_data = _load_data(config)
    app._data = new_data
    screen.data = new_data
    try:
        screen.query_one(SummaryBar).set_data(new_data)
    except Exception:
        pass
    for attr in ("_refresh_table", "_refresh_alerts", "_refresh_status"):
        ref = getattr(screen, attr, None)
        if callable(ref):
            try:
                ref()
            except Exception:
                pass


async def capture_svg(out_svg: Path, screen_name: str = "dashboard") -> None:
    from kube_saver.config import load_config  # noqa: E402
    from kube_saver.tui.app import KubeSaverApp  # noqa: E402

    config = load_config()
    app = KubeSaverApp(config=config)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause(0.5)
        await _load_and_render(app, app.screen, config)
        await pilot.pause(0.3)

        if screen_name == "dashboard":
            pass  # already there
        elif screen_name == "cost":
            await pilot.press("2")
            await pilot.pause(0.4)
            await _load_and_render(app, app.screen, config)
            await pilot.pause(0.3)
        elif screen_name == "recommendations":
            await pilot.press("3")
            await pilot.pause(0.4)
            await _load_and_render(app, app.screen, config)
            await pilot.pause(0.3)
        elif screen_name == "namespace":
            await pilot.press("enter")
            await pilot.pause(0.4)
            await _load_and_render(app, app.screen, config)
            await pilot.pause(0.3)
        else:
            raise SystemExit(f"unknown screen: {screen_name}")

        app.save_screenshot(str(out_svg))


async def render_png(svg_path: Path, png_path: Path) -> None:
    from playwright.async_api import async_playwright  # type: ignore

    html = f"""<!doctype html>
    <html><head><meta charset='utf-8'>
    <style>
      html, body {{ margin: 0; padding: 0; background: #1e1e1e; }}
      svg {{ display: block; }}
    </style>
    </head><body>{svg_path.read_text()}</body></html>"""
    host_html = svg_path.with_suffix(".host.html")
    host_html.write_text(html)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(
                viewport={"width": 1750, "height": 1100},
            )
            await page.goto(f"file://{host_html.resolve()}")
            await page.wait_for_load_state("networkidle")
            await page.add_style_tag(
                content="* { font-family: monospace !important; }"
            )
            await page.screenshot(path=str(png_path), full_page=True)
            await browser.close()
    finally:
        host_html.unlink(missing_ok=True)


async def main() -> None:
    screen_name = sys.argv[1] if len(sys.argv) > 1 else "dashboard"
    if screen_name in {"-h", "--help"}:
        print(__doc__)
        return
    if screen_name.endswith(".svg") or screen_name.endswith(".png"):
        out_svg = Path(sys.argv[1])
        out_png = Path(sys.argv[2]) if len(sys.argv) > 2 else out_svg.with_suffix(".png")
        screen_name = "dashboard"
    else:
        out_svg = (
            Path(sys.argv[2]) if len(sys.argv) > 2
            else Path(f"docs/screenshots/{screen_name}.svg")
        )
        out_png = (
            Path(sys.argv[3]) if len(sys.argv) > 3
            else out_svg.with_suffix(".png")
        )

    out_svg.parent.mkdir(parents=True, exist_ok=True)
    await capture_svg(out_svg, screen_name)
    print(f"saved svg to {out_svg.resolve()}")
    await render_png(out_svg, out_png)
    print(f"saved png to {out_png.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())