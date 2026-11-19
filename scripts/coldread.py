"""Cold read: can a reader with no context follow each chapter, and does each picture show its job?

Usage:  python coldread.py <page.html> <out-folder> [--chapter ID ...] [--runs 3] [--model haiku]
                           [--picture-model haiku] [--text-only] [--bundle-only]

The writer can't un-know what they meant, so they can't judge their own chapter. This script hands
each chapter to a model that knows nothing but what a human reader would remember at that point:
  1. the summaries of the older pages (people don't remember details from two weeks ago),
  2. the previous page, read in full (its pictures as the words drawn in them),
  3. this page from the top through the chapter, without this page's summary (it holds the answer
     key) and without the chapter's check answers (the reader answers those),
  4. the chapter's own pictures as real images, the way the reader sees them.
The model runs with no tools, no CLAUDE.md, no memory and an empty working folder, so it can't
look anything up. It answers what it learned, the check questions, every term and where it learned
it, what it had to assume, what it would ask, and what each picture showed it.

Pictures get two more reads, because you can't see whether a reader uses a picture, only what is
lost without it:
  alone      every picture by itself, with its type and colour key but not its job: does the
             picture show what the plan says it shows?
  without    each complement picture removed from the chapter: does the chapter teach the
             picture's job without it? If it does as well as with it, the picture only repeats
             the text, or the reader ignored it.
--text-only skips the images and both picture reads (quick rereads after a text fix).

Each read runs --runs times in parallel; a finding that repeats across runs is real, a one-off may
be noise. Writes into <out-folder>:
  bundle-ID.txt            exactly what the reader got for chapter ID
  pictures/REF.png         each picture as the reader saw it
  run-ID-K.json            each chapter answer (raw text when it wasn't valid JSON)
  alone-KEY-K.json         each picture read alone
  without-KEY-K.json       each chapter read without one complement picture
  repeated.md              read first: per chapter, the job next to what each run learned, the
                           check answers, each picture's reads, and only the findings two or more
                           runs share
  report.md                everything, per chapter, grouped by reference number
"""
import base64
import json
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pages import (chapters, check_questions, figure_plan, label_numbers, ordered_pages, pictures,
                   planned, read_plan, render, summary_text)

SYSTEM = (
    "You are a careful reader in a reading test. Besides the material you are given, you know "
    "everyday English and programming the way a strong LeetCode solver does: Python, C++, algorithms "
    "and data structures. Nothing about web, databases, frameworks, servers, business or this project. "
    "Answer from the material. When you rely on anything else, say so. An honest 'I am not sure' "
    "helps more than a confident guess. Your own working folder and environment are not the project "
    "the material describes: don't compare the two."
)

QUESTIONS = """Read everything above. Then answer about PART 4, THE CHAPTER UNDER TEST, only.
Reply with one JSON object and nothing else, in this shape:
{
  "learned": "2-4 sentences: what this chapter taught you",
  "main_point": "one sentence: the single main point of this chapter",
  "check_answers": [{"question": "the check question", "answer": "your answer, from the material alone"}],
  "terms": [{"term": "...", "meaning": "what you take it to mean",
             "source": "this chapter | earlier chapter | previous page | older summary | outside knowledge",
             "ref": "the reference number where you met it, like 1-3-5"}],
  "assumptions": [{"ref": "1-5", "assumption": "what you had to assume or guess to follow it"}],
  "questions": [{"ref": "1-5", "question": "what you would ask the author"}],
  "contradictions": [{"ref": "1-5", "issue": "what seems to disagree with what"}]
}
In "terms", list every term, name or abbreviation in the chapter that is not everyday English and
not LeetCode knowledge. "outside knowledge" means you understood it only from what you knew
before, and the material never explained it. Use empty lists where you have nothing."""

PICTURES_Q = """The chapter's pictures are attached as images, in order. Add one more key to the JSON:
  "pictures": [{"ref": "the picture's reference number", "shows": "what the picture showed you",
                "added": "what it told you that the chapter's text did not, or 'nothing'"}]"""

