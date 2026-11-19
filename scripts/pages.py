"""Shared by build.py and coldread.py: page order, the plan, chapters, the summary, and plain text.

The plan is a JSON block in the page's <head>, written before any prose:

    <script type="application/json" id="plan">
    {"example": "Европласт 1.50.100: 522 ₽ goes in, retail 10 620 ₸ comes out.",
     "chapters": {"exam": {"job": "A test case is a basket in and the ТЗ's exact numbers out.",
                           "terms": {"test case": "one input with its expected output, as on LeetCode"}}}}
    </script>

Keys of "chapters" are the ids of the chapter <section>s. A job is the statement the reader leaves
the chapter with. build.py turns the plan into the summary at the top of the page; coldread.py uses
each job as the answer key.
"""
import copy
import html
import json
import re
from dataclasses import dataclass
from pathlib import Path

META = re.compile(r'<meta\s+name="explainer"\s+content="(\d+)\|([^"]+)"\s*/?>', re.I)
PLAN = re.compile(r'<script\s+type="application/json"\s+id="plan">(.*?)</script>', re.S)
CHECK = re.compile(r"^(?:\[[\d-]+\]\s*)?Check:")


def ordered_pages(folder: Path) -> list[tuple[int, str, Path]]:
    """Pages that carry <meta name="explainer" content="ORDER|Label">, oldest first."""
    pages = []
    for p in folder.glob("*.html"):
        m = META.search(p.read_text(encoding="utf-8"))
        if m:
            pages.append((int(m.group(1)), m.group(2).strip(), p))
    pages.sort()
    return pages


def read_plan(text: str) -> dict | None:
    """The page's plan, or None when it has none. Raises ValueError when it's broken."""
    m = PLAN.search(text)
    if m is None:
        return None
    try:
        plan = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        raise ValueError(f"the plan is not valid JSON: {e}") from None
    chapters = plan.get("chapters") if isinstance(plan, dict) else None
    if not isinstance(chapters, dict):
        raise ValueError('the plan needs a "chapters" object, keyed by section id')
    for key, entry in chapters.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("job"), str) or not entry["job"].strip():
            raise ValueError(f'plan chapter "{key}" needs a "job" sentence')
        if not isinstance(entry.get("terms", {}), dict):
            raise ValueError(f'plan chapter "{key}": "terms" must map each term to its one-line meaning')
    return plan


@dataclass
class Chapter:
    n: int            # 0 for the intro, then 1, 2, 3...
    id: str | None
    title: str
    section: object   # the bs4 <section> tag


def plain(tag) -> str:
    """The tag's text without reference numbers, on one line."""
    t = copy.copy(tag)
    for span in t.find_all("span", class_="num"):
        span.decompose()
    return " ".join(t.get_text().split())


def chapters(soup) -> list[Chapter]:
    main = soup.find("main")
    if main is None:
        return []
    found, n = [], 0
    for s in main.find_all("section"):
        if s.find_parent("section") is not None:
            continue
        h2 = s.find("h2", recursive=False)
        if h2 is None:
            found.append(Chapter(0, s.get("id"), "", s))
        else:
            n += 1
            found.append(Chapter(n, s.get("id"), plain(h2), s))
    return found


def check_questions(section) -> list[tuple[str, str]]:
    """(question, folded answer) for each "Check: …" footnote that is a direct child of the section."""
    found = []
    for d in section.find_all("details", recursive=False):
        summary = d.find("summary")
        q = plain(summary) if summary else ""
        if CHECK.match(q):
            body = d.find("div")
            found.append((q, plain(body) if body else ""))
    return found


def planned(plan: dict, chs: list[Chapter]) -> list[tuple[Chapter, dict]]:
    """Chapters that have a plan entry, in page order."""
    jobs = plan.get("chapters", {})
    return [(c, jobs[c.id]) for c in chs if c.n > 0 and c.id in jobs]


def lint(plan: dict, chs: list[Chapter]) -> list[str]:
    """Mechanical checks of the plan against the page. Each message is one rule broken."""
    msgs = []
    jobs = plan.get("chapters", {})
    numbered = [c for c in chs if c.n > 0]
    if not plan.get("example"):
        msgs.append('the plan has no running "example"')
    for c in numbered:
        if not c.id:
            msgs.append(f"chapter {c.n} has no id, so the plan can't give it a job")
            continue
        entry = jobs.get(c.id)
        if entry is None:
            msgs.append(f"chapter {c.n} (#{c.id}) has no job in the plan")
            continue
        terms = entry.get("terms", {})
        if len(terms) > 3:
            msgs.append(f"chapter {c.n} (#{c.id}) plans {len(terms)} new terms; 3 at most")
        checks = len(check_questions(c.section))
        if c is not numbered[-1] and not 1 <= checks <= 2:
            msgs.append(f"chapter {c.n} (#{c.id}) has {checks} check questions; 1 or 2 expected")
    ids = {c.id for c in numbered}
    for key in jobs:
        if key not in ids:
            msgs.append(f"the plan names #{key}, but no chapter has that id")
    return msgs


