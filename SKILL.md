---
name: html-explain
description: Build a local HTML explainer page (warm paper style, sidebar layout, D2 diagrams, Mermaid sequences) that teaches a system, service, integration or concept the user doesn't understand yet, in any project, written as a problem-driven story (situation → problem → fix → next problem) in short plain sentences, with real numbers, one running example and a picture per chapter, a plan with one job per chapter, a summary at the top, and a cold-read test by a model with no context. Use when the user asks for an HTML page with explanations, "make an html about X", "I don't get what X does", or wants more pages like the existing explainers.
---

# Explainer pages

The user learns new systems from these pages. **Their background:** lots of LeetCode in Python and C++, and nothing else in programming yet. So they're fluent in algorithms, data structures and both languages (graphs, topological sort, hash maps, recursion, complexity, float precision). They have no experience with web, HTTP, databases, ORMs, frameworks, background jobs, servers, deployment, CI, git workflows or team practices. **Don't dumb things down, but never assume a reference will land.** Anything outside their background gets an expandable footnote (`details.fn`, see **Writing**). **The goal of the text is that the reader never stops and thinks "what have I just read?"** Pretty text is not the goal. So: short plain sentences (repeated words are fine), real numbers, one running example, a picture in every chapter, and at most 3 new terms per chapter. Pages are written as a story where every idea appears as the fix for a problem the reader has just felt. The pages are **local HTML files**, not published artifacts. They live in one folder per project, as sibling pages that link to each other through a sidebar.

## Files

```
<project>/docs/                      (or wherever the user names)
  explainers.css                     copied by build.py; never edit it per page
  topic-a.html  topic-b.html         one topic per page, lowercase file names
  diagrams/
    _theme.d2                        copied by build.py
    NAME.d2                          diagram source (the part you write)
    NAME.svg                         rendered by build.py, then inlined into the page
```

Skill assets:
- `assets/template.html`: the page skeleton. Always start from it.
- `assets/explainers.css`: the whole design system.
- `assets/theme.d2`: diagram classes.
- `assets/fonts/`: the fonts D2 embeds in diagrams.

Scripts:
- `scripts/build.py <folder>`: copies the stylesheet, renders diagrams, inlines them into the pages, writes each page's summary from its plan and checks the plan's rules, numbers everything, and rewrites the sidebar page list.
- `scripts/check.py <page> <out>`: takes one set of screenshots.
- `scripts/coldread.py <page> <out>`: the cold read (step 8). Hands each chapter, with its pictures as images, to a model with no context, reads each picture alone, and writes a report to judge.
- `scripts/pages.py`: shared by the others: page order, the plan, chapters, summaries, plain text.

Tools: D2 (`%LOCALAPPDATA%\Programs\d2\d2.exe`, or on PATH), Python with beautifulsoup4, Playwright (Edge channel) for the check, and the `claude` CLI for the cold read. Mermaid loads from a pinned CDN.

The skill is a git repo (`github.com/JavohirX/html-explain`, private). Commit changes to the skill there.

## Steps