TYPE_MEANING = {
    "overview": "an overview: where one chapter's piece sits in the whole, the same map growing chapter by chapter",
    "illustration": "an illustration: one narrow case, with real numbers",
    "complement": "a complement: something that is easier to see than to read",
}

ALONE_Q = """This is one picture from an explainer page titled "{title}". The page labels it as {kind}.
{key}
Look only at the picture. Reply with one JSON object and nothing else:
{{
  "shows": "1-2 sentences: what this picture shows",
  "main_point": "one sentence: the single point it makes",
  "elements": [{{"element": "a box, arrow, colour or label", "meaning": "what you take it to stand for"}}],
  "unclear": ["anything you could not work out from the picture alone"]
}}"""


def soup_of(path: Path):
    from bs4 import BeautifulSoup
    return BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")


def page_lines(soup, upto=None, hide_answers_in=None) -> list[str]:
    """The page as a reader meets it: the header, then each chapter, stopping after `upto`."""
    label_numbers(soup)
    out: list[str] = []
    hero = soup.find("header")
    if hero is not None:
        render(hero, out)
    for c in chapters(soup):
        out.append("")
        render(c.section, out, hide_answers=c.section is hide_answers_in)
        if upto is not None and c.section is upto:
            break
    return out


def picture_info(page: Path, target_id: str) -> list[dict]:
    """The chapter's pictures: plan key, reference number, position among the page's <figure>s,
    type and job from the plan, and the colour key under it."""
    soup = soup_of(page)
    plan = read_plan(page.read_text(encoding="utf-8"))
    target = next(c for c in chapters(soup) if c.id == target_id)
    figs = soup.find_all("figure")
    plan_figs = figure_plan(plan, target_id)
    found = []
    for key, fig in pictures(target.section):
        num = fig.find("span", class_="num")
        key_span = fig.find("span", class_="lbl-key")
        entry = plan_figs.get(key, {})
        found.append({"key": key, "ref": num.get_text().strip() if num else key,
                      "index": next(i for i, f in enumerate(figs) if f is fig),
                      "type": entry.get("type"), "job": entry.get("job", ""),
                      "colour_key": key_span.get_text().strip() if key_span else ""})
    return found


def bundle(page: Path, target_id: str, images: bool = True, drop: str | None = None) -> tuple[str, dict]:
    """What the reader gets for one chapter. With images, the chapter's pictures are replaced by
    '[Picture 4-6: image 1, attached]' and sent as images. `drop` removes one picture entirely."""
    pages = ordered_pages(page.parent)
    index = next((i for i, (_, _, p) in enumerate(pages) if p.resolve() == page.resolve()), None)
    if index is None:
        sys.exit(f'{page.name} has no <meta name="explainer" content="ORDER|Label">')
    parts = ["=== PART 1. What you remember from older pages: only their summaries ==="]
    older = pages[: max(index - 1, 0)]
    if not older:
        parts.append("(none)")
    for i, (_, label, p) in enumerate(older, start=1):
        parts.append(f"--- {i:02d} · {label} ---")
        try:
            plan = read_plan(p.read_text(encoding="utf-8"))
        except ValueError:
            plan = None
        parts.append(summary_text(plan, chapters(soup_of(p))) if plan else "(no summary: you remember nothing of this page)")
    parts.append("")
    if index > 0:
        _, label, prev = pages[index - 1]
        parts.append(f"=== PART 2. The previous page, read in full: {index:02d} · {label} ===")
        parts += page_lines(soup_of(prev))
    else:
        parts.append("=== PART 2. The previous page: (none, this is the first page) ===")
    parts.append("")

    soup = soup_of(page)
    target = next((c for c in chapters(soup) if c.id == target_id), None)
    if target is None:
        sys.exit(f"{page.name} has no chapter with id {target_id}")
    attached = []
    for key, fig in pictures(target.section):
        if key == drop:
            fig.decompose()
            continue
        if images:
            num = fig.find("span", class_="num")
            ref = num.get_text().strip() if num else key
            box = fig.find(class_="fig-box") or fig
            box.clear()
            box.append(soup.new_string(f"[Picture {ref}: image {len(attached) + 1}, attached]"))
            attached.append(key)
    _, label, _ = pages[index]
    lines = page_lines(soup, upto=target.section, hide_answers_in=target.section)
    # Split this page into "before the chapter" and "the chapter", at the chapter's heading.
    start = next(i for i, line in enumerate(lines) if line.startswith("## ") and target.title in line)
    parts.append(f"=== PART 3. The page you are reading now: {index + 1:02d} · {label}, from the top ===")
    parts += lines[:start]
    parts.append("")
    parts.append(f"=== PART 4. THE CHAPTER UNDER TEST: {target.n} · {target.title} ===")
    parts += lines[start:]
    info = {"n": target.n, "title": target.title, "checks": check_questions(target.section), "attached": attached}
    return "\n".join(parts) + "\n", info


