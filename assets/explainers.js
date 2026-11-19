/* Explainer pages: tests and questions answered in the page, remembered in this browser.
   .quiz    a test: pick one option; a wrong pick shows why and allows another; the first try counts.
   .choice  a question for the reader: my recommendation (.rec, .rec-why) shows only after a pick.
   .answer-field  a free note (e.g. "disagree with any decision?").
   Answers live in localStorage under "explainers:<file name>", keyed by each block's id, and each
   option is stored by its text, so a later edit of the page never points an answer at the wrong option.
   The sidebar gets the progress, "Copy for Claude" and "Start over". build.py copies this file. */
(function () {
  "use strict";
  var file = decodeURIComponent(location.pathname.split("/").pop() || "page");
  var KEY = "explainers:" + file;
  var store = {};
  try { store = JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch (e) { store = {}; }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(store)); } catch (e) { /* private window */ } }

  function each(list, fn) { Array.prototype.forEach.call(list, fn); }
  function num(el) { var n = el.querySelector(".num"); return n ? n.textContent.trim() : ""; }
  function plain(el) {
    var c = el.cloneNode(true);
    each(c.querySelectorAll(".num, .why, .rec-tag, .label-line"), function (x) { x.remove(); });
    return c.textContent.replace(/\s+/g, " ").trim();
  }
  function options(box) {
    var found = box.querySelectorAll(":scope > .opts > li, :scope tbody > tr");
    return Array.prototype.slice.call(found);
  }
  function key(opt) { return plain(opt).slice(0, 80); }
  function short(opt) {  /* an option's own words: its first cell, cut at about 70 characters */
    var s = plain(opt.querySelector("td") || opt);
    return s.length > 70 ? s.slice(0, 70).replace(/\s+\S*$/, "") + "…" : s;
  }
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

  /* ---------------- tests ---------------- */
  each(document.querySelectorAll(".quiz[id]"), function (q) {
    var opts = options(q);
    var keys = opts.map(key);
    var right = opts.findIndex(function (o) { return o.classList.contains("right"); });
    var verdict = document.createElement("p");
    verdict.className = "verdict";
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
        save(); paint(); bar();
      });
    });
    paint();
    tests.push({ box: q, tries: tries, right: right, opts: opts });
  });

  /* ---------------- questions for the reader ---------------- */
  each(document.querySelectorAll(".choice[id]"), function (c) {
    var opts = options(c);
    var keys = opts.map(key);
    var rec = opts.findIndex(function (o) { return o.classList.contains("rec"); });
    var why = c.querySelector(".rec-why");
    var verdict = document.createElement("p");
    verdict.className = "verdict";
    verdict.setAttribute("aria-live", "polite");
    if (why) c.insertBefore(verdict, why); else c.appendChild(verdict);
    var note = document.createElement("textarea");
    note.className = "answer-note";
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
        if (p >= 0 && i === rec && !tag) {
          tag = document.createElement("span");
          tag.className = "rec-tag";
          tag.textContent = "My recommendation";
          (o.querySelector("td") || o).appendChild(tag);
        }
        if (tag && !(p >= 0 && i === rec)) tag.remove();
      });
      verdict.textContent = p < 0 ? "" : p === rec
        ? "You picked " + num(opts[p]) + ". I'd pick the same."
        : "You picked " + num(opts[p]) + ". I'd recommend " + num(opts[rec]) + ".";
    }
    opts.forEach(function (o, i) {
      clickable(o, function () {
        var s = store[c.id] || {};
        s.pick = keys[i];
        s.at = Date.now();
        store[c.id] = s;
        save(); paint(); bar();
      });
    });
    note.value = (store[c.id] && store[c.id].note) || "";
    note.addEventListener("input", function () {
      var s = store[c.id] || {};
      s.note = note.value;
      store[c.id] = s;
      save(); bar();
    });
    paint();
    choices.push({ box: c, picked: picked, rec: rec, opts: opts });
  });

  /* ---------------- free notes ---------------- */
  each(document.querySelectorAll(".answer-field[id]"), function (f) {
    var note = document.createElement("textarea");
    note.className = "answer-note";
    note.rows = 3;
    note.placeholder = f.getAttribute("data-placeholder") || "Your answer";
    f.appendChild(note);
    note.value = (store[f.id] && store[f.id].note) || "";
    note.addEventListener("input", function () { store[f.id] = { note: note.value, at: Date.now() }; save(); bar(); });
    fields.push({ box: f });
  });

  /* ---------------- the sidebar: progress, copy, start over ---------------- */
  var side = document.querySelector("aside");
  var panel = null;
  function results() {
    var out = [document.title + " (" + file + ")"];
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
  function copy(text, button) {
    function done(ok) {
      button.textContent = ok ? "Copied: paste it to Claude" : "Select the text below and copy it";
      setTimeout(function () { button.textContent = "Copy for Claude"; }, 2500);
    }
    function fallback() {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.className = "answer-note";
      ta.rows = 6;
      panel.appendChild(ta);
      ta.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
      if (ok) ta.remove();
      done(ok);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { done(true); }, fallback);
    } else fallback();
  }
  function bar() {
    if (!side || !(tests.length || choices.length || fields.length)) return;
    if (!panel) {
      panel = document.createElement("div");
      panel.className = "answers";
      panel.innerHTML = '<span class="eyebrow">Your answers</span><p class="progress"></p>' +
        '<div class="buttons"><button type="button" class="copy">Copy for Claude</button>' +
        '<button type="button" class="reset">Start over</button></div>';
      side.appendChild(panel);
      panel.querySelector(".copy").addEventListener("click", function () { copy(results(), this); });
      panel.querySelector(".reset").addEventListener("click", function () {
        if (!confirm("Clear every answer on this page?")) return;
        store = {}; save(); location.reload();
      });
    }
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
    panel.querySelector(".progress").innerHTML = parts.join("<br>");
  }
  bar();
})();