1. **Gather facts first.** Read the project's own sources (specs, briefs, saved vendor docs, code). Every claim must trace to a source or to well-known public behavior. Mark assumptions as **examples** or **open questions**. Never invent a vendor's behavior, prices or timelines. **Compute every number yourself** before it goes on the page, including the numbers in made-up "what if" scenarios. For example, check that a wrong input of 523 ₽ really ends at 10 640 ₸ before the page says so.
2. **Plan the story before writing.** Write down the chain first, one line per chapter, and check that each chapter's fix causes or exposes the next chapter's problem:
   - **Intro (chapter 0):** the goal in a `.oneliner` ("By the end you'll know…"), then one paragraph that maps the chapters.
   - **The starting situation:** the concrete world before the thing exists. Real people, real numbers, what hurts.
   - **The first, simplest idea,** and why it isn't enough.
   - **Problem chapters:** one problem and its fix each. Usually 3–8.
   - **Where this leaves us / what's next:** the result, and the next step with the reason it comes next.
   - Sources go in the footer.

   If the chain needs more than about 12 chapters, split it into several pages, each a complete story. The page's question decides the chain. Don't pad it with a vocabulary section or a comparison table that no problem asked for.

   Then, before writing any prose, add to the plan:
   - **The job of each chapter:** the one statement the reader leaves the chapter with, written as that statement ("A test case is a basket in and the ТЗ's exact numbers out"), not as "the reader knows…". Prefer one claim; if it takes two, the cold read checks each. Every item in the chapter serves the job. A detail the job doesn't need goes into a footnote or out. Three checks against the job:
     - **The frame keeps its promise.** If the chapter uses a frame (an exam, a LeetCode test case, a recipe), list what the frame makes the reader expect, and show each part with the running example's numbers. A test case promises an input and an expected output, so show both. If you can't, drop the frame.
     - **The running example leads.** Show it first and whole. The other cases come after it, as "four more like it". A full source table is rarely the job.
     - **The check question tests the job.** Write it from the job sentence, before the prose. If the easy question to ask is about a detail, that detail is too big on the page.
   - **The running example:** one concrete thing (one product, one file, one person's day) with real numbers, followed through every chapter.
   - **New terms per chapter:** list them. At most 3 per chapter. If a chapter has more, split it or cut the terms the story doesn't need. A footnote doesn't make a term free: it still counts.
   - **The pictures per chapter,** each with a type and a job (the one thing the picture alone must show):
     - **Overview, in every chapter:** where this chapter's piece sits in the whole. It's one map per page that grows chapter by chapter: the same cells in the same places, with this chapter's new piece in `rust`. It goes near the end of the chapter, after the fix, as the "so far" picture. It never replaces the text: the text alone must still teach the chapter's job.
     - **Illustration:** one narrow case with the running example's numbers (a timeline, one product's basket).
     - **Complement:** something that's easier seen than read: an order, states and moves, who depends on whom. The cold read checks that it adds what the text doesn't.
   - **The check questions:** 1–2 per chapter, and their answers.
   - **Just in time:** cut anything the reader doesn't need yet. If something gets built next week, it gets one line now and its own page on the day it's built.
3. **Copy `assets/template.html`** into the folder, and **write the plan into it before any prose**:
   - Set `<title>`: "X Explained", or the question itself.
   - Set `<meta name="explainer" content="ORDER|Label">`. Pages are listed oldest to newest, so a new page always takes the next order after the highest one in the folder (10, 20, 30…). Don't slot a new page between older ones. `build.py` numbers the sidebar 01, 02, 03… from that order, so don't put a number in the label.
   - Fill the plan, the `<script type="application/json" id="explainer-plan">` block in the `<head>`: the running `example` in one line with its key numbers, and under `chapters` one entry per chapter `id` with its `job`, its `terms` (each new term with its meaning in one plain line) and its `figures`: each picture's D2 name with its `type` (`overview`, `illustration`, `complement`) and `job`, plus an optional `key` when a colour means something specific in that picture (`{"green": "a commit"}`). The plan is the single source: `build.py` writes the page's summary and every picture's label from it, and `coldread.py` uses each job as the answer key. To change the summary or a label, change the plan.
   - Fill the "On this page" links in the sidebar to match the section `id`s.

   **Every page has a summary at the top.** A reader can't recall a detail from a page two weeks old, but they can reread its summary in a minute. When you edit an older page that has no plan, add its plan first.

   **Adding a plan to an older page:** go page by page in reading order, and treat every later page as if it doesn't exist yet, because the cold read gives each page only the pages before it. Write each job from what the chapter already teaches, not from what you wish it taught. Add the missing check questions. Then build, cold-read and fix as in steps 6–8.
4. **Write the chapters,** following **Writing** below, each one serving its job. **Every block that isn't a plain paragraph says what it is**, so the reader never has to work out whether a box is a decision, a question for them or a bridge. Give it `data-role`, and lists and tables a `data-name`; `build.py` writes the label next to the number ("6-8 QUESTION FOR SVETLANA", "6-6 RULES what every setting declares"):
   - **Boxes** (`.note`): `decided`, `question` (with `data-who="Svetlana"`; "you" by default), `open` (decided later, and where), `changed` (see **Changed facts** in step 8), `next` (the bridge to the next problem). Don't repeat the label in the text ("Decided: …").
   - **Lists, cards and limits:** `steps` (in order), `options` (pick one), `problems` (all at once), `rules` (all apply), `reasons`, `examples`, `parts`, `decisions`. The kind says why it's a list; the name says what its items are.
   - **Tables:** `table`, with a name that says what one row is: "One row per day: what we build, and when the day is done".
   - **Code sketches:** `figure data-role="code"` with a name. **Pictures** take their label from the plan ("OVERVIEW <job>"), with a colour key under the caption, made from the classes the diagram uses. Don't describe the colours in the caption too.
   - Footnotes are labelled "Footnote" by `build.py`; check questions already start with "Check:".