def shoot(page: Path, figs: list[dict], folder: Path) -> dict:
    """Screenshot each picture's box, the way the reader sees it: {key: png path}."""
    from playwright.sync_api import sync_playwright
    folder.mkdir(parents=True, exist_ok=True)
    shots = {}
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="msedge")
        except Exception:  # noqa: BLE001 - fall back to the bundled browser
            browser = pw.chromium.launch()
        tab = browser.new_page(viewport={"width": 1100, "height": 1000})
        tab.goto(page.as_uri())
        tab.wait_for_timeout(3000)  # fonts + mermaid
        for f in figs:
            fig = tab.locator("figure").nth(f["index"])
            box = fig.locator(".fig-box")
            path = folder / f"{f['ref']}.png"
            (box if box.count() else fig).first.screenshot(path=str(path))
            shots[f["key"]] = path
        browser.close()
    return shots


def ask(prompt: str, model: str, images: list[Path] | None = None) -> str:
    """One read. Images go in as content blocks next to the text; the reader still has no tools."""
    exe = shutil.which("claude")
    if exe is None:
        raise RuntimeError("the claude CLI is not on PATH")
    cmd = [exe, "-p", "--model", model, "--tools", "", "--setting-sources", "", "--strict-mcp-config",
           "--no-session-persistence", "--system-prompt", SYSTEM]
    if images:
        content = [{"type": "text", "text": prompt}]
        for k, img in enumerate(images, start=1):
            content.append({"type": "text", "text": f"Image {k}:"})
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                        "data": base64.b64encode(img.read_bytes()).decode()}})
        stdin = json.dumps({"type": "user", "message": {"role": "user", "content": content}}) + "\n"
        cmd += ["--input-format", "stream-json", "--output-format", "stream-json", "--verbose"]
    else:
        stdin = prompt
    with tempfile.TemporaryDirectory(prefix="coldread-") as empty:
        r = subprocess.run(cmd, input=stdin, cwd=empty, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=900)
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout).strip()[-800:])
    if not images:
        return r.stdout
    for line in reversed(r.stdout.splitlines()):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "result":
            return str(event.get("result", ""))
    raise RuntimeError("no result in the stream: " + r.stdout[-500:])


def parse(raw: str):
    start, end = raw.find("{"), raw.rfind("}")
    try:
        return json.loads(raw[start:end + 1])
    except (ValueError, json.JSONDecodeError):
        return None


def _items(answer, key):
    value = answer.get(key) if isinstance(answer, dict) else None
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


FINDINGS = (("assumptions", "assumption", "Assumptions"),
            ("questions", "question", "Questions for the author"),
            ("contradictions", "issue", "Contradictions"))


def _check_answers(answers: list, index: int) -> list[tuple[int, str]]:
    """Each run's answer to the chapter's check question number `index`, matched by position."""
    found = []
    for k, a in enumerate(answers, start=1):
        items = _items(a, "check_answers")
        if index < len(items):
            found.append((k, items[index].get("answer", "")))
    return found


