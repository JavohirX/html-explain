"""One visual check of an explainer page.

Usage:  python check.py <page.html> <out-folder>

Saves a screenshot of every <figure> (figure-0.png, figure-1.png, ...) and of the top
of the page (page.png) into <out-folder>. Read those images once, fix what they show,
and don't loop.
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

if len(sys.argv) < 3:
    sys.exit(__doc__)
page, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
out.mkdir(parents=True, exist_ok=True)
with sync_playwright() as pw:
    try:
        browser = pw.chromium.launch(channel="msedge")
    except Exception:
        browser = pw.chromium.launch()
    tab = browser.new_page(viewport={"width": 1100, "height": 1000})
    tab.goto(page.as_uri())
    tab.wait_for_timeout(3000)  # fonts + mermaid
    tab.screenshot(path=str(out / "page.png"))
    for i, fig in enumerate(tab.locator("figure").all()):
        fig.screenshot(path=str(out / f"figure-{i}.png"))
        print(out / f"figure-{i}.png")
    browser.close()
print(out / "page.png")