5. **Write diagrams** as `diagrams/NAME.d2` (see below). Place each one in the page as `<!-- d2:NAME "alt sentence" --><!-- /d2 -->` inside `<div class="fig-box">`. Don't put double quotes inside the alt text. Never hand-place SVG coordinates: that's what caused overlapping labels before. The alt sentence says what the picture shows: the cold reader gets only that and the words drawn in it.
6. **Build:** `python ~/.claude/skills/html-explain/scripts/build.py <folder>`. Fix every FAILED line, and every WARNING about the page you're working on: a chapter without a job, more than 3 new terms, a chapter without 1–2 check questions, a chapter without an overview picture, a picture without a type and job, a box, list or table without a role.
7. **Look once:** `python ~/.claude/skills/html-explain/scripts/check.py <page.html> <scratchpad>/check`. Read the screenshots, fix what they show in one pass, rebuild, and stop. Don't loop.
   **Then reread the text once as the user,** someone who knows only LeetCode. Mark every word they'd stop at and every sentence they'd read twice. Fix each one: explain it, split it, or cut it. Count each chapter's new terms again (3 at most).
8. **Cold read:** `python ~/.claude/skills/html-explain/scripts/coldread.py <page.html> <scratchpad>/coldread`, then read `repeated.md` first: per chapter, the job next to what each run learned, the check answers, and only the findings two or more runs share. Open `report.md` when you need a single run's full answer.
   - **Why:** the writer can't un-know what they meant, so they fill every gap without noticing, and the word-level checks pass anyway. Chapter 1 of "Monday, part 1" framed the ТЗ's five products as test cases, then showed only outputs, counted them, and asked why one brand has 5 prices and another 4. Every sentence passed the rules. In the cold read, none of 3 runs mentioned any input, and one summed it up as "how many numbers each product has". After the rewrite, all 3 learned "a basket of inputs, and the exact numbers that must come out".
   - **What the reader gets:** what a person would hold at that point. The summaries of the older pages, the previous page in full, and this page from the top through the chapter, with the chapter's pictures as real images. It doesn't get this page's summary, because that holds the answer key, or the chapter's check answers, because it answers those itself. It runs with no tools, no CLAUDE.md, no memory and an empty folder, 3 times per chapter, and answers what it learned, the check questions, each term and where it learned it, what it assumed, what it would ask, and what each picture showed it.
   - **Pictures get two more reads,** because you can't see whether a reader uses a picture, only what's lost without it. **Alone:** every picture by itself, with its type and colour key but not its job. **Without:** each complement picture removed from its chapter. `--text-only` skips both, for quick rereads after a text fix.
   - **Judge each chapter:**
     - **The job is learned:** each claim of the job shows up in "what it learned" in at least 2 of 3 runs. The main point is only a hint: readers tend to pick the chapter's finish line ("Monday is over when all 22 pass") as the main point.
     - **The check answers match the page's answers.** A run that says "the chapter doesn't state this, my guess is…" and guesses right still passes: a check may take one step of reasoning.
     - **No unexplained terms:** a term marked "outside knowledge" in 2 or more runs needs an explanation or a footnote. Ignore everyday words and LeetCode knowledge the user has (VAT, currency signs). If an older page explains the term but has no summary yet, add that page's plan instead.
     - **No repeated confusion:** an assumption, question or contradiction at the same reference number in 2 or more runs is a real gap. A finding from one run only gets fixed when it's clearly right. `repeated.md` leaves out findings at a "Next problem" box: the reader sees only up to this chapter, so the question that leads into the next one always looks unanswered.
     - **Each picture shows its job:** read alone, the job shows up in what it "shows" in at least 2 of 3 runs. If not, redraw it. A **complement** must also add something: the chapter read without it learns the picture's job in fewer runs than the chapter read with it. If the chapter does as well without it, the picture only repeats the text: make it show what the text can't, or call it an illustration. In the first test, two of four complements taught nothing the text didn't, and both became illustrations; one now shows the real versions from the lock file.
     - **What the pictures taught us:**
       - **A picture alone must say what it's about.** All six readers of a proposal's stages, read alone, took it for "a blocked purchase price", because its first box said that. A title node fixed it (`near: top-center`, class `note`).
       - **A map's labels must stay true in every chapter that shows it.** "Engine v1.3 → 10 620 ₸" sat on the map in chapters 7 and 8, while chapter 7's story has 1.3 giving 10 630. Keep chapter-specific facts off the growing map.
       - **Draw no arrow that claims less than the text.** "git → snapshots → calculator" read as "git snapshots only the calculator", against "every file in the project". When no target is true, drop the arrow and say it in the label.
       - **Count what the picture shows.** "Four layers" over a picture with three rows read as a contradiction in 3 of 3 runs.
   - **Sort each repeated finding into one of four kinds,** and handle it by its kind:

     | Kind | What to do |
     |---|---|
     | The page or the project knows the answer, but the text doesn't say it | Fix the text. This is most findings, and it's your job, not the user's. |
     | The next chapter answers it | Nothing. |
     | A page not yet written will decide it | An `open` box that says where it's decided, and add the question to that page's list in the project's to-do list. |
     | Nobody has decided it, and it belongs here | A `question` box at the bottom of the chapter, with options and a default, also added to the project's to-do list. The user answers by number; then the answer goes into the text and the box goes. |

   - **Fix:** when the job isn't learned, rebuild the chapter from its job; don't patch words. For a repeated question or contradiction, fix the sentence it points at:
     - **State a fact, never a hedge.** "The proposal is usually replaced" made 3 of 3 runs ask "when isn't it?". "A draft, blocked or sent proposal is replaced" closed it.
     - **State the whole claim, not one example of it.** "We type 1.50.100's numbers" made 3 of 3 runs ask "what about the other four products?". "We type the five products' numbers" closed it.
     - **Fix for clarity, not with later facts.** The page answers what its own story raises. A question the next page answers gets one forward line at most ("Tuesday's page covers this"), not the answer.
     - **Check every fact you add** against the project's sources, plans and memory before it goes on the page. If the project hasn't decided it yet, don't decide it in the page: leave it and tell the user it's open.
   - **Every fix gets verified.** A round is a fix plus a rerun of only the changed chapters with `--chapter ID`. A fix can open a new question, as both examples above did before their second version. Stop after 3 rounds, and tell the user what's still open.
   - The reader can't feel overload, so it can't tell you a chapter is too heavy. That stays with the term count and the user. It also knows git, Django and servers, and quietly fills gaps with that: it's an optimistic stand-in for the user, so the user's own reading stays the final check. For pictures read alone, Sonnet caught the point a little more often than Haiku (2.5 against 1.5 of 3, on one picture), but both tripped on the same flaw. So Haiku stays the default, and `--picture-model sonnet` is there for a second opinion.

   **Changed facts.** Each page tells its story as of when it was written, but it must never teach a number that's no longer true. When a decision changes a fact on an older page, add a `changed` box at that spot: "On 16 November this changed. Nobody had made the fourteen extra cases, so we wrote our own. Page 06 has them." Don't rewrite the old story. Each time a decision changes, search every page for the old value (and the plans, since the summary comes from them). Three rules from the cold read:
   - **Keep the old sentence true, and move the old fact into the note.** "Fourteen more test cases are coming", with the note right under it, read as a contradiction in 3 of 3 runs. The past tense ("the ТЗ promised fourteen more") still did in 2 of 3. What worked: the old sentence says only what's still true ("five products, 22 numbers"), and the note tells the whole change ("The ТЗ also promised fourteen more… On 16 November we learned nobody had made them…").
   - **A change that runs through the whole page needs one reading rule, and the new values next to the old ones.** With the week moved two days, a note at every spot ("This Monday was Wednesday 18 November") did not fix it: 2–3 of 3 runs still flagged four spots, because the reader had to combine old day names and new dates in their head. What fixed all four (0 of 3): a note at the top that says how to read the page ("this page keeps the plan's day names; the table in chapter 3 gives each day's real date"), a «Real date» column next to the old days in that table, and the other notes pointing to the column.
   - **A picture that still shows the old value contradicts its own note** (3 of 3: page 01's map said "Engine, Mon" under a note that said Wednesday). Redraw it with the new values, and say in the note that the picture shows them.
   - **An answered question isn't a changed fact.** Replace the `question` box with a `decided` box that states the answer. A question about 40 % next to a `changed` note about 15 % read as a contradiction in 3 of 3 runs.
9. **Report:** give the file link, then answer the user's actual question in plain words in 2–4 lines, then list any open questions the page raises. Add one line on the cold read: which chapters passed, and anything still open. Don't write a report of what you did ("I added A, B and C"). The user can't check that. Tell them what the page will teach them and where to start reading.

## Reference numbers

The user answers pages by number ("5-6-5 ok", "9-2 no") instead of quoting text, so every page carries one numbering with dashes, never dots. `build.py` writes the numbers; don't type them yourself.

- **Chapter:** each `<section>` with an `h2`, counted from 1. Its eyebrow becomes "5 · LABEL", and its "On this page" link becomes "5 · Label". The intro section without an `h2` is chapter 0.
- **Item:** each block in a chapter: a paragraph, note, figure, card, list, table, card grid or limits block. For example, 5-6. The number sits in the block's label: above a list or table, on the first line of a box, above a picture.
- **Member:** each card, list item, table row, limit or glossary entry inside a collection. For example, 5-6-5. A list nested inside a member goes one level deeper (5-6-5-2).
- **`.qgroups`** is see-through: each question group is an item of the chapter (9-2), and each question in it is a member (9-2-1).
- Put every point, suggestion and question in its own paragraph, list item, card or row, so each gets its own number. Two questions in one paragraph share a number and can't be answered separately.
- When the user replies with numbers, read them against the built page: `grep -n '>5-6-5<' page.html`. When a reply names another page, the sidebar number (01, 02…) says which one.

## Design system (chosen by the user; don't drift from it)

**Keep it minimal.** Use only what's listed here, with no extra colors, sizes or ornaments.

- **7 colors**, all defined as tokens in `explainers.css`:
  - `--bg` #FAF6EF (paper)
  - `--surf` #FFFDF9 (cards, tables, figures)
  - `--tint` #F2EBDF (darker beige: notes, code, card footers, current page in the sidebar)
  - `--line` #E4DACB (borders and dividers)
  - `--text` #111111
  - `--muted` #6B6358 (small labels and captions)
  - `--accent` #B4531A (the only accent: links and "ask now" tags)
- **4 sizes:** 34 (h1), 22 (h2), 16 (everything read, including h3), 13 (labels, captions, sidebar, table headers).
- **2 weights:** 400 and 700. The only exception is Unbounded headings at 600.
- **3 fonts, each with one job:** Unbounded for h1 and h2 only, Open Sans for all other text, Cousine for `<code>` only.
- **Sharp corners everywhere.** No border-radius.
- **No tiny decorative touches:** no accent bars on the edges of boxes or links, no pills, no colored tag backgrounds, no emoji. Emphasis comes from a filled `--tint` block, bold text, or position.
- **Light theme only.** Never reuse the project's app or brand theme.

**Layout:**
- A **left sidebar** (sticky, against the window's left edge) holds everything clickable: the page list, "On this page" links, and optional page facts. The reading column holds only reading material. No buttons or tag clouds in the text.
- **The reading column is 800px wide**, centered in the remaining space and shifted slightly left. **Every element in it has that same width:** paragraphs, notes, cards, tables and figures.
- **Stack things vertically.** Put items side by side only for a real head-to-head comparison, using `.compare`. Everything else (cards, lists, flows, glossary) goes one under another.
- Below 900px the sidebar moves above the content.

**Components:** only use these classes.

| Class | For |
|---|---|
| `.summary` | the summary under the header; `build.py` writes it from the plan, never by hand |
| `.oneliner` | the page's goal, in chapter 0 |
| `.note` | a highlighted box (tint block) with a `data-role`: `decided`, `question` (+ `data-who`), `open`, `changed`, `next`. A `div.note` may hold a `<p>` and a list of options |
| `.card` inside `.grid` | a stacked list of cards; `.ru` for the original term, `.sp` for the "In this project" footer |
| `.compare` | two or three cards side by side, only when comparing head to head |
| `.limits` with `.limit` | what goes wrong: the problem in `.l` (bold), then the concrete scenario or what we do in `.r`. Usually `data-role="problems"` |
| `.table-box` with `<table>` | tables; `td.k` for a bold first column; `data-role="table"` and a `data-name` that says what one row is |
| `figure` with `.fig-box` and `figcaption` | diagrams; type, job and key come from the plan's `figures` |
| `figure` > `.fig-box` > `pre.code` | a short code sketch, only when the reader truly needs to see code; always with a figcaption, `data-role="code"` and a `data-name` |
| `details.fn` | a footnote: `<details class="fn"><summary>What's X?</summary><div><p>…</p></div></details>`, placed right after the paragraph it explains (never inside a `<p>`), or inside an `li` or a `.limit` after its text. As a section's direct child it gets its own reference number, so the user can say "4-3 still unclear". Also used for check questions: the summary is "Check: …?" and the body is the answer |
| `ol.steps`, `ul.tight` | lists |
| `.eyebrow` | the small label above each h2 ("2 · VOCABULARY") |
| `.tag` or `.tag.now` | text-only status labels |
| `.small` | a muted 13px line |
| `.gloss` | a glossary |

Don't write inline `style=` attributes. If something needs a new class, add it to `assets/explainers.css` in the skill, within the rules above, and rebuild.

## D2 diagrams

`build.py` puts `...@_theme` at the top of each `.d2` file. Use the theme classes, never raw colors:

| Class | Use for |
|---|---|
| `box` | an ordinary component |
| `rust` | the thing the page is about |
| `green` | our own system |
| `blue` | a third-party system in focus |
| `bad` | an attacker, a failure, what must not happen |
| `note` | free text |
| `zone` | a boundary (private network, cloud) |
| `panel` | a titled container, e.g. "Option A" |
| edges: `live`, `bg` (dashed: background or async), `danger`, `accent` | |

```d2
direction: down
app: "Guest app\nFlutter" {class: green}
push: "Push service\nGoogle servers" {class: rust}
private: "Private network" {
  class: zone
  api: "Internal API" {class: box}
}
app -> push: "token" {class: live}
push -> private.api: "nightly" {class: bg}
```

- **Diagrams show at their real size (scale 1), never stretched.** `build.py` gives each inlined SVG its real width and height, and the CSS only lets it shrink. So the text in every diagram is exactly the theme's sizes, which match the page: 16 for boxes and panel titles, 13 for edge labels. A small diagram stays small and centered. That's correct, so don't widen it to fill the box.
- **Keep every diagram at most 762px wide** (the box's inner width). Anything wider has to shrink, and its text shrinks with it. `build.py` warns about it. Fixes, in order:
  1. Split long labels into 2–3 lines.
  2. Shrink the grid gaps (60–80 is enough). But a gap with a labelled edge in it needs about 70: in a narrower one the label covers the arrow ("go back" hid the very arrow its picture was about). If that edge matters, put its target below instead of beside, so the edge runs down.
  3. Drop edge labels that repeat the target's name ("accept" pointing at "Accepted").
  4. Turn a row of sources into a column (`direction: right`, sources stacked on the left).
  5. Split the diagram in two.
- Layouts that work:
  - A hub with many neighbors: `direction: down`, with the hub in the middle.
  - A long chain (a timeline, a lifecycle): `grid-columns: 3` or `4` with `horizontal-gap: 60–170`, numbered labels ("1 · …"), and edges only between neighboring cells. Grid edges are straight and cut through anything in their way.
  - A top-to-bottom flow with labels on the edges (a value passing through parts): `grid-columns: 1` with `vertical-gap: 90`. Don't use `direction: down` here: it leaves about 350px between nodes, and the figure becomes several screens tall.
  - Two groups to compare (before/after): put two `panel` containers in a top-level grid (`grid-columns: 1` to stack them, `2` for side by side). Don't rely on `direction: right` to place containers: it stacked them. Write the caption after you've seen the render, so "left/right" or "top/bottom" matches it.
- **Grids fill column by column** unless `grid-rows` comes before `grid-columns`. To fill row by row (reading order), write `grid-rows: 2` and then `grid-columns: 3`.
- **Write `.d2` files with the Write tool,** not through a shell heredoc. In this environment, `\\n` in a heredoc became a real line break, and D2 failed with "double quoted strings must be terminated".
- **Numbers belong in diagrams too:** put the running example's values on the edges ("522 ₽", "proposal: 10 620 ₸"). The fonts render ₽, ₸, × and Cyrillic.
  - A two-option comparison: two `panel` containers, drawing the edge that differs.
  - A pure mapping (A corresponds to B): an HTML table, not a diagram.
- Labels: a title line plus at most one or two short lines (`\n`). Explanations go in the `<figcaption>`.
- About 12 nodes at most. Split bigger diagrams.

## Mermaid (sequence diagrams only)

Use `<pre class="mermaid">` in a `.fig-box` for request/response flows between 3–5 participants. The template loads Mermaid 10.9.1 with matching colors. Delete those scripts if the page has no sequences.

## Numeric charts

Only if the page has real data: load Chart.js from cdnjs with a pinned version, and use `--accent`, `--muted` and `--line` for colors. Chart only real numbers from a source.

## Writing: tell it as a problem story

The user's model is building a house in a jungle. It's getting dark and bamboo is everywhere, so you make a bamboo bed. At night the water rises and insects crawl on you, so you put the bed on legs, two meters up. Next day it rains, so you add a roof. Then the monsoon floods it, so you build higher. A friend says higher houses get no mosquitoes, and it works. But climbing down for water every day is tiring, so why not collect rainwater from the roof? **Every piece exists because of a problem the reader has just felt.** That is the shape of every page. (It's also called problem-driven, or "you could have invented it", explaining.)

**The goal of the text:** the reader reads a chapter and never thinks "what have I just read?". Pretty text is not the goal. Clear text is.

**Plain sentences.**
- One idea per sentence. Most sentences under 15 words.
- At most one "which", "that", "because" or comma clause per sentence. If there are more, split it into two sentences.
- Use the same word for the same thing, every time. Never swap in a synonym for variety. A new word makes the reader think it's a new thing. If it's "the basket" once, it's "the basket" everywhere, never "the snapshot", "the bundle" or "the input". That holds across sibling pages too: page 01's "delivery" against page 02's "transport" for the same 9 % read as a contradiction in 3 of 3 runs.
- Plain words before technical words: "the price calculator" first, then "programmers call it the engine".
- Simple sentences, full ideas. Don't remove content. Remove complexity.

Bad: "Without the contract, the engine (Monday) and the gather step that fills its basket (Tuesday) get written on different days against different ideas of the basket."
Good: "On Monday we write the calculator. On Tuesday we write the code that fills its basket. If nobody wrote down what goes in the basket, Tuesday's basket won't fit Monday's calculator."

**Numbers, examples, pictures.**
- **Numbers.** Every chapter carries real numbers from the project. Not "the price goes up" but "522 ₽ becomes 10 620 ₸". Write out the arithmetic when it's short: "522 × 6.5 = 3 393".
- **Examples.** Every general statement is followed right away by an example. If you can't find one, the statement is probably empty: cut it.
- **One running example.** Follow the same concrete thing through the whole page, so every chapter shows what happens to that same thing.
- **A picture in every chapter**, when the chapter has anything to draw: a diagram, a table of numbers, or a before/after. The best picture grows: the same diagram in each chapter, with the new piece in `rust`. It doubles as the "so far" recap.

**At most 3 new terms per chapter.** Count them while planning and again before showing the page.

**Teach just in time.** A page teaches only what the reader needs now. Something built next week gets one line now and its own page on that day. A plan page fits on about one screen.

**Each chapter has the same rhythm:**
1. **So far:** one bold-led line (`<p><b>So far:</b> …</p>`) or the growing picture. A reader who lost a chapter can pick the thread back up here. Skip it only in the first chapter.
2. **The problem**, as a concrete scenario with real names and numbers from the project: "the analyst edits the rate halfway through, so 3 000 products use the old rate and 3 000 the new one". Use `.limits` when several things go wrong at once.
3. **The fix**, in plain words, as steps (`ol.steps`), with the running example's numbers in the steps.
4. **The name**, optionally, only after the idea has been explained: "Programmers call this a snapshot." Put a long aside in `.small`.
5. **Check yourself:** 1–2 questions the reader answers from memory, each a `details.fn` whose summary is the question ("Check: on Tuesday 1.50.100 gives 10 630 ₸. Where do you look first?") and whose body is the answer. Ask "why?" or "what happens if…?" with numbers, never "what is X called?". Reading alone doesn't stick; recalling does.
6. **The bridge**, a `.note` that names the next problem the fix leads to: "Good. But some products depend on others."

**Rules:**
- **State the goal first.** The reader must always know where the page is going and why they're reading the current chapter.
- **Don't dumb down the ideas, and don't assume references.** No baby analogies for things the reader already knows: topological sort, hash maps or floating-point error need no "like socks before shoes". But every term from outside their LeetCode background (web, databases, frameworks, infrastructure, team practice, the project's business domain) gets explained where it first appears. If a term isn't needed to follow the story, leave it out.
- **Footnotes for possible gaps.** When a line uses something the reader may not know, and explaining it inline would break the story's flow, put an expandable footnote right under that line. Its summary names the term as a question ("What's a database transaction?"). Its body explains it in 2–5 short sentences and ties it back to the story ("In our case…"). Footnotes are optional depth: the story must still read correctly with every footnote closed. Use them only for real possible gaps, never for things the reader certainly knows.
- **No bare references in the text.** Don't drop spec section numbers (§7.2), table or column names, library names or business-plan parts into a sentence without explaining what they are. Sources go in the footer. Name a tool only when the reader will meet it, and say what it does in the same sentence.
- **Explain the order.** When there are several options or steps, say why this one comes first and why not the others, for example by showing who depends on whom.
- **Use analogies** where they help: a bucket instead of many trips to the river. Keep each one to a single sentence.
- **Never write a report.** "We do A, B and C, and it's great" teaches nothing. Every claim answers a "why?" the reader would ask.
- No filler, no marketing tone, active voice.
- Keep original-language terms (e.g. a vendor's Russian terms) next to the plain names, since those are what the reader will meet in docs and APIs.
- Don't guess pronouns for real people named in project documents. Use their name, their role or "they".

## A chapter done right

This is the model. It's chapter 2 of the Premiera page "Next week, day by day", the first page written by these rules. The running example is one product: Европласт 1.50.100, where 522 ₽ goes in and 10 620 ₸ comes out. Copy its shape, not its content.

```html
<section id="order">
  <span class="eyebrow">WHY THIS ORDER</span>
  <h2>Build from the middle out</h2>
  <!-- 1. So far: one line, with the running example's numbers -->
  <p><b>So far:</b> six parts. 522 ₽ goes in at the top, 10 620 ₸ comes out at the bottom. The calculator sits in the middle.</p>
  <!-- 2. The problem: a concrete scenario with numbers that were computed, not guessed -->
  <p>Imagine we build all six parts at once. On Friday we run 1.50.100. The program says 10 640 ₸, not 10 620 ₸. Something is wrong. But where?</p>
  <p>Two very different mistakes give exactly this number:</p>
  <ul class="tight">
    <li>The import read 523 ₽ instead of 522 ₽. Then 523 × 6.5 = 3 399.5, and the retail price ends up at 10 640 ₸.</li>
    <li>The database kept the rate as 6.51 instead of 6.5. Then 522 × 6.51 = 3 398.22, and the retail price also ends up at 10 640 ₸.</li>
  </ul>
  <p>And the mistake could be in any of the other four parts too. Six suspects. We have to search all six.</p>
  <!-- the picture: before/after, same part names as everywhere else on the page -->
  <figure>
    <div class="fig-box"><!-- d2:suspects "…" --><!-- /d2 --></div>
    <figcaption>Top: everything built at once. When the price is wrong, all six parts are suspects. Bottom: Tuesday, when we build one day at a time. The calculator already passed on Monday. Only the two new parts are suspects.</figcaption>
  </figure>
  <!-- 3. The fix: steps, each with the running example's numbers -->
  <p>The fix: add the parts one day at a time, and test 1.50.100 every day.</p>
  <ol class="steps">
    <li><b>Monday:</b> the calculator alone. We type the basket by hand. It must say 10 620 ₸. If it doesn't, the mistake is in the calculator. It's the only part.</li>
    <li><b>Tuesday:</b> the database and the gather step. The basket now comes from the database. It must still say 10 620 ₸. If it says 10 640 ₸, the calculator is not a suspect: it passed on Monday. The mistake is in one of the two new parts.</li>
    <!-- … -->
  </ol>
  <p>Each day adds new parts next to parts that already passed. So when a number breaks, we know where to look: in today's parts.</p>
  <!-- explain the order: why this and not the obvious alternative -->
  <p>Why the middle and not the top? The calculator needs only a basket, and we can type that by hand. Every other part needs its neighbour. So the calculator comes first, and the other parts grow around it.</p>
  <!-- 5. Check: a what-happens-if question with numbers; the answer is folded -->
  <details class="fn"><summary>Check: on Tuesday 1.50.100 comes out as 10 640 ₸. On Monday it was 10 620 ₸. The calculator's code did not change. Where do you look first?</summary><div>
    <p>At the basket. The same calculator with the same basket gives the same answer. So Tuesday's basket must differ from Monday's. Compare them number by number. Maybe the database kept the rate as 6.51.</p>
  </div></details>
  <!-- 6. Bridge -->
  <p class="note">Here is the whole week as a table: what we build each day, and how we know it works.</p>
</section>
```

What makes it work:
- **Zero new terms.** Chapter 1 already introduced every word used here.
- **The problem is felt, not stated.** It doesn't say "debugging gets harder". It shows one wrong number with two causes.
- **Sentences of 5–15 words.** "Six suspects." is a full sentence.
- **The same words throughout:** "suspect", "part", "basket", "10 620 ₸". No synonyms.
