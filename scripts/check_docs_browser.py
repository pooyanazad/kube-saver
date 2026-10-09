"""Exercise a built documentation site locally; never publish it."""

from __future__ import annotations

import argparse
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import expect, sync_playwright


def check(site: Path, output: Path) -> None:
    """Check navigation, search, keyboard access and narrow layouts."""
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as temp:
        root = Path(temp)
        (root / "kube-saver").symlink_to(site.resolve(), target_is_directory=True)
        handler = partial(SimpleHTTPRequestHandler, directory=str(root))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}/kube-saver/"
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base, wait_until="networkidle")
                page.keyboard.press("Tab")
                assert "Skip to content" in page.locator(":focus").inner_text()
                page.screenshot(path=str(output / "desktop.png"), full_page=True)
                expect(page.locator(".md-search-result__meta")).to_have_text(
                    "Type to start searching", timeout=30000,
                )
                # Material updates search queries on keyup; fill() emits no key events.
                page.get_by_role("textbox", name="Search", exact=True).press_sequentially("metrics-server")
                page.locator(".md-search-result__item").first.wait_for(state="visible")
                assert page.locator(".md-search-result__item").count() > 0
                page.keyboard.press("Escape")
                for slug in (
                    "getting-started", "faq", "safety", "rbac", "gitops",
                    "cli-reference", "configuration", "troubleshooting",
                ):
                    response = page.goto(f"{base}{slug}/")
                    assert response is not None and response.status == 200, slug
                    assert page.locator("h1").count() == 1, slug
                page.set_viewport_size({"width": 390, "height": 844})
                page.goto(f"{base}getting-started/", wait_until="networkidle")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.get_by_role("button", name="Open navigation", exact=True).press("Enter")
                expect(page.locator("#__drawer")).to_be_checked()
                expect(page.get_by_role("button", name="Close navigation", exact=True)).to_have_attribute(
                    "aria-expanded", "true",
                )
                # The active Start section initially occupies the mobile drawer.
                # Use its back control to reach the top-level section list.
                page.locator("label.md-nav__title").filter(has_text="Start").click()
                page.locator("label.md-nav__link").filter(has_text="Understand results").click()
                page.get_by_role("navigation", name="Navigation", exact=True).get_by_role(
                    "link", name="GitOps review workflow", exact=True,
                ).click()
                page.wait_for_url(f"{base}gitops/")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(output / "mobile.png"), full_page=True)
                assert not errors, errors
                browser.close()
            print("PASS: keyboard skip link, working search, eight priority pages, mobile navigation and 390px overflow checks")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    check(args.site, args.output)