def _outside(answers: list) -> dict:
    """term -> [(run, item)] for terms a run knew only from outside knowledge."""
    found = defaultdict(list)
    for k, a in enumerate(answers, start=1):
        for t in _items(a, "terms"):
            if "outside" in str(t.get("source", "")).lower():
                found[str(t.get("term", "")).strip().lower()].append((k, t))
    return found


def _by_ref(answers: list, key: str, field: str) -> list[tuple[str, list]]:
    """[(ref, [(run, text)])], the refs flagged by the most runs first."""
    found = defaultdict(list)
    for k, a in enumerate(answers, start=1):
        for item in _items(a, key):
            found[str(item.get("ref", "")).strip() or "?"].append((k, item.get(field, "")))
    return sorted(found.items(), key=lambda kv: (-len({k for k, _ in kv[1]}), kv[0]))


def _runs(hits) -> int:
    return len({k for k, _ in hits})


def _picture_lines(figs: list[dict], answers: list, alone: dict, without: dict, full: bool) -> list[str]:
    """Per picture: its job, what it showed alone, what it added in the chapter, and (complement)
    what the chapter taught without it."""
    out = []
    for f in figs:
        out += ["", f"**Picture {f['ref']}** ({f['key']}, {f['type'] or 'no type in the plan'}). "
                    f"Job: {f['job'] or '(none)'}"]
        for k, a in enumerate(alone.get(f["key"], []), start=1):
            if isinstance(a, dict):
                out.append(f"- alone, run {k}: {a.get('shows', '')} Point: {a.get('main_point', '')}")
                if full:
                    out += [f"  - {e.get('element', '')}: {e.get('meaning', '')}" for e in _items(a, "elements")]
                    out += [f"  - unclear: {u}" for u in (a.get("unclear") or []) if isinstance(u, str)]
            else:
                out.append(f"- alone, run {k}: (no JSON)")
        for k, a in enumerate(answers, start=1):
            for p in _items(a, "pictures"):
                if str(p.get("ref", "")).strip() == f["ref"]:
                    out.append(f"- in the chapter, run {k}: {p.get('shows', '')} Added: {p.get('added', '')}")
        for k, a in enumerate(without.get(f["key"], []), start=1):
            out.append(f"- without it, run {k} learned: {a.get('learned', '') if isinstance(a, dict) else '(no JSON)'}")
    return out


def report_chapter(cid, info, job, answers, figs, alone, without) -> list[str]:
    runs = len(answers)
    out = [f"## {info['n']} · {info['title']} (#{cid})", "", f"**Job, the answer key:** {job}", "",
           "**Main point, per run:**"]
    for k, a in enumerate(answers, start=1):
        if isinstance(a, dict):
            out.append(f"{k}. {a.get('main_point', '(none)')}")
        else:
            out.append(f"{k}. (no JSON: {str(a)[:300]})")
    out += ["", "**What it learned, per run:**"]
    out += [f"{k}. {a.get('learned', '')}" for k, a in enumerate(answers, start=1) if isinstance(a, dict)]

    out += ["", "**Check questions:**"]
    for i, (q, page_answer) in enumerate(info["checks"]):
        out.append(f"- {q}")
        out.append(f"  - page: {page_answer}")
        out += [f"  - run {k}: {text}" for k, text in _check_answers(answers, i)]
    out += _picture_lines(figs, answers, alone, without, full=True)

    outside = _outside(answers)
    out += ["", "**Terms it knew only from outside knowledge:**"]
    if not outside:
        out.append("- none")
    for term, hits in sorted(outside.items(), key=lambda kv: -_runs(kv[1])):
        meanings = "; ".join(f"run {k}: {t.get('meaning', '')} [{t.get('ref', '')}]" for k, t in hits)
        out.append(f"- **{term}**, {_runs(hits)}/{runs} runs. {meanings}")

    for key, field, title in FINDINGS:
        groups = _by_ref(answers, key, field)
        out += ["", f"**{title}, grouped by reference number:**"]
        if not groups:
            out.append("- none")
        for ref, hits in groups:
            out.append(f"- **{ref}**, {_runs(hits)}/{runs} runs")
            out += [f"  - run {k}: {text}" for k, text in hits]
    out.append("")
    return out


