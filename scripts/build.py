"""Build step for explainer pages.

Usage:  python build.py <pages-folder> [--force]

1. Copies the shared stylesheet (explainers.css) into the folder.
2. Renders every diagrams/*.d2 to diagrams/*.svg with the explainer theme and fonts
   (only when the .d2 or the theme is newer than the .svg, or with --force).
3. Inlines each rendered SVG into the pages, between
       <!-- d2:NAME "alt text" --> ... <!-- /d2 -->
   so a page is one self-contained file (viewers that block local sub-files still show it).
   A legacy <img src="diagrams/NAME.svg" alt="..."> is converted to that marker.
4. Numbers every chapter, item and sub-item of each page (5, 5-6, 5-6-5) so the reader can
   answer "5-6-5 ok" instead of quoting text. See enumerate_page().
5. Rewrites the sidebar page list between <!-- nav --> and <!-- /nav --> in every page,
   listing all pages that carry <meta name="explainer" content="ORDER|Label">, numbered 01, 02, ...
"""
import html
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
ASSETS = SKILL / "assets"
FONTS = ASSETS / "fonts"
IMPORT_LINE = "...@_theme"
MAX_WIDTH = 762  # the figure box's inner width (800 - 2*18 padding - 2*1 border).
# Diagrams are shown at their real size, so their text matches the page (16 and 13).
# A wider diagram has to be shrunk to fit, and its text shrinks with it.


def find_d2():
    exe = shutil.which("d2")
    if exe:
        return exe
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "d2" / "d2.exe"
    if local.exists():
        return str(local)
    sys.exit("d2 not found. Install it: download the windows-amd64 tar.gz from "
             "https://github.com/d2lang/d2/releases and put d2.exe in %LOCALAPPDATA%\\Programs\\d2\\")


def sync_css(folder: Path):
    src, dst = ASSETS / "explainers.css", folder / "explainers.css"
    if not dst.exists() or dst.read_bytes() != src.read_bytes():
        shutil.copyfile(src, dst)
        print("css      explainers.css updated")


