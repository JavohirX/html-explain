"""Build step for explainer pages.

Usage:  python build.py <pages-folder> [--force]

1. Copies the shared stylesheet (explainers.css) and script (explainers.js) into the folder.
   Tests (.quiz) and questions (.choice) get a stable id and a one-time shuffle (interactive()).
2. Renders every diagrams/*.d2 to diagrams/*.svg with the explainer theme and fonts
   (only when the .d2 or the theme is newer than the .svg, or with --force).
3. Inlines each rendered SVG into the pages, between
       <!-- d2:NAME "alt text" --> ... <!-- /d2 -->
   so a page is one self-contained file (viewers that block local sub-files still show it).
   A legacy <img src="diagrams/NAME.svg" alt="..."> is converted to that marker.
4. Writes the summary at the top of each page from its plan (see pages.py), between
   <!-- summary --> and <!-- /summary -->, and checks the plan's rules: one job per chapter,
   at most 3 new terms, 1-2 check questions. Each broken rule is a WARNING line.
5. Numbers every chapter, item and sub-item of each page (5, 5-6, 5-6-5) so the reader can
   answer "5-6-5 ok" instead of quoting text, and labels every block that isn't a plain paragraph
   with what it is: "6-8 DECIDED", "6-6 RULES what every setting declares", "4-6 OVERVIEW <job>".
   Pictures also get a key under them: what each colour and line style used in them means.
   See enumerate_page().
   Before numbering, every <pre class="code" data-lang="..."> gets its code colors (color_pages);
   after it, every <b class="red"> is listed in a "Don't miss" box at the top (dontmiss).
6. Rewrites the sidebar page list between <!-- nav --> and <!-- /nav --> in every page,
   listing all pages that carry <meta name="explainer" content="ORDER|Label">, numbered 01, 02, ...
"""
import html
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from pages import (FIGURE_TYPES, chapters, figure_key, figure_plan, is_box, is_picture, lint, ordered_pages,
                   read_plan, role_label, summary_html)

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
    for name in ("explainers.css", "explainers.js"):
        src, dst = ASSETS / name, folder / name
        if not dst.exists() or dst.read_bytes() != src.read_bytes():
            shutil.copyfile(src, dst)
            print(f"asset    {name} updated")


# ------------------------------------------------------------------------------------------
# Tests and questions answered in the page (explainers.js runs them and remembers the answers).
#   <div class="quiz" data-role="turn|test"> <p class="q">…</p> <ul class="opts">
#     <li>option<span class="why">why it's wrong</span></li> <li class="right">…<span class="why">…</span></li> …
#   <div class="choice" data-role="question"> <p class="q">…</p> options as <ul class="opts"> or a
#     .table-box (one row per option); the recommended one has class "rec"; <p class="rec-why"> says why.
#   <div class="answer-field" data-role="question" data-placeholder="…"> <p>what to write</p> </div>
# Each block gets a stable id the first time, and its options are shuffled once, at that moment,
# so the right answer or the recommendation isn't always first. After that the order stays.
# ------------------------------------------------------------------------------------------
QBLOCK = re.compile(r'<div class="(quiz|choice|answer-field)"([^>]*)>')
DIV_TAG = re.compile(r"<div\b|</div>")


def _block_end(text: str, start: int) -> int:
    depth = 0
    for m in DIV_TAG.finditer(text, start):
        depth += 1 if m.group(0) == "<div" else -1
        if depth == 0:
            return m.end()
    return len(text)


OPTION_LISTS = (('ul class="opts"', "li"), ("tbody", "tr"))
KEY_OPTION = re.compile(r'<(?:li|tr) class="(?:right|rec)"')


def _options(block: str):
    """(match of the option list's body, its options, their indent), or None."""
    for open_tag, item in OPTION_LISTS:
        m = re.search(rf'(<{open_tag}>)(.*?)(\s*</{open_tag.split()[0]}>)', block, re.S)
        if m:
            return m, re.findall(rf"<{item}\b.*?</{item}>", m.group(2), re.S), re.match(r"\s*", m.group(2)).group(0)
    return None


def _key_place(block: str) -> int | None:
    """Where the right answer (a test) or my recommendation (a question) sits, counted from 0."""
    found = _options(block)
    if not found:
        return None
    places = [i for i, it in enumerate(found[1]) if KEY_OPTION.match(it)]
    return places[0] if len(places) == 1 else None


