/* Tiny SVG chart kit for the Storm Desk: a line chart over years (one series with an area wash, or
 * several series with a legend; optional shaded year bands), a horizontal ranked bar chart, and a
 * paired-dot ("dumbbell") Then -> Now comparison. Every chart gets a hover/focus tooltip and a table
 * view. Data text is always set with textContent. No dependencies. */
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const nf = new Intl.NumberFormat("en-US");
  const BASE = () => window.WW_BASE || "";

  function fmtMoney(v) {
    if (v >= 1e9) return "$" + (v / 1e9).toFixed(1) + "B";
    if (v >= 1e6) return "$" + (v / 1e6).toFixed(1) + "M";
    if (v >= 1e3) return "$" + Math.round(v / 1e3) + "K";
    return "$" + Math.round(v);
  }
  const FORMATS = { events: nf.format, deaths: nf.format, injuries: nf.format, damage: fmtMoney };
  const LABELS = { events: "Events", deaths: "Deaths", injuries: "Injuries", damage: "Reported damage" };

  function el(tag, attrs, parent) {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function h(tag, cls, text, parent) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    if (parent) parent.appendChild(n);
    return n;
  }

  function niceTicks(max, count = 4) {
    if (!(max > 0)) return [0, 1];
    const raw = max / count, mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw);
    const ticks = [];
    for (let v = 0; v <= max + step * 0.001; v += step) ticks.push(+v.toPrecision(12));
    if (ticks[ticks.length - 1] < max) ticks.push(+(ticks[ticks.length - 1] + step).toPrecision(12));
    return ticks;
  }
  function shortNum(v) {
    if (v >= 1e9) return (v / 1e9).toFixed(v % 1e9 ? 1 : 0) + "B";
    if (v >= 1e6) return (v / 1e6).toFixed(v % 1e6 ? 1 : 0) + "M";
    if (v >= 1e3) return (v / 1e3).toFixed(v % 1e3 ? 1 : 0) + "K";
    return String(+v.toFixed(2));
  }
  const tickLabel = (metric, t) => (metric === "damage" ? "$" + shortNum(t) : shortNum(t));

  /* Frame: title, subtitle, optional legend, table toggle, a chart body and a hidden table.
   * table = {head: [..], num: [bool per column], rows: [[text, ...], ...]} */
  function frameWith(root, { title, sub, legend, table }) {
    root.innerHTML = "";
    const head = h("div", "chart-head", null, root);
    h("p", "chart-title", title, head);
    const btn = h("button", "chart-toggle", "Table", head);
    btn.type = "button";
    h("p", "chart-sub", sub || "", root);
    if (legend && legend.length) {
      const lg = h("ul", "chart-legend", null, root);
      for (const item of legend) {
        const li = h("li", null, null, lg);
        h("span", `key key-${item.key || "dot"} ${item.cls || "s1"}`, null, li).setAttribute("aria-hidden", "true");
        li.appendChild(document.createTextNode(item.label));
      }
    }
    const body = h("div", "chart", null, root);
    const t = h("table", "chart-table", null, root);
    t.hidden = true;
    const tr = h("tr", null, null, h("thead", null, null, t));
    table.head.forEach((c, i) => h("th", table.num[i] ? "num" : "", c, tr));
    const tb = h("tbody", null, null, t);
    for (const row of table.rows) {
      const r = h("tr", null, null, tb);
      row.forEach((c, i) => h("td", table.num[i] ? "num" : "", c, r));
    }
    btn.onclick = () => {
      t.hidden = !t.hidden; body.hidden = !t.hidden;
      btn.textContent = t.hidden ? "Table" : "Chart";
    };
    const tip = h("div", "chart-tip", null, root);
    tip.hidden = true;
    return { body, tip };
  }
  function frame(root, title, sub, rows, colName, fmt) {
    return frameWith(root, { title, sub, table: { head: [colName, title], num: [false, true],
      rows: rows.map(([k, v]) => [String(k), fmt(v)]) } });
  }

  /* Tooltip content from lines of parts: a string, {b: "bold value"}, or {key: "s1"} (a line key). */
  function showTip(root, tip, x, y, lines) {
    tip.textContent = "";
    lines.forEach((parts, i) => {
      const row = h("div", i ? null : "tip-head", null, tip);
      for (const p of parts) {
        if (typeof p === "string") row.appendChild(document.createTextNode(p));
        else if (p.key) h("span", `tip-key ${p.key}`, null, row).setAttribute("aria-hidden", "true");
        else h("b", null, p.b, row);
      }
    });
    tip.hidden = false;
    const r = root.getBoundingClientRect();
    const w = tip.offsetWidth / 2;
    tip.style.left = Math.max(w, Math.min(r.width - w, x)) + "px";
    tip.style.top = y + "px";
  }

  /* Years on x, one measure on y.
   *   Single series: data: [{x: 1950, y: 223}, ...]
   *   Several:       series: [{name, cls: "s1", data: [{x, y}, ...]}, ...] (cls picks the palette slot)
   *   bands:         [{from: 1955, to: 1974, label: "Then"}, ...] shaded year ranges behind the lines
   *   format:        optional value formatter (default FORMATS[metric]); unit: tooltip word after values */
  function line(root, { title, sub, data, series, bands = [], metric = "events", format, unit }) {
    const fmt = format || FORMATS[metric];
    const multi = Array.isArray(series);
    const S = multi ? series : [{ name: title, cls: "s1", data: data || [] }];
    const years = [...new Set(S.flatMap(s => s.data.map(d => d.x)))].sort((a, b) => a - b);
    const maps = S.map(s => new Map(s.data.map(d => [d.x, d.y])));
    const table = multi
      ? { head: ["Year", ...S.map(s => s.name)], num: [false, ...S.map(() => true)],
          rows: years.map(x => [String(x), ...maps.map(m => (m.has(x) ? fmt(m.get(x)) : "–"))]) }
      : { head: ["Year", title], num: [false, true], rows: S[0].data.map(d => [String(d.x), fmt(d.y)]) };
    const { body, tip } = frameWith(root, { title, sub, table,
      legend: multi ? S.map(s => ({ label: s.name, cls: s.cls, key: "line" })) : null });
    if (!years.length) { h("p", "chart-loading", "No matching events.", body); return; }
    const W = Math.max(body.clientWidth, 280), H = Math.round(Math.min(300, Math.max(200, W * 0.32)));
    const m = { t: bands.length ? 22 : 10, r: 12, b: 24, l: 44 };
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": title }, body);
    const x0 = years[0], x1 = years[years.length - 1];
    const ticks = niceTicks(Math.max(...S.flatMap(s => s.data.map(d => d.y))));
    const yMax = ticks[ticks.length - 1];
    const X = v => m.l + (x1 === x0 ? 0.5 : (v - x0) / (x1 - x0)) * (W - m.l - m.r);
    const Y = v => H - m.b - (v / yMax) * (H - m.t - m.b);

    // Era bands sit behind everything; a half-year pad makes a band cover its end years' points.
    for (const b of bands) {
      const a = Math.max(x0, b.from), z = Math.min(x1, b.to);
      if (a > z) continue;
      const pad = x1 === x0 ? 0 : 0.5 * (W - m.l - m.r) / (x1 - x0);
      const bx = Math.max(m.l, X(a) - pad), bw = Math.min(W - m.r, X(z) + pad) - bx;
      el("rect", { class: "band", x: bx, y: m.t, width: bw, height: H - m.t - m.b }, svg);
      if (b.label) el("text", { class: "band-label", x: bx + bw / 2, y: m.t - 7, "text-anchor": "middle" }, svg).textContent = b.label;
    }
    ticks.forEach(t => {
      el("line", { class: "grid-line", x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t) }, svg);
      el("text", { x: m.l - 8, y: Y(t) + 4, "text-anchor": "end" }, svg).textContent = tickLabel(metric, t);
    });
    const span = x1 - x0, step = span > 40 ? 10 : span > 15 ? 5 : span > 6 ? 2 : 1;
    for (let yr = Math.ceil(x0 / step) * step; yr <= x1; yr += step)
      el("text", { x: X(yr), y: H - 6, "text-anchor": "middle" }, svg).textContent = yr;

    S.forEach((s, i) => {
      if (!s.data.length) return;
      const pts = s.data.map(d => `${X(d.x).toFixed(1)},${Y(d.y).toFixed(1)}`);
      const a = s.data[0].x, z = s.data[s.data.length - 1].x;
      if (!multi) el("path", { class: "area", d: `M${X(a)},${Y(0)}L${pts.join("L")}L${X(z)},${Y(0)}Z` }, svg);
      el("path", { class: `line ${s.cls || "s" + (i + 1)}`, d: "M" + pts.join("L") }, svg);
      const last = s.data[s.data.length - 1];
      el("circle", { class: `dot ${s.cls || "s" + (i + 1)}`, cx: X(last.x), cy: Y(last.y), r: 4 }, svg);
    });

    const cursor = el("line", { class: "cursor", y1: m.t, y2: H - m.b, visibility: "hidden" }, svg);
    const hots = S.map((s, i) => el("circle", { class: `dot ${s.cls || "s" + (i + 1)}`, r: 5, visibility: "hidden" }, svg));
    const hit = el("rect", { x: m.l, y: 0, width: W - m.l - m.r, height: H, fill: "transparent", tabindex: 0,
      "aria-label": `${title}: use the table view for every value` }, svg);
    const word = unit != null ? unit : LABELS[metric].toLowerCase();
    function show(yr) {
      yr = Math.max(x0, Math.min(x1, yr));
      cursor.setAttribute("x1", X(yr)); cursor.setAttribute("x2", X(yr)); cursor.setAttribute("visibility", "visible");
      let top = H;
      S.forEach((s, i) => {
        const v = maps[i].get(yr);
        if (v == null) { hots[i].setAttribute("visibility", "hidden"); return; }
        hots[i].setAttribute("cx", X(yr)); hots[i].setAttribute("cy", Y(v)); hots[i].setAttribute("visibility", "visible");
        top = Math.min(top, Y(v));
      });
      const p = svg.getBoundingClientRect(), scale = W / p.width, rb = root.getBoundingClientRect();
      const lines = multi
        ? [[String(yr)], ...S.map((s, i) => [{ key: s.cls || "s" + (i + 1) },
            { b: maps[i].has(yr) ? fmt(maps[i].get(yr)) : "–" }, " " + s.name])]
        : [[`${yr} · `, { b: fmt(maps[0].get(yr) || 0) }, word ? " " + word : ""]];
      showTip(root, tip, p.left - rb.left + X(yr) / scale, p.top - rb.top + top / scale, lines);
    }
    function hide() {
      tip.hidden = true; cursor.setAttribute("visibility", "hidden");
      hots.forEach(c => c.setAttribute("visibility", "hidden"));
    }
    let focusYear = x1;
    hit.addEventListener("pointermove", ev => {
      const p = svg.getBoundingClientRect(), scale = W / p.width;
      show(focusYear = Math.round(x0 + ((ev.clientX - p.left) * scale - m.l) / (W - m.l - m.r) * (x1 - x0)));
    });
    hit.addEventListener("pointerleave", hide);
    hit.addEventListener("focus", () => show(focusYear));
    hit.addEventListener("blur", hide);
    hit.addEventListener("keydown", ev => {
      const d = { ArrowLeft: -1, ArrowRight: 1 }[ev.key];
      if (!d) return;
      ev.preventDefault();
      show(focusYear = Math.max(x0, Math.min(x1, focusYear + d)));
    });
  }

  /* Ranked horizontal bars. data: [{label, value}, ...] already sorted. */
  function bars(root, { title, sub, data, metric = "events", colName = "", onPick }) {
    const fmt = FORMATS[metric];
    const { body, tip } = frame(root, title, sub, data.map(d => [d.label, d.value]), colName, fmt);
    if (!data.length) { h("p", "chart-loading", "No matching events.", body); return; }
    const W = Math.max(body.clientWidth, 260), row = 26, bar = 16, labelW = Math.min(150, W * 0.38), valW = 64;
    const H = data.length * row + 4;
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": title }, body);
    const max = Math.max(...data.map(d => d.value)) || 1;
    const plotW = W - labelW - valW;
    el("line", { class: "axis-line", x1: labelW, x2: labelW, y1: 0, y2: H }, svg);
    data.forEach((d, i) => {
      const y = i * row + (row - bar) / 2, w = Math.max(2, (d.value / max) * plotW), r = Math.min(4, w / 2);
      const g = el("g", { style: onPick ? "cursor:pointer" : "" }, svg);
      const lbl = el("text", { x: labelW - 8, y: y + bar / 2 + 4, "text-anchor": "end" }, g);
      lbl.textContent = d.label.length > 20 ? d.label.slice(0, 19) + "…" : d.label;
      // Square at the baseline, 4px rounded at the data end.
      el("path", { class: "mark", d: `M${labelW},${y}h${w - r}a${r},${r} 0 0 1 ${r},${r}v${bar - 2 * r}a${r},${r} 0 0 1 -${r},${r}h-${w - r}Z` }, g);
      el("text", { class: "val", x: labelW + w + 6, y: y + bar / 2 + 4 }, g).textContent = fmt(d.value);
      const hit = el("rect", { x: 0, y: i * row, width: W, height: row, fill: "transparent" }, g);
      hit.addEventListener("pointerenter", () => {
        svg.querySelectorAll(".mark").forEach(n => n.classList.add("dim"));
        g.querySelector(".mark").classList.remove("dim");
        const p = svg.getBoundingClientRect(), rb = root.getBoundingClientRect(), s = p.width / W;
        showTip(root, tip, p.left - rb.left + (labelW + w / 2) * s, p.top - rb.top + y * s,
          [[`${d.label} · `, { b: fmt(d.value) }, onPick ? " · click to filter" : ""]]);
      });
      hit.addEventListener("pointerleave", () => {
        tip.hidden = true; svg.querySelectorAll(".mark").forEach(n => n.classList.remove("dim"));
      });
      if (onPick) hit.addEventListener("click", () => onPick(d.label));
    });
  }

  // ---- Then & Now helpers (docs/THEN_AND_NOW.md); then-now.js and the [[then-now]] shortcode share them.
  const MINUS = "−";
  /* A per-year average: two significant digits under 1 (0.05, 0.6), one decimal under 10 (4.2 deaths
   * a year), whole numbers above. A nonzero average never shows as 0. */
  function fmtAvg(metric, v) {
    if (metric === "damage") return fmtMoney(v);
    if (v > 0 && v < 1) return String(+v.toPrecision(2));
    if (v > 0 && v < 10) return v.toFixed(1);
    return nf.format(Math.round(v));
  }
  /* then -> now as "+12%", "−8%", "0%", "new" (then is 0), or "–" (both 0). A drop to a nonzero
   * value never rounds to −100%: it shows as at most −99.9%. */
  function pctChange(a, b) {
    if (!a) return b ? "new" : "–";
    const p = (b - a) / a * 100, ab = Math.abs(p);
    if (p < 0 && b > 0 && ab >= 99.5) return MINUS + (ab >= 99.95 ? "99.9" : ab.toFixed(1)) + "%";
    const q = ab < 10 ? +ab.toFixed(1) : Math.round(ab);
    return q === 0 ? "0%" : (p > 0 ? "+" : MINUS) + nf.format(q) + "%";
  }
  /* Under one event, death or injury a year in Then, a percent change says more about small numbers
   * than about change: such changes are shown as a per-year difference instead. */
  const smallBase = (metric, a) => metric !== "damage" && a > 0 && a < 1;
  function perYearDiff(metric, a, b) {
    const d = b - a;
    return d === 0 ? "0/yr" : (d > 0 ? "+" : MINUS) + fmtAvg(metric, Math.abs(d)) + "/yr";
  }
  const eraText = e => (e.from === e.to ? String(e.from) : `${e.from}–${e.to}`);
  const NOUN = { events: "recorded events", deaths: "deaths", injuries: "injuries", damage: "damage" };
  /* "recorded events a year" / "in damage a year (2024 dollars)" */
  function perYearWords(metric, r) {
    if (metric === "damage") return `a year in damage (${r.dollars === "nominal" ? "dollars as reported" : r.base_year + " dollars"})`;
    return `${NOUN[metric]} a year`;
  }
  const listText = a => (a.length < 3 ? a.join(" and ") : a.slice(0, -1).join(", ") + " and " + a[a.length - 1]);
  const total = (v, e) => nf.format(Math.round(v * e.years));
  const nominalNote = r => `Dollars as reported come from different years, so they aren't compared as a percent; ` +
    `choose ${r.base_year} dollars to compare them.`;

  /* The paired-dot comparison. rows: [{label, a, b, aMissing?, bMissing?, aText?, bText?, change?, note?}];
   * a = Then (slot 1), b = Now (slot 2). A side flagged missing wasn't recorded through that era: it gets
   * no dot and no change, and shows aText/bText (default "not recorded"). change overrides the percent. */
  function dumbbell(root, { title, sub, rows, aName, bName, format, tickFormat = shortNum, colName = "Event type", unit = "" }) {
    const fmt0 = format || nf.format;
    const NR = "not recorded";
    const fmtA = r => (r.aMissing ? r.aText || NR : fmt0(r.a)), fmtB = r => (r.bMissing ? r.bText || NR : fmt0(r.b));
    const change = r => (r.change != null ? r.change : r.aMissing || r.bMissing ? "n/a" : pctChange(r.a, r.b));
    const { body, tip } = frameWith(root, { title, sub,
      legend: [{ label: aName, cls: "s1" }, { label: bName, cls: "s2" }],
      table: { head: [colName, aName, bName, "Change"], num: [false, true, true, true],
               rows: rows.map(r => [r.label, fmtA(r), fmtB(r), change(r)]) } });
    if (!rows.length) { h("p", "chart-loading", "No event types to compare.", body); return; }
    const W = Math.max(body.clientWidth, 280), row = 34, axisH = 22;
    const labelW = Math.min(150, Math.round(W * 0.34)), chgW = 58;
    const plot = { l: labelW + 10, r: W - chgW - 10 };
    const H = rows.length * row + axisH;
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": title }, body);
    const ticks = niceTicks(Math.max(...rows.flatMap(r => [r.aMissing ? 0 : r.a, r.bMissing ? 0 : r.b])));
    const xMax = ticks[ticks.length - 1];
    const X = v => plot.l + (v / xMax) * (plot.r - plot.l);
    ticks.forEach(t => {
      el("line", { class: "grid-line", x1: X(t), x2: X(t), y1: 0, y2: H - axisH }, svg);
      el("text", { x: X(t), y: H - 6, "text-anchor": "middle" }, svg).textContent = tickFormat(t);
    });
    const groups = [];
    rows.forEach((r, i) => {
      const cy = i * row + row / 2;
      const g = el("g", { class: "pair", tabindex: 0, role: "listitem",
        "aria-label": `${r.label}: ${aName} ${fmtA(r)}, ${bName} ${fmtB(r)}, change ${change(r)}` }, svg);
      groups.push(g);
      el("text", { x: labelW, y: cy + 4, "text-anchor": "end" }, g).textContent =
        r.label.length > 22 ? r.label.slice(0, 21) + "…" : r.label;
      if (!r.aMissing && !r.bMissing)
        el("line", { class: "pair-link", x1: X(Math.min(r.a, r.b)), x2: X(Math.max(r.a, r.b)), y1: cy, y2: cy }, g);
      if (!r.aMissing) el("circle", { class: "dot s1", cx: X(r.a), cy, r: 5 }, g);
      if (!r.bMissing) el("circle", { class: "dot s2", cx: X(r.b), cy, r: 5 }, g);
      el("text", { class: "val", x: W, y: cy + 4, "text-anchor": "end" }, g).textContent = change(r);
      const hit = el("rect", { x: 0, y: i * row, width: W, height: row, fill: "transparent" }, g);
      const show = () => {
        groups.forEach(n => n.classList.toggle("dim", n !== g));
        const p = svg.getBoundingClientRect(), rb = root.getBoundingClientRect(), s = p.width / W;
        const mid = r.aMissing ? r.b : r.bMissing ? r.a : (r.a + r.b) / 2;
        const lines = [
          [r.label],
          [{ key: "s1" }, { b: fmtA(r) }, ` ${unit}${unit ? " · " : ""}${aName}`],
          [{ key: "s2" }, { b: fmtB(r) }, ` ${unit}${unit ? " · " : ""}${bName}`],
          [`Change: ${change(r)}`],
        ];
        if (r.note) lines.push([r.note]);
        showTip(root, tip, p.left - rb.left + X(mid) * s, p.top - rb.top + (cy - 8) * s, lines);
      };
      const hide = () => { tip.hidden = true; groups.forEach(n => n.classList.remove("dim")); };
      hit.addEventListener("pointerenter", show);
      hit.addEventListener("pointerleave", hide);
      g.addEventListener("focus", show);
      g.addEventListener("blur", hide);
    });
    svg.setAttribute("role", "list");
    svg.setAttribute("aria-label", title);
  }

  /* The table cell for a toll that wasn't recorded through an era: "recorded from 1993" when its first
   * nonzero value falls inside the era, else "not recorded". */
  function gapCell(c, metric, e) {
    const first = c.first_recorded && c.first_recorded[metric];
    return first && first > e.from && first <= e.to ? `recorded from ${first}` : "not recorded";
  }

  /* The Then -> Now comparison chart for one thenNow() result and measure. */
  function compareChart(root, r, metric, sub) {
    const nominal = metric === "damage" && r.dollars === "nominal";
    const rows = r.comparable.map(c => {
      const row = { label: c.type, a: c.then[metric], b: c.now[metric] };
      const notes = [];
      if (metric !== "events" && c.recorded) {
        row.aMissing = !c.recorded.then[metric];
        row.bMissing = !c.recorded.now[metric];
        if (row.aMissing) row.aText = gapCell(c, metric, r.then);
        if (row.bMissing) row.bText = gapCell(c, metric, r.now);
        if (row.aMissing || row.bMissing) notes.push(tollGap(c, metric, r));
      }
      if (!row.aMissing && !row.bMissing) {
        if (nominal) { row.change = "n/a"; notes.push(nominalNote(r)); }
        else if (smallBase(metric, row.a)) {
          row.change = perYearDiff(metric, row.a, row.b);
          notes.push(`Fewer than one a year in ${eraText(r.then)} (${total(row.a, r.then)} in all), so the change is shown per year, not as a percent.`);
        }
      }
      if (c.related && c.related.length)
        notes.push(`Related types recorded separately aren't in these figures: ${listText(c.related.map(x => x.type))}.`);
      if (notes.length) row.note = notes.join(" ");
      return row;
    });
    const where = r.state || "All states";
    keep(root, () => dumbbell(root, {
      title: `${metric === "events" ? "Recorded events" : metric === "damage" ? "Damage" : LABELS[metric]} per year, ${eraText(r.then)} vs ${eraText(r.now)}`,
      sub: sub || [where, "per-year averages", "types recorded in every year of both eras",
        metric === "damage" ? (r.dollars === "nominal" ? "dollars as reported" : `${r.base_year} dollars`) : "",
        "NOAA Storm Events"].filter(Boolean).join(" · "),
      rows, aName: `Then ${eraText(r.then)}`, bName: `Now ${eraText(r.now)}`,
      format: v => fmtAvg(metric, v), tickFormat: t => tickLabel(metric, t),
    }));
  }

  /* Comparable types whose toll (deaths/injuries/damage) wasn't recorded through the whole of one era. */
  const unmeasured = (r, metric) => (metric === "events" ? [] :
    r.comparable.filter(c => c.recorded && (!c.recorded.then[metric] || !c.recorded.now[metric])));
  function tollGap(c, metric, r) {
    const e = !c.recorded.then[metric] ? r.then : r.now;
    const first = c.first_recorded && c.first_recorded[metric];
    if (first && first > e.from && first <= e.to)
      return `The records hold ${metric} for ${c.type} only from ${first}, part-way through ${eraText(e)}, so it isn't compared.`;
    return `The records hold no ${metric} at all for ${c.type} in ${eraText(e)}` + (first ? `; the first is in ${first}.` : ".");
  }

  /* Sentences on the related types (same family, recorded separately) a compared type leaves out. */
  function relatedText(c, metric, r) {
    const words = metric === "damage" ? `a year in damage` : `${NOUN[metric]} a year`;
    return (c.related || []).map(x => {
      const when = x.since != null ? `recorded every year since ${x.since}` : `recorded in some years from ${x.first} to ${x.last}`;
      return `${c.type} is compared, but NOAA also records related events as ${x.type} (${when}), which isn't: ` +
        `${x.type} holds ${fmtAvg(metric, x.then[metric])} ${words} in ${eraText(r.then)} and ${fmtAvg(metric, x.now[metric])} in ` +
        `${eraText(r.now)} that the ${c.type} figures leave out.`;
    });
  }

  /* One sentence on the comparable types' combined per-year average for the measure. Types whose
   * toll wasn't recorded through both eras are left out of the sum, and the sentence says so. */
  function summarySentence(r, metric) {
    const gaps = unmeasured(r, metric);
    const use = r.comparable.filter(c => !gaps.includes(c));
    const sum = k => use.reduce((s, c) => s + c[k][metric], 0);
    const a = sum("then"), b = sum("now"), n = r.comparable.length;
    const where = r.state ? `the records for ${r.state}` : "the national records";
    if (!n) return `No event type was recorded in every year of both ${eraText(r.then)} and ${eraText(r.now)}, so there is nothing to compare fairly.`;
    const types = n <= 4 ? ` (${listText(r.comparable.map(c => c.type))})` : "";
    const lead = `Counting only the ${n === 1 ? "event type" : n + " event types"} recorded in every year of both eras${types}`;
    const word = metric;
    const firsts = gaps.filter(c => c.first_recorded[metric]).map(c => `${c.type} ${c.first_recorded[metric]}`);
    const gapText = gaps.length
      ? ` ${listText(gaps.map(c => c.type))} ${gaps.length === 1 ? "is" : "are"} left out of the ${word} figures: ` +
        `the national records don't hold ${word} for ${gaps.length === 1 ? "it" : "them"} from the start of both eras` +
        (firsts.length ? ` (first recorded: ${firsts.join(", ")})` : "") + "."
      : "";
    const rel = use.filter(c => c.related && c.related.length);
    const relText = rel.length
      ? ` Related events NOAA records separately as ${listText([...new Set(rel.flatMap(c => c.related.map(x => x.type)))])} ` +
        `aren't in these figures (see "What the record can't tell us").`
      : "";
    if (!use.length) return `${lead}, none has ${word} recorded through both eras, so there is no fair ${word} comparison here.${gapText}`;
    const scope = gaps.length ? ` from ${listText(use.map(c => c.type))}` : "";
    let tail;
    if (metric === "damage" && r.dollars === "nominal") tail = `. ${nominalNote(r)}`;
    else if (smallBase(metric, a)) tail = ` (fewer than one a year in ${eraText(r.then)}, so no percent change is given).`;
    else { const change = pctChange(a, b); tail = change === "–" || change === "new" ? "." : ` (${change}).`; }
    return `${lead}, ${where} show ${fmtAvg(metric, a)} ${perYearWords(metric, r)}${scope} in ${eraText(r.then)} and ` +
      `${fmtAvg(metric, b)} in ${eraText(r.now)}` + tail + gapText + relText;
  }

  /* The tornado lens in one sentence, with the real numbers. The records count county segments of
   * tornado tracks (one row per county a tornado crossed), so the sentence counts segments. */
  function tornadoSentence(r) {
    const t = r.tornado;
    if (!t) return "";
    const T = eraText(r.then), N = eraText(r.now);
    const lead = r.state ? `In ${r.state}, recorded tornado segments` : "Recorded tornado segments";
    if (!t.then.weak && !t.then.strong && !t.now.weak && !t.now.strong && !t.then.unknown && !t.now.unknown)
      return `No tornado segments were recorded${r.state ? " in " + r.state : ""} in ${T} or ${N}.`;
    const f = v => fmtAvg("events", v);
    const chg = (a, b) => {
      if (smallBase("events", a)) return ` (${total(a, r.then)} in all in ${T}, ${total(b, r.now)} in ${N})`;
      const c = pctChange(a, b); return c === "–" ? "" : c === "new" ? " (none before)" : ` (${c})`;
    };
    let s = `${lead} (one per county a tornado crossed) rated F/EF2 or stronger averaged ${f(t.then.strong)} a year in ${T} and ${f(t.now.strong)} a year in ${N}${chg(t.then.strong, t.now.strong)}; ` +
      `weaker F/EF0–1 segments went from ${f(t.then.weak)} to ${f(t.now.weak)} a year${chg(t.then.weak, t.now.weak)}.`;
    if (t.then.unknown || t.now.unknown)
      s += ` Unrated segments (${f(t.then.unknown)} and ${f(t.now.unknown)} a year) are in neither group.`;
    return s;
  }

  /* Cited notes on reading the tornado lens (NOAA SPC Online Tornado FAQ, opened and checked). */
  const SPC_FAQ = "https://www.spc.noaa.gov/faq/tornado/";
  const SEGMENT_NOTE = "NOAA's Storm Prediction Center explains that in these records a tornado is \"counted twice when " +
    "[it crosses] into another county, three times when [it enters] a third county,\" so \"you are not counting tornadoes, but " +
    "instead county-segments of tornado tracks.\" Long-track tornadoes, often the strong ones, are split the most.";
  /* When an era reaches back before the EF scale (2007): ratings and the weak/strong split. */
  function ratingNote(r) {
    if (Math.min(r.then.from, r.now.from) >= 2007) return "";
    return "On the original F scale, used before 2007, the Storm Prediction Center calls rating the damage \"largely a " +
      "judgment call--quite inconsistent and arbitrary.\" Its tornado FAQ says that comparing counts from before Doppler " +
      "radar means adjusting for unreported weak tornadoes or looking only at strong to violent (EF2–EF5) tornadoes, and " +
      "that \"when we do that, very little overall change has occurred since the 1950s.\" A change in the strong group " +
      "across these eras can come from rating practice as well as from storms.";
  }

  /* Damage-category notes for one era, from damage_values.json (distinct nonzero values per year). */
  function damageCategoryNotes(e, dv) {
    const out = [];
    if (e.from > 1995) return out;
    if (dv) {
      const yrs = [];
      for (let y = e.from; y <= Math.min(e.to, 1992); y++) if (dv[y] != null) yrs.push(dv[y]);
      if (yrs.length)
        out.push(`In ${e.from}–${Math.min(e.to, 1992)}, each year's damage figures take at most ${Math.max(...yrs)} distinct dollar values: ` +
          "they record a damage category (its midpoint), not an estimate of the actual loss.");
      const trans = [];
      for (let y = Math.max(e.from, 1993); y <= Math.min(e.to, 1996); y++) if (dv[y] != null) trans.push(`${dv[y]} in ${y}`);
      if (trans.length) out.push(`Distinct damage values per year then climb as estimates replace categories: ${trans.join(", ")}.`);
    } else if (e.from <= 1992) {
      out.push(`Damage figures for ${e.from}–${Math.min(e.to, 1992)} are category midpoints, not estimates.`);
    }
    return out;
  }

  /* The short notes a compact [[then-now]] figure carries: the breaks that apply to what it shows. */
  function compactNotes(r, metric, dv) {
    const notes = [];
    if (metric === "damage") for (const e of [r.then, r.now]) { const d = damageCategoryNotes(e, dv); if (d.length) notes.push(d[0]); }
    if (r.then.years !== r.now.years)
      notes.push(`The eras differ in length (${r.then.years} and ${r.now.years} years), so every figure is a per-year average.`);
    if (metric === "events") notes.push("Counts are recorded events, reports NOAA logged, not a census of storms.");
    if (Math.min(r.then.from, r.now.from) < 2007)
      notes.push("Tornado ratings before 2007 use the original F scale, which NOAA's Storm Prediction Center calls \"largely a judgment call.\"");
    return notes;
  }

  /* Query string for the Then & Now page. */
  function thenNowQuery(r, metric, dollars) {
    const q = new URLSearchParams({ then_from: r.then.from, then_to: r.then.to, now_from: r.now.from, now_to: r.now.to });
    if (r.state) q.set("state", r.state);
    if (metric && metric !== "events") q.set("metric", metric);
    if (metric === "damage" && dollars === "nominal") q.set("dollars", "nominal");
    return q.toString();
  }

  /* Re-draw on resize (charts are sized to their container). */
  const redraws = new Map();
  let rt;
  window.addEventListener("resize", () => {
    clearTimeout(rt);
    rt = setTimeout(() => redraws.forEach(fn => fn()), 150);
  });
  function keep(root, fn) { redraws.set(root, fn); fn(); }

  /* [[storm-chart ...]] shortcodes in posts become <figure class="storm-chart" data-...>. */
  async function renderShortcode(fig) {
    const d = fig.dataset;
    // An unknown metric or chart falls back to the default (the build warns the writer about it).
    const metric = FORMATS[d.metric] ? d.metric : "events";
    const chart = ["years", "types", "states", "months"].includes(d.chart) ? d.chart : "years";
    const filters = { state: d.state, event_type: d.eventType, year_from: d.yearFrom, year_to: d.yearTo };
    const types = (d.eventType || "").split(",").map(t => t.trim()).filter(Boolean).join(" + ");
    const scope = [types || "All storm events", d.state].filter(Boolean).join(" · ");
    fig.textContent = "";
    h("p", "chart-loading", "Loading chart…", fig);
    try {
      if (chart === "years") {
        const rows = await window.WWData.byYear(filters);
        keep(fig, () => line(fig, { title: d.title || `${LABELS[metric]} per year`, sub: d.sub || scope + " · NOAA Storm Events",
          data: rows.map(r => ({ x: r.year, y: r[metric] || 0 })), metric }));
      } else {
        const by = { types: "event_type", states: "state", months: "month" }[chart];
        const rows = await window.WWData.breakdown(by, metric, Number(d.limit) || 10, filters);
        const MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        keep(fig, () => bars(fig, { title: d.title || `${LABELS[metric]} by ${chart.slice(0, -1)}`,
          sub: d.sub || scope + " · NOAA Storm Events", metric, colName: by,
          data: rows.map(r => ({ label: by === "month" ? MONTHS[r.label] : String(r.label), value: r.value })) }));
      }
    } catch (e) {
      fig.textContent = "";
      h("p", "chart-loading", "Chart unavailable: the storm data couldn't be loaded.", fig);
    }
  }

  /* [[then-now ...]] shortcodes become <figure class="then-now" data-then data-now data-state data-metric>:
   * the comparison chart, the summary and tornado sentences, short notes on the breaks in the record
   * that apply (compactNotes), and a link to the full page. */
  async function renderThenNow(fig) {
    const d = fig.dataset;
    const metric = FORMATS[d.metric] ? d.metric : "events";
    const dollars = d.dollars === "nominal" ? "nominal" : "real";
    fig.textContent = "";
    h("p", "chart-loading", "Loading comparison…", fig);
    const dvP = window.WWData.damageValues().catch(() => null);
    try {
      const r = await window.WWData.thenNow(d.then || "1955-1974", d.now || "2005-2024",
        { state: d.state || "" }, { dollars });
      fig.textContent = "";
      const chart = h("div", "chart-panel tn-compact-chart", null, fig);
      compareChart(chart, r, metric);
      const cap = h("figcaption", "tn-compact-text", null, fig);
      h("p", null, summarySentence(r, metric), cap);
      const ts = tornadoSentence(r);
      if (ts) h("p", null, ts, cap);
      const notes = compactNotes(r, metric, await dvP);
      if (notes.length) {
        const np = h("p", "tn-compact-notes", "Notes: " + notes.join(" ") + " ", cap);
        if (Math.min(r.then.from, r.now.from) < 2007 || ts) {
          const src = h("a", null, "Source: NOAA SPC Tornado FAQ", np);
          src.href = SPC_FAQ;
        }
      }
      const a = h("a", "more", "Open in Then & Now →", cap);
      a.href = `${BASE()}/storms/then-and-now/?${thenNowQuery(r, metric, dollars)}`;
    } catch (e) {
      fig.textContent = "";
      h("p", "chart-loading", e instanceof RangeError ? `Comparison unavailable: ${e.message}`
        : "Comparison unavailable: the storm data couldn't be loaded.", fig);
    }
  }

  document.querySelectorAll("figure.storm-chart").forEach(renderShortcode);
  document.querySelectorAll("figure.then-now").forEach(renderThenNow);

  window.WWCharts = {
    line, bars, dumbbell, keep, FORMATS, LABELS,
    thenNow: { fmtAvg, pctChange, smallBase, perYearDiff, unmeasured, tollGap, relatedText, eraText, perYearWords, compareChart,
      summarySentence, tornadoSentence, ratingNote, damageCategoryNotes, compactNotes, thenNowQuery, SPC_FAQ, SEGMENT_NOTE },
  };
})();