def render(folder: Path, force: bool):
    ddir = folder / "diagrams"
    if not ddir.is_dir():
        return
    theme_src, theme_dst = ASSETS / "theme.d2", ddir / "_theme.d2"
    if not theme_dst.exists() or theme_dst.read_bytes() != theme_src.read_bytes():
        shutil.copyfile(theme_src, theme_dst)
        force = True  # theme changed: re-render everything
    d2 = find_d2()
    fonts = ["--font-regular", FONTS / "OpenSans-Regular.ttf", "--font-bold", FONTS / "OpenSans-Bold.ttf",
             "--font-semibold", FONTS / "OpenSans-SemiBold.ttf", "--font-italic", FONTS / "OpenSans-Italic.ttf",
             "--font-mono", FONTS / "Cousine-Regular.ttf", "--font-mono-bold", FONTS / "Cousine-Bold.ttf"]
    failed = 0
    for src in sorted(ddir.glob("*.d2")):
        if src.name.startswith("_"):
            continue
        text = src.read_text(encoding="utf-8")
        if not text.lstrip().startswith(IMPORT_LINE):
            src.write_text(IMPORT_LINE + "\n\n" + text, encoding="utf-8")
        out = src.with_suffix(".svg")
        if not force and out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
            continue
        cmd = [d2, "--pad", "24", "--omit-version", "--no-xml-tag", *map(str, fonts), src.name, out.name]
        # imports resolve against the working directory, so run inside diagrams/
        r = subprocess.run(cmd, cwd=ddir, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode:
            failed += 1
            errs = [l for l in r.stderr.splitlines() if not l.startswith("info:")]
            print(f"FAILED   {src.name}\n" + "\n".join(errs))
            continue
        print(f"diagram  {src.name} -> {out.name}")
        m = re.search(r'viewBox="0 0 (\d+) (\d+)"', out.read_text(encoding="utf-8"))
        if m and int(m.group(1)) > MAX_WIDTH:
            print(f"WARNING  {out.name} is {m.group(1)}px wide, the box holds {MAX_WIDTH}: its text will shrink. "
                  "Use fewer columns, smaller gaps, shorter labels (two lines), or split it.")
    if failed:
        sys.exit(f"{failed} diagram(s) failed")


LEGACY_IMG = re.compile(r'<img src="diagrams/([\w-]+)\.svg" alt="([^"]*)">')
BLOCK = re.compile(r'<!-- d2:([\w-]+)(?: "([^"]*)")? -->.*?<!-- /d2 -->', re.S)
ARIA = re.compile(r'aria-label="([^"]*)"')


def inline(folder: Path):
    ddir = folder / "diagrams"
    for page in sorted(folder.glob("*.html")):
        src = page.read_text(encoding="utf-8")
        text = LEGACY_IMG.sub(lambda m: f'<!-- d2:{m.group(1)} "{m.group(2)}" --><!-- /d2 -->', src)

        def fill(m):
            name, alt = m.group(1), m.group(2)
            if alt is None:  # older marker without alt: keep the label already in the SVG
                a = ARIA.search(m.group(0))
                alt = a.group(1) if a else ""
            svg_file = ddir / f"{name}.svg"
            if not svg_file.exists():
                print(f"MISSING  {page.name}: diagrams/{name}.svg")
                return m.group(0)
            svg = svg_file.read_text(encoding="utf-8")
            # Give the outer <svg> its real size from the viewBox, so CSS shows it at scale 1.
            vb = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
            size = f'width="{vb.group(1)}" height="{vb.group(2)}" ' if vb else ""
            svg = svg.replace("<svg ", f'<svg {size}role="img" aria-label="{html.escape(alt, quote=True)}" ', 1)
            return f'<!-- d2:{name} "{alt}" -->\n{svg}\n<!-- /d2 -->'

        text = BLOCK.sub(fill, text)
        if text != src:
            page.write_text(text, encoding="utf-8")
            print(f"inline   {page.name}")


# ------------------------------------------------------------------------------------------
# Reference numbers
# ------------------------------------------------------------------------------------------
# One numbering per page. A <section> with an h2 is a chapter (1, 2, 3...); the intro section
# without one is chapter 0. Every block in a chapter is an item (5-1, 5-2...). A collection
# (list, card grid, table, limits, glossary) gets its own item number, and each member gets
# the next level (5-6-1...). Lists nested inside a member go one level deeper (5-6-1-2).
# Labels are spliced into the source at positions bs4 reports, so the rest of the file is
# left byte for byte as written. Old labels are stripped first, so rebuilding is safe.
NUM_SPAN = re.compile(r'<span class="num(?: num-block)?">[^<]*</span>')
CHAPTER_PREFIX = re.compile(r'^\s*\d+\s*·\s*')
COLLECTION_CLASSES = {"grid", "grid2", "compare", "limits", "gloss", "table-box", "flows", "now3"}
TRANSPARENT_CLASSES = {"qgroups"}  # its groups are numbered as items of the chapter itself
SKIP_CLASSES = {"eyebrow"}
START_TAG = re.compile(r'<[A-Za-z][^\s/>]*(?:\s+[^\s=/>]+(?:\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s>]+))?)*\s*/?>')


def _classes(tag):
    return set(tag.get("class") or [])


def _kids(tag):
    return [c for c in tag.children if getattr(c, "name", None)]


def _is_collection(tag):
    return tag.name in ("ul", "ol", "table") or bool(_classes(tag) & COLLECTION_CLASSES)


def _members(tag):
    if tag.name in ("ul", "ol"):
        return [c for c in _kids(tag) if c.name == "li"]
    if tag.name == "table" or "table-box" in _classes(tag):
        table = tag if tag.name == "table" else tag.find("table")
        if table is None:
            return []
        return [tr for tr in table.find_all("tr") if tr.find("td") is not None]
    return _kids(tag)


def _nested_collections(tag):
    """Collections inside a member, not counting ones inside another nested collection or an SVG."""
    found = []
    for child in _kids(tag):
        if child.name in ("svg", "script", "style"):
            continue
        if _is_collection(child):
            found.append(child)
        else:
            found += _nested_collections(child)
    return found


def enumerate_page(text: str) -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("WARNING  bs4 is not installed: pages are not numbered (pip install beautifulsoup4)")
        return text
    text = NUM_SPAN.sub("", text)
    soup = BeautifulSoup(text, "html.parser")
    main = soup.find("main")
    if main is None:
        return text
    line_starts = [0]
    for m in re.finditer("\n", text):
        line_starts.append(m.end())

    def start_of(tag):
        return line_starts[tag.sourceline - 1] + tag.sourcepos

    def after_start(tag):
        pos = start_of(tag)
        m = START_TAG.match(text, pos)
        return m.end() if m else pos

    ops = []  # (start, end, replacement)

    def inline(tag, num):
        """The label goes at the start of the element's own text."""
        target = tag
        if tag.name == "figure":
            target = tag.find("figcaption")
            if target is None:
                return block(tag, num)
        elif tag.name == "details":
            target = tag.find("summary") or tag
        elif tag.name == "tr":
            target = tag.find(["td", "th"]) or tag
        pos = after_start(target)
        ops.append((pos, pos, f'<span class="num">{num}</span>'))

    def block(tag, num):
        """A collection has no text of its own, so its label is a line just above it."""
        pos = start_of(tag)
        ops.append((pos, pos, f'<span class="num num-block">{num}</span>'))

    def number_inside(tag, prefix):
        j = 0
        for coll in _nested_collections(tag):
            for member in _members(coll):
                j += 1
                inline(member, f"{prefix}-{j}")
                number_inside(member, f"{prefix}-{j}")

    def number_item(tag, num):
        if _is_collection(tag):
            block(tag, num)
            for j, member in enumerate(_members(tag), start=1):
                inline(member, f"{num}-{j}")
                number_inside(member, f"{num}-{j}")
        else:
            inline(tag, num)
            number_inside(tag, num)

    sections = [s for s in main.find_all("section") if s.find_parent("section") is None]
    chapter = 0
    ids = {}
    for section in sections:
        heading = section.find("h2", recursive=False)
        if heading is not None:
            chapter += 1
            n = chapter
            if section.get("id"):
                ids[section["id"]] = n
            eyebrow = section.find("span", class_="eyebrow", recursive=False)
            if eyebrow is not None:
                begin = after_start(eyebrow)
                end = text.index("</span>", begin)
                ops.append((begin, end, f"{n} · " + CHAPTER_PREFIX.sub("", text[begin:end])))
        else:
            n = 0
        k = 0
        for child in _kids(section):
            if child.name in ("h2", "script", "style") or _classes(child) & SKIP_CLASSES:
                continue
            if _classes(child) & TRANSPARENT_CLASSES:
                for member in _kids(child):
                    k += 1
                    number_item(member, f"{n}-{k}")
                continue
            k += 1
            number_item(child, f"{n}-{k}")

    # "On this page" links carry the chapter number too.
    aside = soup.find("aside")
    if aside is not None:
        for a in aside.find_all("a", href=True):
            target = a["href"][1:] if a["href"].startswith("#") else None
            if target in ids:
                begin = after_start(a)
                end = text.index("</a>", begin)
                ops.append((begin, end, f"{ids[target]} · " + CHAPTER_PREFIX.sub("", text[begin:end])))

    for begin, end, new in sorted(ops, key=lambda op: (op[0], op[1]), reverse=True):
        text = text[:begin] + new + text[end:]
    return text


def enumerate_pages(folder: Path):
    for page in sorted(folder.glob("*.html")):
        src = page.read_text(encoding="utf-8")
        new = enumerate_page(src)
        if new != src:
            page.write_text(new, encoding="utf-8")
            print(f"numbers  {page.name}")


META = re.compile(r'<meta\s+name="explainer"\s+content="(\d+)\|([^"]+)"\s*/?>', re.I)
NAV = re.compile(r"(<!-- nav -->)(.*?)(<!-- /nav -->)", re.S)


def nav(folder: Path):
    pages = []
    for p in folder.glob("*.html"):
        m = META.search(p.read_text(encoding="utf-8"))
        if m:
            pages.append((int(m.group(1)), m.group(2).strip(), p.name))
    pages.sort()
    for _, _, name in pages:
        path = folder / name
        text = path.read_text(encoding="utf-8")
        current = ' aria-current="page"'
        # Pages are ordered oldest to newest and numbered 01, 02, ... by their position.
        links = "\n".join(
            f'  <a href="{n}"{current if n == name else ""}>{i:02d} · {label}</a>'
            for i, (_, label, n) in enumerate(pages, start=1))
        block = f'\n<nav aria-label="Explainer pages">\n{links}\n</nav>\n'
        new = NAV.sub(lambda m: m.group(1) + block + m.group(3), text)
        if new != text:
            path.write_text(new, encoding="utf-8")
            print(f"nav      {name}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    folder = Path(args[0]).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    sync_css(folder)
    render(folder, "--force" in sys.argv)
    inline(folder)
    enumerate_pages(folder)
    nav(folder)
    print("done")


if __name__ == "__main__":
    main()