def _shuffle_once(block: str, seed: str, used: dict) -> str:
    """Shuffle the options once, when the block gets its id. The right or recommended option goes to the
    place used least so far on this page (ties drawn at random), so it isn't "usually the first" by chance.
    The others are shuffled around it. `used` counts places on this page: {place: times}."""
    import random
    rnd = random.Random(seed)
    found = _options(block)
    if not found or len(found[1]) < 2:
        return block
    m, items, indent = found
    keys = [i for i, it in enumerate(items) if KEY_OPTION.match(it)]
    rest = [it for i, it in enumerate(items) if i not in keys]
    rnd.shuffle(rest)
    if len(keys) == 1:
        least = min(used.get(p, 0) for p in range(len(items)))
        place = rnd.choice([p for p in range(len(items)) if used.get(p, 0) == least])
        used[place] = used.get(place, 0) + 1
        rest.insert(place, items[keys[0]])
    return block[:m.start(2)] + "".join(indent + it for it in rest) + block[m.end(2):]


def _qtext(block: str) -> str:
    m = re.search(r'<p class="q">(.*?)</p>', block, re.S) or re.search(r"<p>(.*?)</p>", block, re.S)
    raw = m.group(1) if m else block
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", raw)).split())


def interactive(folder: Path):
    import hashlib
    for _, _, page in ordered_pages(folder):
        text = page.read_text(encoding="utf-8")
        new = text
        if 'src="explainers.js"' not in new:
            link = '<link rel="stylesheet" href="explainers.css">'
            if link in new:
                new = new.replace(link, link + '\n<script src="explainers.js" defer></script>', 1)
            else:
                print(f"WARNING  {page.name}: no explainers.css link, so explainers.js isn't added")
        used: set[str] = set(re.findall(r'<div class="(?:quiz|choice|answer-field)"[^>]*\bid="([^"]+)"', new))
        places: dict = {}  # where the right or recommended option sits, over this page's blocks so far
        pos = 0
        while True:
            m = QBLOCK.search(new, pos)
            if not m:
                break
            kind, attrs = m.group(1), m.group(2)
            end = _block_end(new, m.start())
            block = new[m.start():end]
            line = new.count("\n", 0, m.start()) + 1
            where = f"{page.name}:{line} ({kind})"
            if 'id="' not in attrs:
                base = {"quiz": "t-", "choice": "q-", "answer-field": "n-"}[kind]
                base += hashlib.sha1(_qtext(block).encode("utf-8")).hexdigest()[:8]
                qid, k = base, 2
                while qid in used:
                    qid, k = f"{base}-{k}", k + 1
                used.add(qid)
                block = block.replace(m.group(0), f'<div class="{kind}" id="{qid}"{attrs}>', 1)
                if kind != "answer-field":
                    block = _shuffle_once(block, qid, places)
            elif _key_place(block) is not None:
                places[_key_place(block)] = places.get(_key_place(block), 0) + 1
            # the rules each kind must follow
            role = re.search(r'data-role="([^"]+)"', attrs)
            role = role.group(1) if role else None
            if kind == "quiz":
                opts = re.findall(r"<li\b", block)
                if role not in ("turn", "test"):
                    print(f'WARNING  {where}: a test needs data-role="turn" (before the fix) or "test"')
                if len(opts) < 3:
                    print(f"WARNING  {where}: a test needs at least 3 options, has {len(opts)}")
                if len(re.findall(r'<li class="right"', block)) != 1:
                    print(f'WARNING  {where}: a test needs exactly one <li class="right">')
                if block.count('class="why"') != len(opts):
                    print(f'WARNING  {where}: every option needs its <span class="why">')
                # the longest option is the right one: a reader learns that, and stops thinking
                sizes = []
                for li in re.findall(r"<li\b([^>]*)>(.*?)</li>", block, re.S):
                    own = re.sub(r'<span class="(?:why|num)">.*?</span>', "", li[1], flags=re.S)
                    sizes.append(('class="right"' in li[0], len(html.unescape(re.sub(r"<[^>]+>", "", own)).strip())))
                wrong = [n for r, n in sizes if not r]
                right = [n for r, n in sizes if r]
                if right and wrong and right[0] > 30 and right[0] > 1.25 * max(wrong):
                    print(f"WARNING  {where}: the right option is much the longest ({right[0]} characters, the "
                          f"others at most {max(wrong)}): shorten it or give the wrong ones the same detail")
            elif kind == "choice":
                if role != "question":
                    print(f'WARNING  {where}: a question needs data-role="question"')
                if len(re.findall(r'<(?:li|tr) class="rec"', block)) != 1:
                    print(f'WARNING  {where}: a question needs exactly one option with class "rec"')
                if 'class="rec-why"' not in block:
                    print(f'WARNING  {where}: a question needs <p class="rec-why">: why I recommend it')
                if re.search(r"\bDefault\b", re.sub(r'<p class="rec-why">.*?</p>', "", block, flags=re.S)):
                    print(f"WARNING  {where}: \"Default\" shows the recommendation before the reader picks")
            new = new[:m.start()] + block + new[end:]
            pos = m.start() + len(block)
        if new != text:
            page.write_text(new, encoding="utf-8")
            print(f"answers  {page.name}")


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
LABEL_LINE = re.compile(r'<span class="label-line">(?:<span class="[\w-]+">[^<]*</span>)*</span>')
LABEL_PARTS = re.compile(r'<span class="lbl-(?:role|key)">[^<]*</span>')
CLASS_USE = re.compile(r'class:\s*(\[[^\]]*\]|[\w-]+)')
# What each theme class means, for the key under a picture. Only the classes a picture uses are
# listed. A picture's plan entry can say what a class means in that picture: "key": {"green": "a commit"}.
KEY = [("rust", "rust box", None), ("green", "green box", "our program"),
       ("blue", "blue box", "another company's system"), ("bad", "red box", "a mistake, or what must not happen"),
       ("zone", "dashed frame", "a boundary"), ("accent", "thick rust arrow", "the path to follow"),
       ("danger", "red arrow", "what goes wrong"), ("bg", "dashed arrow", "happens later, or by itself")]


