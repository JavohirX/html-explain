"""Cold read: can a reader with no context follow each chapter?

Usage:  python coldread.py <page.html> <out-folder> [--chapter ID ...] [--runs 3] [--model haiku] [--bundle-only]

The writer can't un-know what they meant, so they can't judge their own chapter. This script hands
each chapter to a model that knows nothing but what a human reader would remember at that point:
  1. the summaries of the older pages (people don't remember details from two weeks ago),
  2. the previous page, read in full,
  3. this page from the top through the chapter, without this page's summary (it holds the answer
     key) and without the chapter's check answers (the reader answers those).
The model runs with no tools, no CLAUDE.md, no memory and an empty working folder, so it can't
look anything up. It answers what it learned, the check questions, every term and where it learned
it, what it had to assume, and what it would ask. Each chapter runs --runs times in parallel; a
finding that repeats across runs is real, a one-off may be noise.

Writes into <out-folder>:
  bundle-ID.txt   exactly what the reader got for chapter ID
  run-ID-K.json   each answer (raw text when it wasn't valid JSON)
  report.md       per chapter: the job from the plan (the answer key) next to the answers
"""
import json
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pages import chapters, check_questions, label_numbers, ordered_pages, planned, read_plan, render, summary_text

SYSTEM = (
    "You are a careful reader in a reading test. Besides the material you are given, you know "
    "everyday English and programming the way a strong LeetCode solver does: Python, C++, algorithms "
    "and data structures. Nothing about web, databases, frameworks, servers, business or this project. "
    "Answer from the material. When you rely on anything else, say so. An honest 'I am not sure' "
    "helps more than a confident guess."
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


def soup_of(path: Path):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    return soup


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


def bundle(page: Path, target_id: str) -> tuple[str, dict]:
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
    _, label, _ = pages[index]
    lines = page_lines(soup, upto=target.section, hide_answers_in=target.section)
    # Split this page into "before the chapter" and "the chapter", at the chapter's heading.
    start = next(i for i, line in enumerate(lines) if line.startswith("## ") and target.title in line)
    parts.append(f"=== PART 3. The page you are reading now: {index + 1:02d} · {label}, from the top ===")
    parts += lines[:start]
    parts.append("")
    parts.append(f"=== PART 4. THE CHAPTER UNDER TEST: {target.n} · {target.title} ===")
    parts += lines[start:]
    info = {"n": target.n, "title": target.title, "checks": check_questions(target.section)}
    return "\n".join(parts) + "\n", info


def ask(prompt: str, model: str) -> str:
    exe = shutil.which("claude")
    if exe is None:
        raise RuntimeError("the claude CLI is not on PATH")
    cmd = [exe, "-p", "--model", model, "--tools", "", "--setting-sources", "", "--strict-mcp-config",
           "--no-session-persistence", "--system-prompt", SYSTEM]
    with tempfile.TemporaryDirectory(prefix="coldread-") as empty:
        r = subprocess.run(cmd, input=prompt, cwd=empty, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=900)
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout).strip()[-800:])
    return r.stdout


def parse(raw: str):
    start, end = raw.find("{"), raw.rfind("}")
    try:
        return json.loads(raw[start:end + 1])
    except (ValueError, json.JSONDecodeError):
        return None


def _items(answer, key):
    value = answer.get(key) if isinstance(answer, dict) else None
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def report_chapter(cid: str, info: dict, job: str, answers: list) -> list[str]:
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
    for q, page_answer in info["checks"]:
        out.append(f"- {q}")
        out.append(f"  - page: {page_answer}")
        for k, a in enumerate(answers, start=1):
            for ca in _items(a, "check_answers"):
                if ca.get("question", "").strip()[:40] in q or q[:40] in ca.get("question", ""):
                    out.append(f"  - run {k}: {ca.get('answer', '')}")
                    break

    outside = defaultdict(list)
    for k, a in enumerate(answers, start=1):
        for t in _items(a, "terms"):
            if "outside" in str(t.get("source", "")).lower():
                outside[str(t.get("term", "")).strip().lower()].append((k, t))
    out += ["", "**Terms it knew only from outside knowledge:**"]
    if not outside:
        out.append("- none")
    for term, hits in sorted(outside.items(), key=lambda kv: -len(kv[1])):
        meanings = "; ".join(f"run {k}: {t.get('meaning', '')} [{t.get('ref', '')}]" for k, t in hits)
        out.append(f"- **{term}**, {len({k for k, _ in hits})}/{runs} runs. {meanings}")

    for key, field, title in (("assumptions", "assumption", "Assumptions"),
                              ("questions", "question", "Questions for the author"),
                              ("contradictions", "issue", "Contradictions")):
        by_ref = defaultdict(list)
        for k, a in enumerate(answers, start=1):
            for item in _items(a, key):
                by_ref[str(item.get("ref", "")).strip() or "?"].append((k, item.get(field, "")))
        out += ["", f"**{title}, grouped by reference number:**"]
        if not by_ref:
            out.append("- none")
        for ref, hits in sorted(by_ref.items(), key=lambda kv: (-len({k for k, _ in kv[1]}), kv[0])):
            out.append(f"- **{ref}**, {len({k for k, _ in hits})}/{runs} runs")
            out += [f"  - run {k}: {text}" for k, text in hits]
    out.append("")
    return out


def main():
    args = sys.argv[1:]
    flags = {"--runs": "3", "--model": "haiku"}
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

    bundles = {}
    for cid in ids:
        body, info = bundle(page, cid)
        (out / f"bundle-{cid}.txt").write_text(body, encoding="utf-8")
        bundles[cid] = (body, info)
        print(f"bundle   {out / f'bundle-{cid}.txt'} ({len(body.split())} words)")
    if "--bundle-only" in flags:
        return

    tasks = [(cid, k) for cid in ids for k in range(1, runs + 1)]

    def one(task):
        cid, k = task
        try:
            raw = ask(bundles[cid][0] + "\n\n" + QUESTIONS, model)
        except Exception as e:  # noqa: BLE001 - one failed run must not stop the others
            raw = f"(run failed: {e})"
        parsed = parse(raw)
        path = out / f"run-{cid}-{k}.json"
        if parsed is not None:
            path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            path.write_text(raw, encoding="utf-8")
        print(f"read     {cid} run {k}: {'ok' if parsed is not None else 'no JSON'}")
        return task, parsed if parsed is not None else raw

    with ThreadPoolExecutor(max_workers=min(6, len(tasks))) as pool:
        results = dict(pool.map(one, tasks))

    lines = [f"# Cold read: {page.name}", "",
             f"Model `{model}`, {runs} runs per chapter. A finding that repeats across runs is real; "
             "a one-off may be noise. The reader can't feel overload: that stays with the term count and you.", ""]
    for cid in ids:
        answers = [results[(cid, k)] for k in range(1, runs + 1)]
        lines += report_chapter(cid, bundles[cid][1], jobs[cid], answers)
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"report   {out / 'report.md'}")


if __name__ == "__main__":
    main()
