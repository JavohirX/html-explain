/* Explainer pages: answers in the page, reading places, the book and the map. build.py copies this file.

   On every page
   - .quiz (a test), .choice (a question for the reader: my recommendation shows only after a pick) and
     .answer-field (a free note) are answered in the page.
   - The page remembers where you were reading (the numbered block at the top of the screen) and which
     footnotes were open. "↑ Top" goes back up.
   - The sidebar's panel: progress, "Copy for Claude", "Start over" (this page's answers) and
     "Forget reading places" (every page's places and the map's state).

   In the book (index.html, <body data-book>, written by build.py)
   - Every page sits in a <template>. Moving between pages swaps the text in place: no reload. The
     address is #/page or #/page/section, so Back, Forward and a reload all land where they should.
   - The map (map.json, embedded by build.py) is the first page: every part of the system, its status,
     what it uses, and a step-by-step trace of one example through the parts.

   Storage, all in localStorage, all under "explainers:":
   "<file>" one page's answers · "places" where each page was left · "map" the map's view, selection
   and step · "last" the book's last page. Answers are stored by each option's text, so an edit of the
   page never points an answer at the wrong option. */
(function () {
  "use strict";

  /* ---------------- small helpers ---------------- */
  var PREFIX = "explainers:";
  function load(key, fallback) {
    try { var v = JSON.parse(localStorage.getItem(PREFIX + key)); return v == null ? fallback : v; }
    catch (e) { return fallback; }
  }
  function keep(key, value) { try { localStorage.setItem(PREFIX + key, JSON.stringify(value)); } catch (e) { /* private window */ } }
  function forget(key) { try { localStorage.removeItem(PREFIX + key); } catch (e) { /* private window */ } }
  function each(list, fn) { Array.prototype.forEach.call(list, fn); }
  function make(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function num(node) { var n = node && node.querySelector(".num"); return n ? n.textContent.trim() : ""; }
  function plain(node) {
    var c = node.cloneNode(true);
    each(c.querySelectorAll(".num, .why, .rec-tag, .label-line"), function (x) { x.remove(); });
    return c.textContent.replace(/\s+/g, " ").trim();
  }
  function short(opt) {  /* an option's own words: its first cell, cut at about 70 characters */
    var s = plain(opt.querySelector("td") || opt);
    return s.length > 70 ? s.slice(0, 70).replace(/\s+\S*$/, "") + "…" : s;
  }
  function typing(e) { return e.target.closest && e.target.closest("textarea, input, select, [contenteditable]"); }

  var BOOK = document.body.hasAttribute("data-book");
  var side = document.querySelector("aside");

  /* ================= answers: tests, questions, note fields ================= */
  function Answers(root, file, title, onChange) {
    var store = load(file, {}) || {};
    function save() { keep(file, store); onChange(); }
    function options(box) { return Array.prototype.slice.call(box.querySelectorAll(":scope > .opts > li, :scope tbody > tr")); }
    function key(opt) { return plain(opt).slice(0, 80); }
    function question(box) { var q = box.querySelector(".q"); return q ? plain(q) : ""; }
    function clickable(opt, pick) {
      opt.tabIndex = 0;
      opt.setAttribute("role", "button");
      opt.addEventListener("click", function (e) { if (e.target.closest("a, textarea")) return; pick(); });
      opt.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); }
      });
    }
    var tests = [], choices = [], fields = [];

    each(root.querySelectorAll(".quiz[id]"), function (q) {
      var opts = options(q), keys = opts.map(key);
      var right = opts.findIndex(function (o) { return o.classList.contains("right"); });
      var verdict = make("p", "verdict");
      verdict.setAttribute("aria-live", "polite");
      q.appendChild(verdict);
      function tries() {
        var s = store[q.id];
        return s && s.tries ? s.tries.map(function (k) { return keys.indexOf(k); }).filter(function (i) { return i >= 0; }) : [];
      }
      function paint() {
        var t = tries(), done = t.indexOf(right) >= 0;
        q.classList.toggle("done", done);
        opts.forEach(function (o, i) {
          o.classList.toggle("picked", t.indexOf(i) >= 0);
          o.classList.toggle("is-right", done && i === right);
          o.classList.toggle("is-wrong", t.indexOf(i) >= 0 && i !== right);
        });
        verdict.className = "verdict" + (done ? " ok" : t.length ? " no" : "");
        verdict.textContent = !t.length ? "" : done
          ? (t[0] === right ? "Right, on the first try." : "Right, on try " + (t.indexOf(right) + 1) + ".")
          : "Not this one. Its reason is under it. Try another.";
      }
      opts.forEach(function (o, i) {
        clickable(o, function () {
          var t = tries();
          if (t.indexOf(right) >= 0 || t.indexOf(i) >= 0) return;
          store[q.id] = { tries: t.concat([i]).map(function (j) { return keys[j]; }), at: Date.now() };
          paint(); save();
        });
      });
      paint();
      tests.push({ box: q, tries: tries, right: right, opts: opts, paint: paint });
    });

    each(root.querySelectorAll(".choice[id]"), function (c) {
      var opts = options(c), keys = opts.map(key);
      var rec = opts.findIndex(function (o) { return o.classList.contains("rec"); });
      var why = c.querySelector(".rec-why");
      var verdict = make("p", "verdict");
      verdict.setAttribute("aria-live", "polite");
      if (why) c.insertBefore(verdict, why); else c.appendChild(verdict);
      var note = make("textarea", "answer-note");
      note.rows = 2;
      note.placeholder = "Your note, if any: a doubt, a change, another option";
      c.appendChild(note);
      function picked() { var s = store[c.id]; return s && s.pick ? keys.indexOf(s.pick) : -1; }
      function paint() {
        var p = picked();
        c.classList.toggle("answered", p >= 0);
        opts.forEach(function (o, i) {
          o.classList.toggle("picked", i === p);
          o.classList.toggle("is-rec", p >= 0 && i === rec);
          var tag = o.querySelector(".rec-tag");
          if (p >= 0 && i === rec && !tag) (o.querySelector("td") || o).appendChild(make("span", "rec-tag", "My recommendation"));
          if (tag && !(p >= 0 && i === rec)) tag.remove();
        });
        verdict.textContent = p < 0 ? "" : p === rec
          ? "You picked " + num(opts[p]) + ". I'd pick the same."
          : "You picked " + num(opts[p]) + ". I'd recommend " + num(opts[rec]) + ".";
        note.value = (store[c.id] && store[c.id].note) || "";
      }
      opts.forEach(function (o, i) {
        clickable(o, function () {
          var s = store[c.id] || {};
          s.pick = keys[i];
          s.at = Date.now();
          store[c.id] = s;
          paint(); save();
        });
      });
      note.addEventListener("input", function () {
        var s = store[c.id] || {};
        s.note = note.value;
        store[c.id] = s;
        save();
      });
      paint();
      choices.push({ box: c, picked: picked, rec: rec, opts: opts, paint: paint });
    });

    each(root.querySelectorAll(".answer-field[id]"), function (f) {
      var note = make("textarea", "answer-note");
      note.rows = 3;
      note.placeholder = f.getAttribute("data-placeholder") || "Your answer";
      f.appendChild(note);
      function paint() { note.value = (store[f.id] && store[f.id].note) || ""; }
      note.addEventListener("input", function () { store[f.id] = { note: note.value, at: Date.now() }; save(); });
      paint();
      fields.push({ box: f, paint: paint });
    });

    function progress() {
      var parts = [];
      if (tests.length) {
        var done = tests.filter(function (t) { return t.tries().indexOf(t.right) >= 0; }).length;
        var first = tests.filter(function (t) { var tr = t.tries(); return tr.length && tr[0] === t.right; }).length;
        parts.push("Tests: " + done + " of " + tests.length + " done, " + first + " right first try");
      }
      if (choices.length) {
        parts.push("Questions: " + choices.filter(function (c) { return c.picked() >= 0; }).length + " of " +
                   choices.length + " answered");
      }
      return parts;
    }
    function results() {
      var out = [title + " (" + file + ")"];
      if (tests.length) {
        var done = 0, first = 0, lines = [];
        tests.forEach(function (t) {
          var tr = t.tries(), ok = tr.indexOf(t.right) >= 0;
          if (ok) done++;
          if (ok && tr[0] === t.right) { first++; return; }
          if (!tr.length) { lines.push("- " + num(t.box) + ": not done"); return; }
          var wrong = tr.filter(function (i) { return i !== t.right; })
            .map(function (i) { return num(t.opts[i]) + " \"" + short(t.opts[i]) + "\""; });
          lines.push("- " + num(t.box) + " " + question(t.box) + " " +
                     (ok ? "Right on try " + (tr.indexOf(t.right) + 1) : "Not right yet") + ". Wrong picks: " + wrong.join("; "));
        });
        out.push("", "Tests: " + done + " of " + tests.length + " done, " + first + " right on the first try.");
        out = out.concat(lines);
      }
      if (choices.length) {
        var answered = choices.filter(function (c) { return c.picked() >= 0; }).length;
        out.push("", "Questions: " + answered + " of " + choices.length + " answered.");
        choices.forEach(function (c) {
          var p = c.picked(), s = store[c.box.id] || {};
          var line = "- " + num(c.box) + " " + question(c.box) + " " + (p < 0 ? "Not answered." : "Picked " + num(c.opts[p]) +
                     ": " + short(c.opts[p]) +
                     (p === c.rec ? " (same as my recommendation)" : " (I recommended " + num(c.opts[c.rec]) + ": " +
                      short(c.opts[c.rec]) + ")"));
          if (s.note) line += " · note: " + s.note.replace(/\s+/g, " ").trim();
          out.push(line);
        });
      }
      var notes = fields.filter(function (f) { var s = store[f.box.id]; return s && s.note && s.note.trim(); });
      if (notes.length) {
        out.push("", "Notes:");
        notes.forEach(function (f) { out.push("- " + num(f.box) + ": " + store[f.box.id].note.replace(/\s+/g, " ").trim()); });
      }
      return out.join("\n");
    }
    function reset() {
      store = {};
      keep(file, store);
      tests.concat(choices, fields).forEach(function (b) { b.paint(); });
      onChange();
    }
    return {
      any: tests.length + choices.length + fields.length > 0,
      progress: progress, results: results, reset: reset
    };
  }

  /* ================= the sidebar panel ================= */
  var panel = null, answers = null;
  function flash(button, text, back) {
    button.textContent = text;
    setTimeout(function () { button.textContent = back; }, 2500);
  }
  function copy(text, button) {
    function done(ok) { flash(button, ok ? "Copied: paste it to Claude" : "Select the text below and copy it", "Copy for Claude"); }
    function fallback() {
      var ta = make("textarea", "answer-note");
      ta.value = text;
      ta.rows = 6;
      panel.appendChild(ta);
      ta.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
      if (ok) ta.remove();
      done(ok);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(function () { done(true); }, fallback);
    else fallback();
  }
  function buildPanel() {
    if (!side || panel) return;
    panel = make("div", "answers");
    panel.innerHTML = '<div class="own"><span class="eyebrow">Your answers</span><p class="progress"></p>' +
      '<div class="buttons"><button type="button" class="copy">Copy for Claude</button>' +
      '<button type="button" class="reset">Start over</button></div></div>' +
      '<button type="button" class="forget">Forget reading places</button>';
    side.appendChild(panel);
    panel.querySelector(".copy").addEventListener("click", function () { if (answers) copy(answers.results(), this); });
    panel.querySelector(".reset").addEventListener("click", function () {
      if (answers && confirm("Clear every answer on this page?")) answers.reset();
    });
    panel.querySelector(".forget").addEventListener("click", function () {
      places = {};
      forget("places");
      forget("map");
      forget("last");
      if (map) map.reset();
      flash(this, "Forgotten: every page opens at its top", "Forget reading places");
    });
  }
  function updatePanel() {
    if (!panel) return;
    var own = panel.querySelector(".own");
    own.hidden = !(answers && answers.any);
    if (answers && answers.any) panel.querySelector(".progress").innerHTML = answers.progress().join("<br>");
  }

  /* ================= reading places ================= */
  var places = load("places", {}) || {};
  var touched = false;  /* the reader scrolled, clicked or typed since the page opened */
  function anchorAt(root) {
    /* the numbered block at the top of the screen, and where its number sits (its top, in px) */
    var nums = root.querySelectorAll(".num"), best = null;
    for (var i = 0; i < nums.length; i++) {
      var n = nums[i];
      if (!n.getClientRects().length) continue;
      var top = n.getBoundingClientRect().top;
      if (top <= 12) best = { num: n.textContent.trim(), dy: Math.round(top) };
      else break;
    }
    return best;
  }
  function detailsKey(d, i) { var n = d.querySelector("summary .num"); return n ? n.textContent.trim() : "#" + i; }
  function savePlace(file, root) {
    if (!file || !root) return;
    var open = [];
    each(root.querySelectorAll("details"), function (d, i) { if (d.open) open.push(detailsKey(d, i)); });
    var a = anchorAt(root);
    places[file] = { num: a ? a.num : null, dy: a ? a.dy : 0, y: Math.round(window.scrollY), open: open };
    keep("places", places);
  }
  function openFootnotes(file, root) {
    var p = places[file];
    if (!p || !p.open) return;
    each(root.querySelectorAll("details"), function (d, i) { if (p.open.indexOf(detailsKey(d, i)) >= 0) d.open = true; });
  }
  function jump(y) {
    /* an instant move: the stylesheet scrolls smoothly, and a slow animation to a remembered place
       would be saved halfway as the new place */
    window.scrollTo({ top: Math.max(0, Math.round(y)), left: 0, behavior: "instant" });
  }
  function jumpTo(node) { jump(window.scrollY + node.getBoundingClientRect().top - 16); }
  function goToPlace(file, root) {
    var p = places[file];
    if (!p) { jump(0); return; }
    var target = null;
    if (p.num) each(root.querySelectorAll(".num"), function (n) { if (!target && n.textContent.trim() === p.num && n.getClientRects().length) target = n; });
    if (target) jump(window.scrollY + target.getBoundingClientRect().top - p.dy);
    else jump(p.y || 0);
  }
  if ("scrollRestoration" in history) history.scrollRestoration = "manual";
  ["wheel", "touchstart", "keydown", "mousedown"].forEach(function (ev) {
    window.addEventListener(ev, function () { touched = true; }, { passive: true });
  });

  /* where the reader is: the page's file and its root; set by the standalone page or by the book */
  var here = { file: null, root: null };
  var saveTimer = null;
  window.addEventListener("scroll", function () {
    topButton.classList.toggle("show", window.scrollY > window.innerHeight * 0.8);
    clearTimeout(saveTimer);
    saveTimer = setTimeout(function () { savePlace(here.file, here.root); }, 150);
  }, { passive: true });
  window.addEventListener("pagehide", function () { savePlace(here.file, here.root); });
  document.addEventListener("toggle", function (e) {
    if (here.root && here.root.contains(e.target)) savePlace(here.file, here.root);
  }, true);

  /* ================= "↑ Top" ================= */
  var topButton = make("button", "to-top", "↑ Top");
  topButton.type = "button";
  topButton.setAttribute("aria-label", "Back to the top of the page");
  topButton.addEventListener("click", function () {
    /* far down, a smooth scroll takes seconds: jump to one screen from the top, glide the rest */
    if (window.scrollY > 2 * window.innerHeight) jump(window.innerHeight);
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
  document.body.appendChild(topButton);

  /* ================= a standalone page ================= */
  if (!BOOK) {
    var file = decodeURIComponent(location.pathname.split("/").pop() || "page");
    var main = document.querySelector("main") || document.body;
    here = { file: file, root: main };
    buildPanel();
    answers = Answers(document, file, document.title, updatePanel);
    updatePanel();
    if (!location.hash) {
      openFootnotes(file, main);
      goToPlace(file, main);
      var again = function () { if (!touched) goToPlace(file, main); };
      if (document.fonts && document.fonts.ready) document.fonts.ready.then(again);
      window.addEventListener("load", again);
    }
    return;
  }

  /* ================= the book ================= */
  var view = document.getElementById("book-view");
  var toc = document.querySelector(".book-toc");
  var pages = {};
  each(document.querySelectorAll("template[data-page]"), function (t) {
    pages[t.getAttribute("data-page")] = { file: t.getAttribute("data-file"), title: t.getAttribute("data-title"), tpl: t };
  });
  var mapData = null;
  var mapScript = document.getElementById("explainer-map");
  if (mapScript) { try { mapData = JSON.parse(mapScript.textContent); } catch (e) { mapData = null; } }
  var map = null;
  var current = null;
  buildPanel();

  function first() {
    var last = load("last", null);
    if (last && (pages[last] || (last === "map" && mapData))) return last;
    return mapData ? "map" : Object.keys(pages)[0];
  }
  function parse() {
    var m = location.hash.match(/^#\/([^\/]+)(?:\/(.+))?$/);
    return m ? { name: decodeURIComponent(m[1]), section: m[2] ? decodeURIComponent(m[2]) : null } : null;
  }
  function go(name, section) {
    var h = "#/" + encodeURIComponent(name) + (section ? "/" + encodeURIComponent(section) : "");
    if (location.hash === h) show(name, section); else location.hash = h;
  }
  function show(name, section) {
    if (!pages[name] && !(name === "map" && mapData)) name = first();
    if (current && current !== name) savePlace(here.file, here.root);
    var same = current === name;
    current = name;
    keep("last", name);
    each(side.querySelectorAll('nav[aria-label="Explainer pages"] a'), function (a) {
      var on = a.getAttribute("href") === "#/" + name;
      if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    if (!same) {
      view.innerHTML = "";
      toc.innerHTML = "";
      touched = false;
      if (name === "map") {
        document.title = mapData.title;
        here = { file: "map", root: view };
        answers = null;
        map = MapView(view, toc, mapData);
      } else {
        var p = pages[name];
        var frag = p.tpl.content.cloneNode(true);
        var t = frag.querySelector(".toc"), c = frag.querySelector(".content");
        while (t && t.firstChild) toc.appendChild(t.firstChild);
        while (c && c.firstChild) view.appendChild(c.firstChild);
        document.title = p.title;
        here = { file: p.file, root: view };
        map = null;
        answers = Answers(view, p.file, p.title, updatePanel);
        openFootnotes(p.file, view);
      }
      updatePanel();
    }
    var land = function () {
      var target = section ? view.querySelector("#" + CSS.escape(section)) : null;
      if (target) jumpTo(target);
      else if (!same) goToPlace(here.file, view);
    };
    land();
    if (section) history.replaceState(null, "", "#/" + encodeURIComponent(name));  /* a reload returns to the place, not the section */
    var mermaids = view.querySelectorAll("pre.mermaid:not([data-processed])");
    if (mermaids.length && window.mermaid) {
      window.mermaid.run({ nodes: mermaids }).then(function () { if (!touched && !section) goToPlace(here.file, view); });
    }
  }

  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("a[href]");
    if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var href = a.getAttribute("href");
    var m = href.match(/^(?:\.\/)?([\w.-]+)\.html(?:#(.*))?$/);
    if (m && m[1] === "index" && m[2] && m[2].charAt(0) === "/") { e.preventDefault(); location.hash = "#" + m[2]; return; }
    if (m && pages[m[1]]) { e.preventDefault(); go(m[1], m[2] || null); return; }
    if (href.charAt(0) === "#" && href.charAt(1) !== "/" && href.length > 1) {
      var target = view.querySelector("#" + CSS.escape(href.slice(1)));
      if (target) { e.preventDefault(); target.scrollIntoView(); }
    }
  });
  document.addEventListener("keydown", function (e) { if (map && current === "map") map.key(e); });
  window.addEventListener("hashchange", function () {
    var r = parse();
    if (r) show(r.name, r.section); else show(first(), null);
  });

  /* ================= the map ================= */
  function MapView(root, tocBox, data) {
    var STATE0 = { view: "layers", selected: null, step: 0 };
    var state = Object.assign({}, STATE0, load("map", {}) || {});
    var byId = {}, usedBy = {};
    data.nodes.forEach(function (n) { byId[n.id] = n; usedBy[n.id] = []; });
    data.nodes.forEach(function (n) { (n.uses || []).forEach(function (u) { if (usedBy[u]) usedBy[u].push(n.id); }); });
    var layerName = {}, stoneName = {};
    data.layers.forEach(function (l) { layerName[l.id] = l.name; });
    (data.milestones || []).forEach(function (m) { stoneName[m.id] = m.name; });
    var steps = (data.trace && data.trace.steps) || [];
    var VIEWS = [["layers", "Layers"], ["roadmap", "Roadmap"]];
    if (steps.length) VIEWS.push(["trace", data.trace.name]);
    function persist() { keep("map", state); }

    /* the frame: title, progress, view buttons, the board, the key */
    var hero = make("header", "hero");
    hero.appendChild(make("span", "eyebrow", "The map"));
    hero.appendChild(make("h1", null, data.title));
    if (data.lede) hero.appendChild(make("p", "lede", data.lede));
    root.appendChild(hero);
    var sec = make("section", "map");
    root.appendChild(sec);
    var count = make("p", "map-count");
    var strip = make("div", "map-strip");
    strip.setAttribute("aria-label", "Every part, by status");
    var tabs = make("div", "map-tabs");
    var traceBar = make("div", "trace-bar");
    var board = make("div", "map-board");
    var key = make("p", "map-key");
    [count, strip, tabs, traceBar, board, key].forEach(function (x) { sec.appendChild(x); });

    var buildable = data.nodes.filter(function (n) { return n.status !== "outside"; });
    var order = ["done", "now", "planned", "later"];
    function tally(st) { return buildable.filter(function (n) { return n.status === st; }).length; }
    count.innerHTML = "<b>" + tally("done") + " of " + buildable.length + " parts built.</b> " +
      tally("now") + " being built now, " + tally("planned") + " more in the plan with a date, " +
      tally("later") + " later.";
    order.forEach(function (st) {
      buildable.filter(function (n) { return n.status === st; }).forEach(function (n) {
        var b = make("button", "cell st-" + st);
        b.type = "button";
        b.setAttribute("data-id", n.id);
        b.title = n.name + ": " + data.statuses[st];
        b.setAttribute("aria-label", b.title);
        b.addEventListener("click", function () { select(n.id); });
        strip.appendChild(b);
      });
    });
    VIEWS.forEach(function (v) {
      var b = make("button", null, v[1]);
      b.type = "button";
      b.setAttribute("data-view", v[0]);
      b.addEventListener("click", function () { setView(v[0]); });
      tabs.appendChild(b);
    });
    var resetB = make("button", "reset", "Reset map");
    resetB.type = "button";
    resetB.addEventListener("click", reset);
    tabs.appendChild(resetB);
    key.innerHTML = order.concat(["outside"]).map(function (st) {
      return '<span class="key-item"><span class="swatch st-' + st + '"></span>' + data.statuses[st] + "</span>";
    }).join("");

    /* the sidebar for the map: its views, as links */
    var tocDiv = make("div");
    tocDiv.appendChild(make("div", "side-label", "On this map"));
    var tocNav = make("nav");
    tocNav.setAttribute("aria-label", "Map views");
    VIEWS.forEach(function (v) {
      var a = make("a", null, v[1]);
      a.href = "#/map";
      a.setAttribute("data-view", v[0]);
      a.addEventListener("click", function (e) { e.preventDefault(); setView(v[0]); jump(0); });
      tocNav.appendChild(a);
    });
    tocDiv.appendChild(tocNav);
    tocBox.appendChild(tocDiv);

    function partButton(n) {
      var b = make("button", "part st-" + n.status);
      b.type = "button";
      b.setAttribute("data-id", n.id);
      b.appendChild(make("span", "part-name", n.name));
      if (n.short) b.appendChild(make("span", "part-short", n.short));
      var when = n.status === "outside" ? "" : n.status === "done" ? "Built" : (stoneName[n.when] || "");
      if (when) b.appendChild(make("span", "part-when", when));
      if (state.view === "trace") {
        var at = [];
        steps.forEach(function (s, i) { if (s.node === n.id) at.push(i + 1); });
        if (at.length) b.appendChild(make("span", "part-step", at.join(", ")));
      }
      b.addEventListener("click", function () { select(state.selected === n.id ? null : n.id); });
      return b;
    }
    function group(head, note, nodes, extra) {
      var g = make("div", "layer" + (extra || ""));
      var h = make("div", "layer-head");
      h.appendChild(make("b", null, head));
      if (note) h.appendChild(make("span", null, note));
      g.appendChild(h);
      var row = make("div", "layer-parts");
      nodes.forEach(function (n) { row.appendChild(partButton(n)); });
      g.appendChild(row);
      return g;
    }
    function link(label, id) {
      var b = make("button", "map-link", label);
      b.type = "button";
      b.addEventListener("click", function () { select(id); });
      return b;
    }
    function detail(n) {
      var d = make("div", "part-detail");
      var where = layerName[n.layer] + " · " + data.statuses[n.status] +
        (n.status !== "outside" && n.status !== "done" && stoneName[n.when] ? ", " + stoneName[n.when] : "");
      d.appendChild(make("span", "eyebrow", where));
      d.appendChild(make("h3", null, n.name));
      if (n.what) d.appendChild(make("p", null, n.what));
      if (n.why) {
        var w = make("p");
        w.appendChild(make("b", null, "The problem it removes. "));
        w.appendChild(document.createTextNode(n.why));
        d.appendChild(w);
      }
      if (n.facts && n.facts.length) {
        var ul = make("ul", "tight");
        n.facts.forEach(function (f) { ul.appendChild(make("li", null, f)); });
        d.appendChild(ul);
      }
      [["Uses", n.uses || []], ["Used by", usedBy[n.id] || []]].forEach(function (pair) {
        if (!pair[1].length) return;
        var p = make("p", "map-links");
        p.appendChild(make("b", null, pair[0] + ": "));
        pair[1].forEach(function (id) { if (byId[id]) p.appendChild(link(byId[id].name, id)); });
        d.appendChild(p);
      });
      if (n.pages && n.pages.length) {
        var r = make("p", "map-links");
        r.appendChild(make("b", null, "Read: "));
        n.pages.forEach(function (pg) {
          var a = make("a", null, pg.label);
          a.href = pg.href;
          r.appendChild(a);
        });
        d.appendChild(r);
      }
      if (n.open && n.open.length) {
        d.appendChild(make("b", null, "Still open"));
        var o = make("ul", "tight");
        n.open.forEach(function (x) { o.appendChild(make("li", null, x)); });
        d.appendChild(o);
      }
      return d;
    }

    function render() {
      each(tabs.querySelectorAll("button[data-view]"), function (b) {
        b.setAttribute("aria-pressed", String(b.getAttribute("data-view") === state.view));
      });
      each(tocNav.querySelectorAll("a"), function (a) {
        if (a.getAttribute("data-view") === state.view) a.setAttribute("aria-current", "true"); else a.removeAttribute("aria-current");
      });
      board.innerHTML = "";
      var groups = [];
      if (state.view === "roadmap") {
        var reached = false;
        data.milestones.forEach(function (m) {
          var nodes = buildable.filter(function (n) { return n.when === m.id; });
          if (!nodes.length) return;
          var next = !reached && nodes.some(function (n) { return n.status !== "done"; });
          if (next) reached = true;
          groups.push(group(m.name, m.note + (next ? " · next up" : ""), nodes, next ? " is-next" : ""));
        });
      } else {
        data.layers.forEach(function (l) {
          var nodes = data.nodes.filter(function (n) { return n.layer === l.id; });
          if (nodes.length) groups.push(group(l.name, l.note, nodes));
        });
      }
      groups.forEach(function (g) { board.appendChild(g); });

      /* the trace: the step's text above the board, and its part marked */
      traceBar.hidden = state.view !== "trace";
      var stepId = null;
      if (state.view === "trace") {
        state.step = Math.max(0, Math.min(state.step, steps.length - 1));
        var s = steps[state.step];
        stepId = s.node;
        traceBar.innerHTML = "";
        if (data.trace.lede) traceBar.appendChild(make("p", "small", data.trace.lede));
        var ctl = make("div", "trace-controls");
        var back = make("button", null, "← Back");
        back.type = "button";
        back.disabled = state.step === 0;
        back.addEventListener("click", function () { step(-1); });
        var fwd = make("button", null, "Next →");
        fwd.type = "button";
        fwd.disabled = state.step === steps.length - 1;
        fwd.addEventListener("click", function () { step(1); });
        ctl.appendChild(back);
        ctl.appendChild(make("span", "trace-count", "Step " + (state.step + 1) + " of " + steps.length));
        ctl.appendChild(fwd);
        traceBar.appendChild(ctl);
        var t = make("p", "trace-text");
        t.appendChild(make("b", null, byId[s.node].name + ". "));
        t.appendChild(document.createTextNode(s.text));
        traceBar.appendChild(t);
      }

      /* selection: the picked part, what it uses and what uses it; the rest steps back */
      var sel = state.selected && byId[state.selected] ? state.selected : null;
      var related = {};
      if (sel) {
        (byId[sel].uses || []).concat(usedBy[sel]).forEach(function (id) { related[id] = true; });
      }
      var inTrace = {};
      steps.forEach(function (s2, i) { if (i <= state.step) inTrace[s2.node] = true; });
      each(board.querySelectorAll(".part"), function (b) {
        var id = b.getAttribute("data-id");
        b.classList.toggle("is-selected", id === sel);
        b.classList.toggle("is-step", id === stepId);
        var dim = false;
        if (state.view === "trace") dim = !inTrace[id] && id !== sel;
        else if (sel) dim = id !== sel && !related[id];
        b.classList.toggle("is-dim", dim);
        b.setAttribute("aria-pressed", String(id === sel));
      });
      if (sel) {
        var holder = board.querySelector('.part[data-id="' + CSS.escape(sel) + '"]').closest(".layer");
        holder.parentNode.insertBefore(detail(byId[sel]), holder.nextSibling);
      }
      each(strip.querySelectorAll(".cell"), function (c) { c.classList.toggle("is-selected", c.getAttribute("data-id") === sel); });
    }
    function select(id) {
      state.selected = id;
      persist();
      render();
      var d = id && board.querySelector(".part-detail");
      if (d) d.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
    function setView(v) { state.view = v; persist(); render(); }
    function step(dx) {
      state.step = Math.max(0, Math.min(steps.length - 1, state.step + dx));
      persist();
      render();
      var b = board.querySelector(".part.is-step");
      if (b) {
        var r = b.getBoundingClientRect(), barBottom = traceBar.getBoundingClientRect().bottom;
        if (r.top < barBottom || r.bottom > window.innerHeight) {
          window.scrollTo({ top: window.scrollY + r.top - barBottom - 24, behavior: "smooth" });
        }
      }
    }
    function reset() { state = Object.assign({}, STATE0); forget("map"); render(); }
    function onKey(e) {
      if (state.view !== "trace" || typing(e)) return;
      if (e.key === "ArrowRight") { e.preventDefault(); step(1); }
      if (e.key === "ArrowLeft") { e.preventDefault(); step(-1); }
    }
    render();
    return { reset: reset, key: onKey };
  }

  /* open where the address points, or where the reader left off */
  var start = parse();
  if (start) show(start.name, start.section); else go(first(), null);
  var again = function () { if (!touched && current) goToPlace(here.file, here.root); };
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(again);
})();