def picture_key(d2_file: Path, entry: dict) -> str:
    """'Key: rust box: new in this chapter · dashed arrow: …' for the classes the diagram uses."""
    if not d2_file.exists():
        return ""
    used = set()
    for m in CLASS_USE.finditer(d2_file.read_text(encoding="utf-8")):
        used |= {c.strip() for c in m.group(1).strip("[]").split(";")}
    own = entry.get("key", {})
    rust = "new in this chapter" if entry.get("type") == "overview" else "what this picture is about"
    parts = [f"{name}: {own.get(cls) or meaning or rust}" for cls, name, meaning in KEY if cls in used]
    return "Key: " + " · ".join(parts) + "." if parts else ""
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


def enumerate_page(text: str, folder: Path | None = None) -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("WARNING  bs4 is not installed: pages are not numbered (pip install beautifulsoup4)")
        return text
    try:
        plan = read_plan(text)
    except ValueError:
        plan = None
    text = LABEL_LINE.sub("", text)
    text = LABEL_PARTS.sub("", text)
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
    fig_plan: dict = {}  # the current chapter's pictures, from the plan

    def esc(s):
        return html.escape(s, quote=False)

    def label_line(pos, num, label):
        parts = f'<span class="num">{num}</span>'
        if label:
            role, name = label
            parts += f'<span class="lbl-role">{esc(role)}</span>'
            if name:
                parts += f'<span class="lbl-text">{esc(name)}</span>'
        ops.append((pos, pos, f'<span class="label-line">{parts}</span>'))

    def inline(tag, num):
        """The number goes at the start of the element's own text."""
        target = tag
        role = ""
        if tag.name == "figure":
            target = tag.find("figcaption")
            if target is None:
                return block(tag, num)
        elif tag.name == "details":
            target = tag.find("summary") or tag
            if "fn" in _classes(tag) and not target.get_text().strip().startswith("Check:"):
                role = '<span class="lbl-role">Footnote</span>'
        elif tag.name == "tr":
            target = tag.find(["td", "th"]) or tag
        pos = after_start(target)
        ops.append((pos, pos, f'<span class="num">{num}</span>{role}'))

    def block(tag, num):
        """A collection has no text of its own, so its label is a line just above it."""
        label_line(start_of(tag), num, role_label(tag))

    def labelled(tag, num):
        """A box or a figure: the label is the first line inside it. Pictures get a key in the caption."""
        label_line(after_start(tag), num, role_label(tag, fig_plan))
        if tag.name == "figure" and is_picture(tag) and folder is not None:
            entry = fig_plan.get(figure_key(tag), {})
            key = picture_key(folder / "diagrams" / f"{figure_key(tag)}.d2", entry)
            caption = tag.find("figcaption")
            if key and caption is not None:
                end = text.index("</figcaption>", after_start(caption))
                ops.append((end, end, f'<span class="lbl-key">{esc(key)}</span>'))

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
        elif is_box(tag) or (tag.name == "figure" and (is_picture(tag) or tag.get("data-role"))):
            labelled(tag, num)
            number_inside(tag, num)
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
        fig_plan = figure_plan(plan, section.get("id"))
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
        new = enumerate_page(src, folder)
        if new != src:
            page.write_text(new, encoding="utf-8")
            print(f"numbers  {page.name}")


