# html-explain

A Claude Code skill that writes explainer pages: local HTML files that teach a system as a problem story (situation → problem → fix → next problem), in short plain sentences, with real numbers, one running example and a picture in every chapter.

`SKILL.md` is the skill itself: the rules Claude follows. This file is for people working on the skill.

## The pipeline

```
1 Gather    read the project's sources, compute every number
2 Plan      the story chain, and one job per chapter: the statement the reader leaves with
3 Template  copy assets/template.html, write the plan JSON into its <head> before any prose
4 Write     the chapters, each serving its job
5 Diagrams  diagrams/NAME.d2, rendered by D2
6 Build     scripts/build.py   summary from the plan, rule checks, numbering, sidebar
7 Look      scripts/check.py   screenshots, then a reread as the reader
8 Cold read scripts/coldread.py  each chapter read by a model with no context, then judged
9 Report    to the user, who answers by reference number (5-6-5)
```

The plan is the single source for four things: the plan itself, the summary at the top of the page, the label above every picture, and the answer key for the cold read.

## Labels and pictures

Every block that isn't a plain paragraph says what it is. Boxes, lists and tables carry `data-role` (and `data-name`), and `build.py` writes the label next to the reference number: "6-8 QUESTION FOR SVETLANA", "6-6 RULES what every setting declares". Lint warns about any block without one.

Every chapter has an overview picture: one map per page that grows chapter by chapter, with the new piece in rust. Other pictures are illustrations (one narrow case with numbers) or complements (easier seen than read). Each picture's type and job are in the plan, and `build.py` writes "OVERVIEW <job>" above it and a colour key under it, from the D2 classes it uses.

## The cold read

The writer can't un-know what they meant, so they can't judge their own chapter. `coldread.py` gives each chapter to a model (Haiku by default) holding only what a human reader would hold at that point:

- the summaries of the older pages,
- the previous page in full,
- this page from the top through the chapter, without this page's summary and without the chapter's check answers.

It runs `claude -p` with no tools, no CLAUDE.md, no memory and an empty working folder, 3 times per chapter. `repeated.md` is the one to read first: the chapter's job next to what each run learned, the check answers, and only the findings two or more runs share. `report.md` has everything: the terms each run knew only from outside, and its assumptions and questions, grouped by reference number. A finding that repeats across runs is real.

The chapter's own pictures go in as real images. Pictures get two more reads, because you can't see whether a reader uses a picture, only what's lost without it: each picture alone (does it show its job?), and the chapter without each complement picture (does the picture add anything?). `--text-only` skips the pictures for quick rereads.

The first test: the old chapter 1 of a project page framed five products as test cases but showed only outputs. None of 3 runs mentioned any input. After the rewrite, all 3 did, and the runs found two more real gaps.

## Layout

```
SKILL.md              the rules Claude follows
assets/template.html  page skeleton, with the plan block and the summary marker
assets/explainers.css the design system (7 colors, 4 sizes, 2 weights, 3 fonts)
assets/theme.d2       diagram classes
assets/fonts/         fonts D2 embeds in diagrams
scripts/build.py      build step
scripts/check.py      screenshots
scripts/coldread.py   cold read
scripts/pages.py      shared helpers: page order, plan, chapters, summary, plain text
```

## Install

Clone into the user skills folder:

```
git clone git@github.com:JavohirX/html-explain.git ~/.claude/skills/html-explain
```

Needs Python 3.10+ with `beautifulsoup4` and `playwright`, [D2](https://github.com/d2lang/d2/releases) on PATH or in `%LOCALAPPDATA%\Programs\d2\`, and the `claude` CLI for the cold read.

## Usage

```
python scripts/build.py <pages-folder>
python scripts/check.py <page.html> <out-folder>
python scripts/coldread.py <page.html> <out-folder> [--chapter ID ...] [--runs 3] [--model haiku]
                           [--picture-model haiku] [--text-only] [--bundle-only]
```

`--bundle-only` writes what the reader would get, without calling a model.
