/* Then & Now (docs/THEN_AND_NOW.md): compares two eras of NOAA storm records fairly. Only event types
 * recorded in every year of both eras are compared; everything else is listed as not comparable, and
 * the caveats are generated from the data. State lives in the URL, like the Storm Desk. */
(function () {
  const C = window.WWCharts, T = C.thenNow, data = window.WWData;
  const $ = id => document.getElementById(id);
  const form = $("tn-controls");
  if (!form) return;
  const els = form.elements;
  const PRESETS = [
    ["1955-1974,2005-2024", "1955–1974 vs 2005–2024"],
    ["1975-1994,2005-2024", "1975–1994 vs 2005–2024"],
    ["1996-2005,2015-2024", "1996–2005 vs 2015–2024"],
  ];
  const METRICS = ["events", "deaths", "injuries", "damage"];
  const YEARS = ["then_from", "then_to", "now_from", "now_to"];
  const status = $("tn-status"), summary = $("tn-summary"), compare = $("tn-compare");
  const tornado = $("tn-tornado"), tornadoChart = $("tn-tornado-chart");
  const unmatched = $("tn-unmatched"), caveats = $("tn-caveats");
  const BUSY = [summary, compare, tornado, tornadoChart, unmatched, caveats].filter(Boolean);
  let seq = 0, lastKey = null;

  function h(tag, cls, text, parent) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    if (parent) parent.appendChild(n);
    return n;
  }

  const listText = a => (a.length < 3 ? a.join(" and ") : a.slice(0, -1).join(", ") + " and " + a[a.length - 1]);

  // ---- Controls ------------------------------------------------------------------------------
  const preset = els.preset;
  if (preset && !preset.options.length) {
    for (const [v, label] of PRESETS) preset.add(new Option(label, v));
    preset.add(new Option("Custom", ""));
  }
  function applyPreset(v) {
    const m = /^(\d{4})-(\d{4}),(\d{4})-(\d{4})$/.exec(v || "");
    if (!m) return false;
    YEARS.forEach((k, i) => { if (els[k]) els[k].value = m[i + 1]; });
    return true;
  }
  function syncPreset() {
    if (!preset) return;
    const v = `${els.then_from.value}-${els.then_to.value},${els.now_from.value}-${els.now_to.value}`;
    preset.value = [...preset.options].some(o => o.value === v) ? v : "";
  }
  function syncDollars() {
    const field = $("tn-dollars-field") || (els.dollars && els.dollars.closest("label"));
    if (field) field.hidden = els.metric.value !== "damage";
  }

  // Restore from the URL; fill gaps from the default preset. A state is matched to the menu ignoring
  // case; one that isn't in the records is dropped (with a note) rather than shown as a state with 0.
  const params = new URLSearchParams(location.search);
  let startNote = "";
  applyPreset(PRESETS[0][0]);
  for (const k of [...YEARS, "state", "metric", "dollars"]) {
    let v = params.get(k);
    const el = els[k];
    if (v == null || !el) continue;
    if (k === "state" && v && el.tagName === "SELECT") {
      const hit = [...el.options].find(o => o.value && o.value.toLowerCase() === v.trim().toLowerCase());
      if (!hit) { startNote = `No state named "${v}" in the records, so this shows all states.`; continue; }
      v = hit.value;
    }
    if (k === "metric" && !METRICS.includes(v)) continue;
    el.value = v;
  }
  if (!params.has("then_from") && params.get("preset")) applyPreset(params.get("preset"));
  syncPreset();
  syncDollars();

  function current() {
    const v = k => (els[k] ? String(els[k].value).trim() : "");
    return {
      then: [v("then_from"), v("then_to")], now: [v("now_from"), v("now_to")],
      state: v("state"), metric: METRICS.includes(v("metric")) ? v("metric") : "events",
      dollars: v("dollars") === "nominal" ? "nominal" : "real",
    };
  }

  function say(msg, kind) {
    if (!status) return;
    status.textContent = msg || "";
    status.dataset.kind = kind || "";
    status.hidden = !msg;
  }
  function busy(on) { BUSY.forEach(n => { n.classList.toggle("tn-busy", on); n.setAttribute("aria-busy", on); }); }
  /* Results that no longer match the controls (after an invalid edit) stay dimmed until fixed. */
  function stale(on) { BUSY.forEach(n => n.classList.toggle("tn-stale", on)); }
  /* Mark the year inputs of the era an error message names (or none) as invalid. */
  function markInvalid(msg) {
    const bad = !msg ? [] : /Then era/.test(msg) ? ["then_from", "then_to"] : /Now era/.test(msg) ? ["now_from", "now_to"] : YEARS;
    for (const k of YEARS) {
      if (!els[k]) continue;
      if (bad.includes(k)) { els[k].setAttribute("aria-invalid", "true"); els[k].setAttribute("aria-describedby", "tn-status"); }
      else { els[k].removeAttribute("aria-invalid"); els[k].removeAttribute("aria-describedby"); }
    }
  }
  /* A cited line: text followed by a superscript link to an entry in the page's Sources list. */
  function cite(parent, tag, cls, text, src) {
    const n = h(tag, cls, text, parent);
    const ref = src && document.getElementById(src);
    if (ref) {
      const num = [...ref.parentNode.children].indexOf(ref) + 1;
      const a = h("a", null, String(num), h("sup", "tn-cite", null, n));
      a.href = "#" + src;
    }
    return n;
  }

  // ---- Sections ------------------------------------------------------------------------------
  function renderSummary(r, q) {
    if (!summary) return;
    summary.textContent = "";
    h("p", "tn-lede", T.summarySentence(r, q.metric), summary);
    const notes = [];
    if (r.then.years !== r.now.years)
      notes.push(`The eras differ in length (${r.then.years} and ${r.now.years} years), so every figure is a per-year average.`);
    else notes.push(`Each era is ${r.then.years} year${r.then.years === 1 ? "" : "s"}; figures are per-year averages.`);
    const overlap = Math.max(r.then.from, r.now.from) <= Math.min(r.then.to, r.now.to);
    if (overlap) notes.push("The two eras overlap, so some years are counted in both.");
    if (r.only_now.length)
      notes.push(`${r.only_now.length} other event type${r.only_now.length === 1 ? " appears" : "s appear"} in ${T.eraText(r.now)} but ` +
        `${r.only_now.length === 1 ? "isn't" : "aren't"} compared, because NOAA didn't record ${r.only_now.length === 1 ? "it" : "them"} in every year of both eras.`);
    notes.push("Counts are recorded events: reports NOAA logged, not a census of storms. Tornadoes are recorded once per county their track crossed.");
    h("p", "tn-note", notes.join(" "), summary);
  }

  function renderTornado(r, q, years) {
    if (tornado) {
      tornado.textContent = "";
      h("p", null, T.tornadoSentence(r), tornado);
      const rn = T.ratingNote(r);
      if (rn) cite(tornado, "p", "tn-note", rn, "tn-src-faq");
    }
    if (!tornadoChart || !years) return;
    const lo = Math.min(r.then.from, r.now.from), hi = Math.max(r.then.to, r.now.to);
    const rows = years.filter(y => y.year >= lo && y.year <= hi);
    // Slots 3 and 7 (aqua, violet): blue and orange mean Then and Now everywhere on this page.
    const series = [
      { name: "Weak (F/EF0–1)", cls: "s3", data: rows.map(y => ({ x: y.year, y: y.weak })) },
      { name: "Strong (F/EF2–5)", cls: "s7", data: rows.map(y => ({ x: y.year, y: y.strong })) },
    ];
    C.keep(tornadoChart, () => C.line(tornadoChart, {
      title: "Recorded tornado segments per year by rating",
      sub: `${q.state || "All states"} · one per county crossed · eras shaded · unrated not shown · NOAA Storm Events`,
      series, metric: "events", unit: "tornado segments",
      bands: [{ from: r.then.from, to: r.then.to, label: "Then" }, { from: r.now.from, to: r.now.to, label: "Now" }],
    }));
  }

  function renderUnmatched(r) {
    if (!unmatched) return;
    unmatched.textContent = "";
    const all = [...r.only_now, ...r.only_then];
    if (!all.length) {
      h("p", null, `Every event type recorded in ${T.eraText(r.then)} or ${T.eraText(r.now)} was recorded in every year of both, so nothing is left out.`, unmatched);
      return;
    }
    h("p", "tn-note", `${all.length} event type${all.length === 1 ? " is" : "s are"} in the records for one era or the other but not in every year of both, so ${all.length === 1 ? "it isn't" : "they aren't"} compared.`, unmatched);
    const ul = h("ul", "tn-unmatched-list", null, unmatched);
    for (const t of all) {
      const li = h("li", null, null, ul);
      h("span", "tn-type", t.type, li);
      const when = t.since != null
        ? `recorded every year since ${t.since}`
        : t.last < r.now.from ? `last recorded in ${t.last}`
        : `recorded in some years from ${t.first} to ${t.last}, not every year`;
      h("span", "tn-when", when, li);
    }
  }

  async function renderCaveats(r, metric) {
    if (!caveats) return;
    let dv = null, cpi = null;
    try { [dv, cpi] = await Promise.all([data.damageValues(), data.cpi()]); } catch (e) { /* caveats still render */ }
    const list = $("tn-caveats-list") || caveats.querySelector("ul.tn-caveats") ||
      h("ul", "tn-caveats", null, caveats);
    list.textContent = "";
    const add = text => h("li", null, text, list);
    const eras = [["then", r.then], ["now", r.now]];

    // Damage categories, measured from the distinct dollar values recorded each year.
    for (const [, e] of eras) T.damageCategoryNotes(e, dv).forEach(add);
    // Which event types each era includes.
    const n = r.comparable.length;
    add(`The records include ${r.types_recorded.then} event type${r.types_recorded.then === 1 ? "" : "s"} in ${T.eraText(r.then)} and ` +
      `${r.types_recorded.now} in ${T.eraText(r.now)}; ${n} ${n === 1 ? "was" : "were"} recorded in every year of both, and only ` +
      `${n === 1 ? "that one is" : "those are"} compared.`);
    // Tolls not recorded through the whole of an era for a compared type (Hail and Thunderstorm Wind
    // carry no deaths, injuries or damage until 1983–1993), measured from the national record: a toll
    // counts for an era only if the records hold it from the era's first year.
    const TOLLS = ["deaths", "injuries", "damage"];
    const none = [], partly = [];
    for (const c of r.comparable) {
      if (!c.recorded) continue;
      for (const k of TOLLS) for (const [key, e] of eras) {
        if (c.recorded[key][k]) continue;
        const first = c.first_recorded[k];
        if (first && first > e.from && first <= e.to) partly.push(`${c.type} ${k} (from ${first}, in ${T.eraText(e)})`);
        else none.push(`${c.type} ${k} (in ${T.eraText(e)}${first ? `; first recorded ${first}` : ""})`);
      }
    }
    const uniq = a => [...new Set(a)];
    if (partly.length)
      add(`Some tolls first appear in the records part-way through an era: ${listText(uniq(partly))}. Averaging them over ` +
        `the whole era would count years that hold nothing, so they show as "recorded from", not as a number, and aren't compared.`);
    if (none.length)
      add(`The records hold none of these at all: ${listText(uniq(none))}. They show as "not recorded", not as zero, and aren't compared.`);
    // Related types recorded separately (Heat vs Excessive Heat): computed for the chosen measure.
    for (const c of r.comparable) T.relatedText(c, metric, r).forEach(add);
    if (r.comparable.some(c => c.related && c.related.length))
      add("NOAA has split or renamed some event types since 1996, so a type recorded every year can still hold less " +
        "of a kind of weather in one era than in the other.");
    // F vs EF: the records switch during 2007 (checked against the database: F ratings run through
    // early 2007, EF ratings from 2007 on). The tornado file merges them by number.
    const usesF = e => e.from <= 2007, usesEF = e => e.to >= 2007;
    if (eras.some(([, e]) => usesF(e)) && eras.some(([, e]) => usesEF(e)))
      add("Tornado ratings switch from the Fujita (F) scale to the Enhanced Fujita (EF) scale during 2007. " +
        "This page groups them by number, so F2 and EF2 count as the same rating.");
    const t = r.tornado;
    if (t && (t.then.unknown || t.now.unknown))
      add(`Some recorded tornado segments have no rating (${T.fmtAvg("events", t.then.unknown)} a year in ${T.eraText(r.then)}, ` +
        `${T.fmtAvg("events", t.now.unknown)} in ${T.eraText(r.now)}); they're left out of the weak/strong split.`);
    cite(list, "li", null, T.SEGMENT_NOTE, "tn-src-faq");
    if (cpi)
      add(`Real dollars are ${cpi.base_year} dollars, adjusted year by year with the annual average of the CPI-U ` +
        `(series ${cpi.series}${cpi.source ? ", " + cpi.source : ""}).`);
    // Static caveats: statements about what these numbers are, not claims about the world.
    add("Every count is a recorded event: something someone observed and reported, and NOAA logged. " +
      "A change in recorded events can come from a change in reporting as well as a change in storms.");
    add("Deaths and injuries are counted under the event they were recorded with, so how each one was attributed shapes these totals.");
    add("Nothing here is adjusted for population or for how much stands in a storm's path.");
  }

  // ---- Refresh -------------------------------------------------------------------------------
  async function refresh() {
    syncDollars();
    const q = current();
    const key = JSON.stringify(q);
    if (key === lastKey) return;
    lastKey = key;
    const url = new URLSearchParams({ then_from: q.then[0], then_to: q.then[1], now_from: q.now[0], now_to: q.now[1] });
    if (q.state) url.set("state", q.state);
    if (q.metric !== "events") url.set("metric", q.metric);
    if (q.metric === "damage" && q.dollars === "nominal") url.set("dollars", "nominal");

    const my = ++seq;
    busy(true);
    say("Loading…", "loading");
    let r, years;
    try {
      [r, years] = await Promise.all([
        data.thenNow(q.then, q.now, { state: q.state }, { dollars: q.dollars }),
        data.tornadoByYear({ state: q.state }).catch(() => null),
      ]);
    } catch (e) {
      if (my !== seq) return;
      busy(false);
      lastKey = null;
      const msg = e instanceof RangeError ? e.message : "Couldn't load the storm data. Try again in a moment.";
      say(msg, "error");
      markInvalid(e instanceof RangeError ? msg : "");
      // Whatever is on screen no longer matches the controls: dim it, and never leave "Loading…" up.
      stale(true);
      const loading = compare && compare.querySelector(".chart-loading");
      if (loading && !compare.querySelector("svg, table")) loading.textContent = "No comparison to show until the years above are fixed.";
      return;
    }
    if (my !== seq) return;
    // Only a comparison that loaded goes in the address bar, so a shared link never holds bad eras.
    history.replaceState(null, "", `?${url}`);
    markInvalid("");
    stale(false);
    say(startNote);
    startNote = "";
    renderSummary(r, q);
    if (compare) { compare.classList.add("chart-panel"); T.compareChart(compare, r, q.metric); }
    renderTornado(r, q, years);
    renderUnmatched(r);
    await renderCaveats(r, q.metric);
    if (my === seq) busy(false);
  }

  let timer;
  form.addEventListener("input", e => {
    if (e.target === preset) { applyPreset(preset.value); }
    else if (YEARS.includes(e.target.name)) syncPreset();
    clearTimeout(timer);
    timer = setTimeout(refresh, e.target.type === "number" ? 500 : 0);
  });
  form.addEventListener("change", e => { if (e.target === preset) applyPreset(preset.value); });
  form.addEventListener("submit", e => { e.preventDefault(); refresh(); });
  refresh();
})();