SUMMARY = re.compile(r"(<!-- summary -->)(.*?)(<!-- /summary -->)", re.S)


def summarize(folder: Path):
    """Every page gets a summary at the top, written from its plan. Pages without a plan are flagged."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("WARNING  bs4 is not installed: no summaries (pip install beautifulsoup4)")
        return
    for _, _, page in ordered_pages(folder):
        text = page.read_text(encoding="utf-8")
        try:
            plan = read_plan(text)
        except ValueError as e:
            print(f"FAILED   {page.name}: {e}")
            continue
        if plan is None:
            print(f"WARNING  {page.name} has no plan: no summary at the top, and coldread.py can't test it")
            continue
        chs = chapters(BeautifulSoup(text, "html.parser"))
        for msg in lint(plan, chs):
            print(f"WARNING  {page.name}: {msg}")
        if not SUMMARY.search(text):
            print(f"WARNING  {page.name} has a plan but no <!-- summary --><!-- /summary --> under the header")
            continue
        block = "\n" + summary_html(plan, chs) + "\n"
        new = SUMMARY.sub(lambda m: m.group(1) + block + m.group(3), text)
        if new != text:
            page.write_text(new, encoding="utf-8")
            print(f"summary  {page.name}")


# ------------------------------------------------------------------------------------------
# Code colors. Every <pre class="code" data-lang="..."> is colored from its plain text, so
# rebuilding is safe: old color spans are stripped first. Don't put markup inside a code block.
# python, toml, sql: Pygments. shell: "> " or "$ " starts a command; if a block has no prompt,
# every line is a command; other lines are output, left plain. tree: a folder tree, with each
# line's description (after two or more spaces) muted. text: no colors.
# ------------------------------------------------------------------------------------------
CODE = re.compile(r'<pre class="code"(?: data-lang="([a-z]+)")?>(?:<code>)?(.*?)(?:</code>)?</pre>', re.S)
PYGMENTS_LANGS = {"python", "toml", "sql"}
CODE_LANGS = PYGMENTS_LANGS | {"shell", "tree", "text"}


def _shell_command(cmd: str) -> str:
    out, first = [], True
    for tok in re.findall(r'"[^"]*"|\'[^\']*\'|#.*$|\s+|[^\s"\']+', cmd):
        e = html.escape(tok, quote=False)
        if tok.isspace():
            out.append(e)
        elif tok.startswith("#"):
            out.append(f'<span class="c">{e}</span>')
        elif tok[0] in "\"'":
            out.append(f'<span class="s">{e}</span>')
        elif first:
            out.append(f'<span class="cmd">{e}</span>')
            first = False
        elif tok.startswith("-"):
            out.append(f'<span class="fl">{e}</span>')
        else:
            out.append(e)
    return "".join(out)


def color_code(lang: str, text: str) -> str:
    if lang in PYGMENTS_LANGS:
        from pygments import highlight
        from pygments.formatters import HtmlFormatter
        from pygments.lexers import get_lexer_by_name
        return highlight(text, get_lexer_by_name(lang), HtmlFormatter(nowrap=True)).rstrip("\n")
    lines = text.split("\n")
    if lang == "shell":
        prompted = any(re.match(r"(> |\$ )", ln) for ln in lines)
        out = []
        for ln in lines:
            m = re.match(r"(> |\$ )(.*)$", ln)
            if m:
                out.append(f'<span class="gp">{html.escape(m.group(1), quote=False)}</span>' + _shell_command(m.group(2)))
            elif not prompted and ln.strip():
                out.append(_shell_command(ln))
            else:
                out.append(html.escape(ln, quote=False))
        return "\n".join(out)
    if lang == "tree":
        out = []
        for ln in lines:
            m = re.match(r"^(.*?\S)(\s{2,})(\S.*)$", ln)
            out.append(html.escape(ln, quote=False) if not m else
                       html.escape(m.group(1) + m.group(2), quote=False) + f'<span class="c">{html.escape(m.group(3), quote=False)}</span>')
        return "\n".join(out)
    return html.escape(text, quote=False)


def color_pages(folder: Path):
    for _, _, page in ordered_pages(folder):
        text = page.read_text(encoding="utf-8")

        def one(m):
            lang, body = m.group(1), m.group(2)
            line = text.count("\n", 0, m.start()) + 1
            if lang not in CODE_LANGS:
                print(f"WARNING  {page.name}:{line}: a code block without data-lang "
                      f"({', '.join(sorted(CODE_LANGS))}): no colors")
                return m.group(0)
            plain = html.unescape(re.sub(r"<[^>]+>", "", body))
            return f'<pre class="code" data-lang="{lang}"><code>{color_code(lang, plain)}</code></pre>'

        new = CODE.sub(one, text)
        if new != text:
            page.write_text(new, encoding="utf-8")
            print(f"code     {page.name}")


# ------------------------------------------------------------------------------------------
# "Don't miss": every <b class="red"> on a page is listed in a box at the top, with the number
# of the block it sits in, so a red fact can't be scrolled past. The box goes between
# <!-- dontmiss --> and <!-- /dontmiss -->; build.py adds the marker under the summary (or
# above the first section) when a page has none. Runs after the numbers are written.
# ------------------------------------------------------------------------------------------
DONTMISS = re.compile(r"(<!-- dontmiss -->)(.*?)(<!-- /dontmiss -->)", re.S)
RED = re.compile(r'<b class="red">(.*?)</b>', re.S)


def dontmiss(folder: Path):
    for _, _, page in ordered_pages(folder):
        text = page.read_text(encoding="utf-8")
        body = DONTMISS.sub("", text)
        items = []
        for m in RED.finditer(body):
            before = body[:m.start()]
            nums = re.findall(r'<span class="num">([0-9-]+)</span>', before)
            sec = re.findall(r'<section id="([^"]+)"', before)
            ref = nums[-1] if nums else "?"
            link = f'<a href="#{sec[-1]}">{ref}</a>' if sec else ref
            items.append(f"    <li>{link} · {m.group(1).strip()}</li>")
        if not DONTMISS.search(text):
            if not items:
                continue
            marker = "<!-- dontmiss --><!-- /dontmiss -->"
            if "<!-- /summary -->" in text:
                text = text.replace("<!-- /summary -->", "<!-- /summary -->\n" + marker, 1)
            else:
                text = text.replace("<section", marker + "\n\n<section", 1)
        block = ("" if not items else
                 '\n<div class="dontmiss" id="dontmiss">\n  <span class="eyebrow">Don\'t miss</span>\n'
                 '  <ul class="tight">\n' + "\n".join(items) + "\n  </ul>\n</div>\n")
        new = DONTMISS.sub(lambda m: m.group(1) + block + m.group(3), text)
        if new != page.read_text(encoding="utf-8"):
            page.write_text(new, encoding="utf-8")
            print(f"red      {page.name}: {len(items)} to not miss")


NAV = re.compile(r"(<!-- nav -->)(.*?)(<!-- /nav -->)", re.S)


def nav(folder: Path):
    pages = [(order, label, p.name) for order, label, p in ordered_pages(folder)]
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
    interactive(folder)
    color_pages(folder)
    summarize(folder)
    enumerate_pages(folder)
    dontmiss(folder)
    nav(folder)
    print("done")


if __name__ == "__main__":
    main()