def _esc(s: str) -> str:
    return html.escape(s, quote=False)


def summary_html(plan: dict, chs: list[Chapter]) -> str:
    rows = planned(plan, chs)
    out = ['<div class="summary" id="summary">', '  <span class="eyebrow">Summary</span>']
    if plan.get("example"):
        out.append(f'  <p><b>Running example:</b> {_esc(plan["example"])}</p>')
    out.append('  <ul class="tight">')
    for c, entry in rows:
        out.append(f'    <li><a href="#{c.id}">{c.n} · {_esc(c.title)}</a><br>{_esc(entry["job"])}</li>')
    out.append("  </ul>")
    terms = [(t, m) for _, entry in rows for t, m in entry.get("terms", {}).items()]
    if terms:
        out.append("  <p><b>Terms this page teaches</b></p>")
        out.append('  <ul class="tight">')
        out += [f"    <li><b>{_esc(t)}</b>: {_esc(m)}</li>" for t, m in terms]
        out.append("  </ul>")
    out.append("</div>")
    return "\n".join(out)


def summary_text(plan: dict, chs: list[Chapter]) -> str:
    rows = planned(plan, chs)
    out = []
    if plan.get("example"):
        out.append(f"Running example: {plan['example']}")
    out += [f"{c.n} · {c.title}: {entry['job']}" for c, entry in rows]
    terms = [(t, m) for _, entry in rows for t, m in entry.get("terms", {}).items()]
    if terms:
        out.append("Terms: " + "; ".join(f"{t} = {m}" for t, m in terms))
    return "\n".join(out)


# ------------------------------------------------------------------------------------------
# Plain text, the way a reader meets the page: what coldread.py hands to the model.
# Reference numbers stay in, as "[1-3]", so the reader can point at a sentence.
# Pictures become their alt sentence plus the words drawn in them.
# ------------------------------------------------------------------------------------------
INLINE = {"b", "strong", "i", "em", "a", "code", "span", "br", "sup", "sub", "small", "abbr", "kbd", "u", "s"}
SKIP = {"script", "style", "aside", "footer", "nav", "input", "label"}


def label_numbers(soup) -> None:
    """Turn every reference number into plain text '[1-3] ' (changes the soup in place)."""
    for span in soup.find_all("span", class_="num"):
        span.replace_with(f"[{span.get_text().strip()}] ")


def _svg_words(svg) -> str:
    alt = svg.get("aria-label", "").strip()
    words = []
    for t in svg.find_all("text"):
        spans = t.find_all("tspan")
        w = " ".join(s.get_text() for s in spans) if spans else t.get_text()
        w = " ".join(w.split())
        if w:
            words.append(w)
    tail = f" Words in it: {' / '.join(words)}" if words else ""
    return f"[Picture: {alt}{tail}]"


def render(node, out: list[str], hide_answers: bool = False, prefix: str = "") -> None:
    """Append the node's readable lines to out."""
    from bs4 import Comment, NavigableString, Tag

    buf: list[str] = []

    def flush():
        s = " ".join("".join(buf).split())
        buf.clear()
        if s:
            out.append(prefix + s)

    for child in node.children:
        if isinstance(child, Comment):
            continue
        if isinstance(child, NavigableString):
            buf.append(str(child))
            continue
        if not isinstance(child, Tag):
            continue
        name, cls = child.name, set(child.get("class") or [])
        if name in SKIP or cls & {"eyebrow", "summary"}:
            continue
        if name in INLINE:
            buf.append(" " if name == "br" else child.get_text())
            continue
        flush()
        if name == "svg":
            out.append(_svg_words(child))
        elif name == "details":
            summary = child.find("summary")
            q = " ".join(summary.get_text().split()) if summary else ""
            body, sub = child.find("div"), []
            if body is not None:
                render(body, sub)
            if CHECK.match(q):
                out.append(f"Check question: {q}")
                if not hide_answers and sub:
                    out.append("Answer (folded): " + " ".join(sub))
            else:
                out.append(f"Footnote (folded): {q}")
                out += ["    " + line for line in sub]
        elif name in ("h1", "h2", "h3"):
            out.append("#" * int(name[1]) + " " + " ".join(child.get_text().split()))
        elif name == "pre":
            out.append("```\n" + child.get_text().strip("\n") + "\n```")
        elif name == "tr":
            out.append(" | ".join(" ".join(c.get_text().split()) for c in child.find_all(["th", "td"])))
        elif name == "li":
            render(child, out, hide_answers, "- ")
        elif name == "figcaption":
            render(child, out, hide_answers, "Caption: ")
        else:
            render(child, out, hide_answers)
    flush()