def repeated_chapter(cid, info, job, answers, figs, alone, without, next_refs) -> list[str]:
    """The judge's short view: the job next to what each run learned, the check answers, each
    picture's reads, and only the terms, assumptions, questions and contradictions that two or more
    runs share. Findings at the chapter's "Next problem" box are left out: the reader sees only up to
    this chapter, so the question that leads into the next one always looks unanswered."""
    runs = len(answers)
    out = [f"## {info['n']} · {info['title']} (#{cid})", "", f"**Job:** {job}", "", "**Learned:**"]
    for k, a in enumerate(answers, start=1):
        out.append(f"{k}. {a.get('learned', '')}" if isinstance(a, dict) else f"{k}. (no JSON)")
    for i, (q, page_answer) in enumerate(info["checks"]):
        out += ["", f"**{q}**", f"- page: {page_answer}"]
        out += [f"- run {k}: {text}" for k, text in _check_answers(answers, i)]
    out += _picture_lines(figs, answers, alone, without, full=False)
    shared = [f"- term **{term}** known only from outside, {_runs(hits)}/{runs} runs"
              for term, hits in _outside(answers).items() if _runs(hits) >= 2]
    for key, field, title in FINDINGS:
        for ref, hits in _by_ref(answers, key, field):
            if _runs(hits) >= 2 and ref not in next_refs:
                shared.append(f"- {title.lower()} at **{ref}**, {_runs(hits)}/{runs} runs")
                shared += [f"  - run {k}: {text}" for k, text in hits]
    out += ["", "**Shared by 2+ runs:**"] + (shared or ["- nothing"]) + [""]
    return out


def next_problem_refs(page: Path, cid: str) -> set[str]:
    """Reference numbers of the chapter's "Next problem" boxes."""
    soup = soup_of(page)
    target = next(c for c in chapters(soup) if c.id == cid)
    refs = set()
    for box in target.section.find_all(attrs={"data-role": "next"}):
        num = box.find("span", class_="num")
        if num:
            refs.add(num.get_text().strip())
    return refs


def main():
    args = sys.argv[1:]
    flags = {"--runs": "3", "--model": "haiku", "--picture-model": None}
    wanted, positional, i = [], [], 0
    while i < len(args):
        a = args[i]
        if a in flags:
            flags[a] = args[i + 1]
            i += 2
        elif a == "--chapter":
            wanted.append(args[i + 1])
            i += 2
        elif a.startswith("--"):
            flags[a] = "1"
            i += 1
        else:
            positional.append(a)
            i += 1
    if len(positional) < 2:
        sys.exit(__doc__)
    page, out = Path(positional[0]).resolve(), Path(positional[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    runs, model = int(flags["--runs"]), flags["--model"]
    picture_model = flags["--picture-model"] or model
    with_pictures = "--text-only" not in flags

    text = page.read_text(encoding="utf-8")
    try:
        plan = read_plan(text)
    except ValueError as e:
        sys.exit(f"{page.name}: {e}")
    if plan is None:
        sys.exit(f"{page.name} has no plan: write the chapter jobs first (see SKILL.md, step 2)")
    jobs = {c.id: entry["job"] for c, entry in planned(plan, chapters(soup_of(page)))}
    ids = wanted or list(jobs)
    missing = [cid for cid in ids if cid not in jobs]
    if missing:
        sys.exit(f"no job in the plan for: {', '.join(missing)}")
    title = next((line for line in page_lines(soup_of(page))[:3] if line.startswith("# ")), "# " + page.name)[2:]

    bundles, figs, without_bundles = {}, {}, {}
    for cid in ids:
        body, info = bundle(page, cid, images=with_pictures)
        (out / f"bundle-{cid}.txt").write_text(body, encoding="utf-8")
        bundles[cid] = (body, info)
        figs[cid] = picture_info(page, cid) if with_pictures else []
        print(f"bundle   {out / f'bundle-{cid}.txt'} ({len(body.split())} words, {len(info['attached'])} pictures)")
        for f in figs[cid]:
            if f["type"] == "complement":
                without_bundles[f["key"]] = (cid, bundle(page, cid, images=True, drop=f["key"]))
    if "--bundle-only" in flags:
        return

    all_figs = [f for cid in ids for f in figs[cid]]
    shots = shoot(page, all_figs, out / "pictures") if all_figs else {}
    for f in all_figs:
        print(f"picture  {shots[f['key']]}")

    tasks = [("chapter", cid, None, k) for cid in ids for k in range(1, runs + 1)]
    by_key = {f["key"]: f for f in all_figs}
    tasks += [("alone", None, f["key"], k) for f in all_figs for k in range(1, runs + 1)]
    tasks += [("without", cid, key, k) for key, (cid, _) in without_bundles.items() for k in range(1, runs + 1)]

    def one(task):
        kind, cid, fig, k = task
        try:
            if kind == "chapter":
                body, info = bundles[cid]
                imgs = [shots[key] for key in info["attached"]]
                prompt = body + "\n\n" + QUESTIONS + ("\n" + PICTURES_Q if imgs else "")
                raw, name = ask(prompt, model, imgs), f"run-{cid}-{k}.json"
            elif kind == "alone":
                fig = by_key[fig]
                kind_text = TYPE_MEANING.get(fig["type"], "a picture")
                prompt = ALONE_Q.format(title=title, kind=kind_text, key=fig["colour_key"])
                raw, name = ask(prompt, picture_model, [shots[fig["key"]]]), f"alone-{fig['key']}-{k}.json"
            else:
                _, (body, info) = without_bundles[fig]
                imgs = [shots[key] for key in info["attached"]]
                prompt = body + "\n\n" + QUESTIONS + ("\n" + PICTURES_Q if imgs else "")
                raw, name = ask(prompt, model, imgs), f"without-{fig}-{k}.json"
        except Exception as e:  # noqa: BLE001 - one failed run must not stop the others
            raw, name = f"(run failed: {e})", f"failed-{kind}-{cid or ''}-{k}.txt"
        parsed = parse(raw)
        path = out / name
        path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2) if parsed is not None else raw,
                        encoding="utf-8")
        print(f"read     {name}: {'ok' if parsed is not None else 'no JSON'}")
        return task, parsed if parsed is not None else raw

    with ThreadPoolExecutor(max_workers=min(6, len(tasks))) as pool:
        results = dict(pool.map(one, tasks))

    lines = [f"# Cold read: {page.name}", "",
             f"Model `{model}`, pictures read alone by `{picture_model}`, {runs} runs per read. A finding "
             "that repeats across runs is real; a one-off may be noise. The reader can't feel overload: "
             "that stays with the term count and you.", ""]
    short = [f"# Cold read, repeated findings: {page.name}", "",
             f"Read this first. The full answers are in report.md. Model `{model}`, pictures read alone by "
             f"`{picture_model}`, {runs} runs per read.", ""]
    for cid in ids:
        answers = [results[("chapter", cid, None, k)] for k in range(1, runs + 1)]
        alone = {f["key"]: [results[("alone", None, f["key"], k)] for k in range(1, runs + 1)] for f in figs[cid]}
        without = {key: [results[("without", c, key, k)] for k in range(1, runs + 1)]
                   for key, (c, _) in without_bundles.items() if c == cid}
        info = bundles[cid][1]
        lines += report_chapter(cid, info, jobs[cid], answers, figs[cid], alone, without)
        short += repeated_chapter(cid, info, jobs[cid], answers, figs[cid], alone, without,
                                  next_problem_refs(page, cid))
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "repeated.md").write_text("\n".join(short), encoding="utf-8")
    print(f"report   {out / 'repeated.md'} (read first)")
    print(f"report   {out / 'report.md'}")


if __name__ == "__main__":
    main()
