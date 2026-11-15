// Price Check (/prices/): search a procedure, see an estimate. The method is docs/PRICE_CHECK.md.
//
// The data file (prices/data.json, written by scripts/build_site.py from data_sources/procedure-prices.json)
// holds only published Medicare figures; every estimate is computed here, in WWPrices.estimate():
//   each part of the bill = Medicare's amount x what private insurers pay relative to Medicare
// with a low, typical and high multiplier per kind of fee (data.multipliers, each one cited on the page).
(function () {
  "use strict";

  const PLACES = {
    office: { label: "Office or clinic", where: "in an office or clinic" },
    center: { label: "Surgery center", where: "at a surgery center" },
    hospital: { label: "Hospital outpatient", where: "at a hospital outpatient department" },
  };
  const SCAN_OFFICE = { label: "Imaging center or office", where: "at an imaging center or doctor's office" };
  const MIN_SHARE = 0.1;      // a setting is offered when at least this share of Medicare's cases happen there
  const THIN = 5000;          // fewer Medicare services than this a year: say the figures rest on little data

  const share = (p) => {
    const o = p.doctor.office ? p.doctor.office[0] : 0, f = p.doctor.facility ? p.doctor.facility[0] : 0;
    return o + f ? o / (o + f) : 0;
  };

  // Medicare pays a hospital outpatient department more than a surgery center for the same procedure.
  // Where CMS doesn't publish a hospital figure for a code, the hospital fee is estimated from the
  // center rate using the median of that ratio across the procedures that have both.
  function hospitalRatio(data) {
    const r = data.procedures.filter((p) => p.hospital && p.center).map((p) => p.hospital[1] / p.center).sort((a, b) => a - b);
    if (!r.length) return null;
    const m = r.length >> 1;
    return r.length % 2 ? r[m] : (r[m - 1] + r[m]) / 2;
  }

  // A scan or test the fee schedule splits into the machine's part and the doctor's reading (p.schedule):
  // outside a hospital it is priced from the schedule's price for both together, because Medicare's
  // office average mixes whole scans with bills for one part only. In a hospital it is the doctor's
  // reading plus the hospital's part, when the schedule carries the hospital's rate and CMS publishes
  // no hospital or surgery center figure of its own for the code.
  const scanHospital = (p) => Boolean(p.schedule && p.schedule.hospital && !p.hospital && !p.center && p.doctor.facility);

  const isScan = (p) => p.specialty === "Scans and tests" || Boolean(p.schedule && p.schedule.hospital);

  /** The settings a procedure is priced in, most likely first. */
  function settings(p) {
    const office = p.doctor.office, facility = p.doctor.facility, s = share(p), out = [];
    if (scanHospital(p)) return s < 0.5 ? ["hospital", "office"] : ["office", "hospital"];
    // An office figure far below the facility one isn't the price of doing the procedure in an office
    // (Medicare always pays the doctor at least as much there); it comes from partial bills, so skip it.
    const officeOk = office && s >= MIN_SHARE && (!facility || office[1] >= 0.6 * facility[1]);
    const facilityOk = facility && 1 - s >= MIN_SHARE;
    if (officeOk) out.push("office");
    if (facilityOk && p.center) out.push("center");
    if (facilityOk && (p.hospital || p.center)) out.push("hospital");
    if (!out.length) {                       // nothing passed the tests: take whatever can be priced at all
      if (facility && p.center) out.push("center");
      if (facility && (p.hospital || p.center)) out.push("hospital");
      if (!out.length && office) out.push("office");
    }
    if (out[0] === "office" && s < 0.5 && out.length > 1) out.push(out.shift());   // mostly done in facilities
    return out;
  }

  function part(key, label, medicare, mult, extra) {
    return Object.assign({ key, label, medicare, low: medicare * mult.low, mid: medicare * mult.mid, high: medicare * mult.high }, extra);
  }

  /** The estimate for one procedure. opts: {state, setting, anesthesia}. */
  function estimate(data, p, opts) {
    opts = opts || {};
    const available = settings(p);
    const setting = available.includes(opts.setting) ? opts.setting : available[0];
    const place = setting === "office" ? "office" : "facility";
    const m = data.multipliers, parts = [], flags = {};
    const local = opts.state && p.states[opts.state] && p.states[opts.state][place];
    const fee = local || p.doctor[place];
    const whole = setting === "office" && p.schedule;      // the scan and its reading, at the schedule's national price
    flags.state = local && !whole ? opts.state : null;
    flags.stateMissing = Boolean(opts.state && !local && !whole);
    flags.national = Boolean(opts.state && whole);
    if (whole) parts.push(part("doctor", isScan(p) ? "Scan and reading" : "Test and reading", p.schedule.global, m.doctor, { scheduled: true, thing: isScan(p) ? "scan" : "test" }));
    else parts.push(part("doctor", scanHospital(p) ? "Doctor's reading" : p.billed_by ? "Clinician's fee" : "Doctor's fee", fee[1], m.doctor, { billed: fee[2], services: fee[0], place, state: flags.state }));
    if (setting === "center") parts.push(part("center", "Surgery center fee", p.center, m.center, {}));
    if (setting === "hospital") {
      if (p.hospital) parts.push(part("hospital", "Hospital fee", p.hospital[1], m.hospital, { billed: p.hospital[2], services: p.hospital[0] }));
      else if (scanHospital(p)) parts.push(part("hospital", "Hospital fee", p.schedule.hospital, m.hospital, { scheduled: true }));
      else {
        flags.hospitalEstimated = true;
        const ratio = hospitalRatio(data);
        parts.push(part("hospital", "Hospital fee", p.center * ratio, m.hospital, { estimated: true, from: p.center, ratio }));
      }
    }
    flags.anesthesiaAvailable = Boolean(p.anesthesia && setting !== "office");
    if (flags.anesthesiaAvailable && opts.anesthesia !== false) {
      parts.push(part("anesthesia", "Anesthesia", p.anesthesia.fee[1], m.anesthesia, { billed: p.anesthesia.fee[2], services: p.anesthesia.fee[0] }));
    }
    const total = { medicare: 0, low: 0, mid: 0, high: 0 };
    for (const x of parts) for (const k in total) total[k] += x[k];
    const all = (p.doctor.office ? p.doctor.office[0] : 0) + (p.doctor.facility ? p.doctor.facility[0] : 0);
    flags.thin = all < THIN;
    return { setting, available, parts, total, flags };
  }

  /** Round to a figure that doesn't claim more precision than an estimate has. */
  function round(v) {
    const step = v < 20 ? 1 : v < 100 ? 5 : v < 1000 ? 10 : v < 10000 ? 50 : 100;
    return Math.max(step, Math.round(v / step) * step);
  }
  const usd = (v) => "$" + round(v).toLocaleString("en-US");
  const exact = (v) => "$" + Math.round(v).toLocaleString("en-US");
  const range = (t) => (round(t.low) === round(t.high) ? usd(t.mid) : `${usd(t.low)} – ${usd(t.high)}`);
  const percent = (m) => Math.round(m * 100) + "%";

  const fold = (s) => s.toLowerCase().normalize("NFD").replace(/[^a-z0-9 ]+/g, " ").replace(/\s+/g, " ").trim();

  const stem = (w) => (w.length > 4 && w.endsWith("s") ? w.slice(0, -1) : w);   // "cataracts" finds "cataract"
  const words = (query) => fold(query).split(" ").filter(Boolean).map(stem);
  // A search word matches a text when one of the text's words starts with it ("derm" finds "dermatologist",
  // but "ent" doesn't find "treatment", nor "urologist" "neurologist"). One or two letters must be the
  // whole word ("PT" is not "ptosis"). A procedure's name also matches inside a word, for words long
  // enough to mean something ("scopy" finds "colonoscopy").
  const starts = (text, w) => text.split(" ").some((t) => (w.length < 3 ? t === w : t.startsWith(w)));
  const inside = (text, w) => w.length >= 4 && text.includes(w);

  const doctorWords = (s) => fold(`${s.name} ${s.doctor} ${s.doctors} ${(s.aka || []).join(" ")}`);

  /** The kind of doctor a search names ("dermatologist", "skin doctor", "ENT"): its entry in
      data.specialties, or null. Every word of the search must be one of that entry's words. */
  function specialtyFor(data, query) {
    const ws = words(query);
    if (!ws.length) return null;
    return (data.specialties || []).find((s) => { const text = doctorWords(s); return ws.every((w) => starts(text, w)); }) || null;
  }

  /** Procedures matching a search, best first. Every word must appear somewhere in the entry: its name,
      its other names, the kind of doctor who does it, or its description. */
  function search(data, query) {
    const ws = words(query);
    if (!ws.length) return data.procedures.slice();
    const doctors = {};
    for (const s of data.specialties || []) doctors[s.name] = doctorWords(s);
    const scored = [];
    for (const p of data.procedures) {
      const name = fold(p.name), aka = fold((p.aka || []).join(" ")),
        doctor = [p.specialty].concat(p.also || []).map((s) => doctors[s] || fold(s)).join(" "),
        rest = fold(`${p.code} ${p.about} ${p.medicare_description}`);
      let score = 0, ok = true;
      for (const w of ws) {
        if (starts(name, w)) score += 4;
        else if (inside(name, w)) score += 3;
        else if (starts(aka, w)) score += 2;
        else if (starts(doctor, w)) score += 1.5;
        else if (starts(rest, w)) score += 1;
        else { ok = false; break; }
      }
      if (ok) scored.push([score, p]);
    }
    return scored.sort((a, b) => b[0] - a[0]).map((x) => x[1]);
  }

  const api = { settings, estimate, search, specialtyFor, round, hospitalRatio };
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  window.WWPrices = api;

  // ---------------------------------------------------------------- the page

  const root = document.getElementById("pc");
  if (!root) return;
  const $ = (id) => document.getElementById(id);
  const form = $("pc-form"), q = $("pc-q"), stateSel = $("pc-state"), detail = $("pc-detail"), count = $("pc-count");
  let data = null, byId = {}, current = null, setting = null, anesthesia = true;
  const TITLE = document.title;
  const SOURCE_NUMBER = { doctor: 1, center: 2, hospital: 3, kff: 4, rand: 5, anesthesia: 6, gfe: 7, schedule: 8 };   // the Sources list in prices.html

  function el(tag, attrs, ...kids) {
    const node = document.createElement(tag);
    for (const k in attrs || {}) {
      if (attrs[k] == null || attrs[k] === false) continue;
      if (k === "class") node.className = attrs[k];
      else if (k === "text") node.textContent = attrs[k];
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), attrs[k]);
      else node.setAttribute(k, attrs[k] === true ? "" : attrs[k]);
    }
    for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) node.append(kid);
    return node;
  }

  const placeText = (p, key) => (key === "office" && (p.specialty === "Scans and tests" || (p.schedule && p.schedule.hospital)) ? SCAN_OFFICE : PLACES[key]);

  function readUrl() {
    const u = new URLSearchParams(location.search);
    const state = u.get("state");
    stateSel.value = data.states.includes(state) ? state : "";
    setting = u.get("where");
    anesthesia = u.get("anesthesia") !== "no";
    current = byId[u.get("p")] || null;
    q.value = u.get("q") || "";
  }

  function writeUrl(push) {
    const u = new URLSearchParams();
    if (current) u.set("p", current.id);
    else if (q.value.trim()) u.set("q", q.value.trim());
    if (stateSel.value) u.set("state", stateSel.value);
    if (current && setting && setting !== settings(current)[0]) u.set("where", setting);
    if (!anesthesia) u.set("anesthesia", "no");
    const url = location.pathname + (u.toString() ? "?" + u : "");
    history[push ? "pushState" : "replaceState"](null, "", url);
  }

  function listPrices() {
    for (const span of root.querySelectorAll("[data-item]")) {
      const p = byId[span.dataset.item];
      const price = span.querySelector("[data-price]");
      if (!p || !price) continue;
      const t = estimate(data, p, { state: stateSel.value }).total;
      price.replaceChildren(el("span", { class: "pc-item-guess", text: "about " + usd(t.mid) }), el("span", { class: "pc-item-range", text: range(t) }));
    }
  }

  function filter() {
    const found = new Set(search(data, q.value).map((p) => p.id));
    for (const li of root.querySelectorAll("[data-item]")) li.hidden = !found.has(li.dataset.item);
    for (const g of root.querySelectorAll("[data-group]")) g.hidden = !g.querySelector("[data-item]:not([hidden])");
    $("pc-none").hidden = found.size > 0;
    const n = found.size;
    count.textContent = q.value.trim() ? `${n} ${n === 1 ? "match" : "matches"} for “${q.value.trim()}”` : `${n} procedures`;
    for (const a of root.querySelectorAll("a[data-q]")) {
      if (fold(a.dataset.q) === fold(q.value)) a.setAttribute("aria-current", "true"); else a.removeAttribute("aria-current");
    }
  }

  function mark() {
    for (const a of root.querySelectorAll("a[data-id]")) {
      if (current && a.dataset.id === current.id) a.setAttribute("aria-current", "true");
      else a.removeAttribute("aria-current");
    }
  }

  // The range drawn to scale: Medicare's payment, the likely range, the best guess.
  function rangeFigure(t) {
    const max = t.high * 1.08, pct = (v) => (100 * v / max).toFixed(2) + "%";
    const summary = `Scale from $0 to ${usd(max)}. Medicare's price is ${usd(t.medicare)}. Likely range ${usd(t.low)} to ${usd(t.high)}. Best guess ${usd(t.mid)}.`;
    return el("figure", { class: "pc-range" },
      el("div", { class: "pc-track", role: "img", "aria-label": summary },
        el("span", { class: "pc-band", style: `left:${pct(t.low)};width:${pct(t.high - t.low)}` }),
        el("span", { class: "pc-medicare", style: `left:${pct(t.medicare)}` }),
        el("span", { class: "pc-guess", style: `left:${pct(t.mid)}` })),
      el("div", { class: "pc-axis", "aria-hidden": "true" }, el("span", { text: "$0" }), el("span", { text: usd(max) })),
      el("figcaption", { class: "pc-legend" },
        el("span", {}, el("i", { class: "pc-key pc-key-medicare" }), `Medicare's price ${usd(t.medicare)}`),
        el("span", {}, el("i", { class: "pc-key pc-key-band" }), `Likely range ${usd(t.low)} – ${usd(t.high)}`),
        el("span", {}, el("i", { class: "pc-key pc-key-guess" }), `Best guess ${usd(t.mid)}`)));
  }

  function breakdown(e) {
    const head = ["Part of the bill", "Medicare's price", "Best guess", "Likely range", "List price"];
    const row = (cells, tag) => el("tr", {}, cells.map((c, i) => el(i ? tag : "th", { class: i ? "num" : null, scope: i ? null : "row", text: c })));
    const assumed = e.parts.some((x) => x.key === "center");   // the surgery center's range is our assumption: say so in the table
    const body = e.parts.map((x) => row([x.label + (x.estimated ? " (estimated)" : ""), exact(x.medicare), usd(x.mid),
      (x.low === x.high ? usd(x.mid) : `${usd(x.low)} – ${usd(x.high)}`) + (x.key === "center" ? " *" : ""), x.billed ? exact(x.billed) : "not published"], "td"));
    const t = e.total;
    return el("div", { class: "pc-table-wrap" },
      el("table", { class: "chart-table pc-table" },
        el("caption", { class: "pc-caption", text: "What makes up the estimate" }),
        el("thead", {}, el("tr", {}, head.map((h, i) => el("th", { class: i ? "num" : null, scope: "col", text: h })))),
        el("tbody", {}, body),
        e.parts.length > 1 && el("tfoot", {}, row(["Total", exact(t.medicare), usd(t.mid), `${usd(t.low)} – ${usd(t.high)}`, ""], "td"))),
      assumed && el("p", { class: "pc-fineprint", text: "* The surgery center's range is our own assumption, not a published figure. “How we got this number” below explains it." }));
  }

  function notes(p, e) {
    const out = [], f = e.flags, state = stateSel.value;
    if (p.note) out.push(p.note_source ? [p.note + " (", el("a", { href: p.note_source.url, rel: "noopener", text: p.note_source.label }), ")"] : p.note);
    if (f.state) out.push(`The doctor's fee is ${state}'s own average. ${e.parts.length > 1 ? "Facility and anesthesia fees are national figures; Medicare adjusts them somewhat for local wages." : ""}`.trim());
    if (f.national) out.push(`This is Medicare's national price. Medicare adjusts it somewhat for local costs, and we don't have a ${state} figure for the whole ${e.parts[0].thing}.`);
    if (p.retired) out.push(p.retired.note);
    if (f.stateMissing) out.push(`Medicare paid for too few of these in ${state} to publish a reliable figure there, so this is the national average.`);
    if (f.thin) out.push("Medicare covers this procedure relatively rarely, so its averages rest on fewer cases than most on this page. Treat the estimate as rougher than usual.");
    if (f.anesthesiaAvailable) out.push("Anesthesia is billed by time, and the figure here is Medicare's average bill for this kind of case. When an anesthesiologist supervises a nurse anesthetist, each can send a bill, so the anesthesia total can be higher. With only local numbing there is no anesthesia bill.");
    out.push("“List price” is the average the providers billed Medicare. Almost no one pays it, but an uninsured patient who doesn't ask for a discount can be billed it.");
    return out;
  }

  const cite = (...keys) => keys.map((k) => el("sup", { class: "tn-cite" }, el("a", { href: `#pc-src-${k}`, text: String(SOURCE_NUMBER[k]) })));

  // How each part of the bill was worked out, with the numbers and where each one comes from.
  function working(p, e) {
    const m = data.multipliers, s = data.sources;
    const times = (x, mult) => `${exact(x.medicare)} × ${mult.mid.toFixed(2)} ≈ ${usd(x.mid)}.`;
    const span = (mult) => (mult.low === mult.mid ? `up to ${percent(mult.high)}` : `${percent(mult.low)} to ${percent(mult.high)}`);
    return e.parts.map((x) => {
      if (x.key === "doctor" && x.scheduled) {
        return el("li", {}, el("strong", { text: `${x.label}. ` }),
          `Medicare's national price for the ${x.thing} and the doctor's reading together, done outside a hospital, is ${exact(x.medicare)} (${s.schedule.year} fee schedule).`, cite("schedule"),
          ` We use that instead of Medicare's average bill, because many of those bills are for the ${x.thing} alone or the reading alone.`,
          ` Studies find private insurers pay about ${percent(m.doctor.mid)} of Medicare's price for services on this fee schedule (${span(m.doctor)} across studies).`, cite("kff"), ` ${times(x, m.doctor)}`);
      }
      if (x.key === "hospital" && x.scheduled) {
        return el("li", {}, el("strong", { text: "Hospital fee. " }),
          `Medicare's national price for a hospital outpatient department's part of this scan (the machine and staff) is ${exact(x.medicare)} (${s.schedule.year}).`, cite("schedule"),
          ` Private insurers pay hospitals about ${percent(m.hospital.mid)} of Medicare's price for outpatient care`, cite("rand"),
          `; an earlier review of studies found a range of ${percent(m.hospital.low)} to ${percent(m.hospital.high)}.`, cite("kff"), ` ${times(x, m.hospital)}`);
      }
      if (x.key === "doctor") {
        return el("li", {}, el("strong", { text: `${x.label}. ` }),
          `Medicare's price for the ${p.billed_by ? "clinician" : "doctor"} averaged ${exact(x.medicare)} ${x.place === "office" ? "in an office" : "in a facility"}, across ${x.services.toLocaleString("en-US")} cases ${x.state ? "in " + x.state : "nationwide"} in ${s.doctor.year}.`, cite("doctor"),
          ` Studies find private insurers pay doctors about ${percent(m.doctor.mid)} of Medicare's price (${span(m.doctor)} across studies).`, cite("kff"), ` ${times(x, m.doctor)}`,
          p.billed_by ? ` That figure was measured for physicians' services. We have no separate figure for ${p.billed_by}, so treat this estimate as rougher than most.` : "");
      }
      if (x.key === "center") {
        return el("li", {}, el("strong", { text: "Surgery center fee. " }),
          `Medicare's national price for the surgery center is ${exact(x.medicare)} (${s.center.period}).`, cite("center"),
          ` Private insurers pay surgery centers about ${percent(m.center.mid)} of Medicare's price.`, cite("rand"),
          ` ${times(x, m.center)}`,
          el("span", { class: "pc-assumed" }, ` The range for this part is our own assumption, not a published figure. No study gives a national range for surgery centers, so we set one: the low end is Medicare's own price (${percent(m.center.low)}; ${exact(x.medicare)}), because in some states surgery centers average no more than that, and the high end is what hospitals average (${percent(m.center.high)}; ${usd(x.high)}), because surgery centers are paid well below hospitals on average for the same services.`), cite("rand"));
      }
      if (x.key === "hospital") {
        const start = x.estimated
          ? [`Medicare doesn't publish a hospital figure for this procedure, so we estimate one from the surgery center price: ${exact(x.from)} × ${x.ratio.toFixed(2)} (how much more Medicare typically pays a hospital than a surgery center, among the procedures here that have both) ≈ ${exact(x.medicare)}.`, cite("center", "hospital")]
          : [`Medicare's price for the hospital outpatient department averaged ${exact(x.medicare)} across ${x.services.toLocaleString("en-US")} cases in ${s.hospital.year}.`, cite("hospital")];
        return el("li", {}, el("strong", { text: "Hospital fee. " }), start,
          ` Private insurers pay hospitals about ${percent(m.hospital.mid)} of Medicare's price for outpatient care`, cite("rand"),
          `; an earlier review of studies found a range of ${percent(m.hospital.low)} to ${percent(m.hospital.high)}.`, cite("kff"), ` ${times(x, m.hospital)}`);
      }
      return el("li", {}, el("strong", { text: "Anesthesia. " }),
        `Medicare's price for anesthesia (code ${p.anesthesia.code}) averaged ${exact(x.medicare)} per bill, across ${x.services.toLocaleString("en-US")} bills in ${s.doctor.year}.`, cite("doctor"),
        ` Private insurers' rates for anesthesia are about ${percent(m.anesthesia.mid)} of Medicare's (${span(m.anesthesia)} in a newer survey).`, cite("anesthesia"), ` ${times(x, m.anesthesia)}`);
    });
  }

  // What to say on the phone, with this procedure's code and numbers filled in.
  function callScript(p, e) {
    const t = e.total, place = placeText(p, e.setting), parts = e.parts.length > 1, whole = e.parts[0].scheduled;
    const cheaper = e.available.some((key) => estimate(data, p, { state: stateSel.value, setting: key, anesthesia }).total.mid < t.mid);
    return el("aside", { class: "pc-call" },
      el("h3", { text: "When you call" }),
      el("p", { class: "pc-say", text: `“What is your self-pay price for ${p.retired ? p.retired.ask + ", and which billing code will you use" : "billing code " + p.code}?${parts ? (e.flags.anesthesiaAvailable ? " Does that include the facility and anesthesia, or only the doctor's fee?" : " Does that include the facility's fee, or only the doctor's?") : whole ? " Does that include the doctor's reading?" : " Does that cover everything done at that visit?"}”` }),
      el("p", {}, `Our best guess for the total ${place.where} is ${usd(t.mid)}, and the likely range is ${range(t)}. If the answer is well above that, ask why`,
        cheaper ? ", and whether it can be done somewhere less expensive. " : ". ",
        "If you are uninsured or not using insurance, you can ask for the price in writing: it is called a Good Faith Estimate.", cite("gfe")));
  }

  // The price menu: every procedure a search found, with its best guess and range.
  function menu(found) {
    const text = q.value.trim(), state = stateSel.value, who = specialtyFor(data, text), m = data.multipliers, s = data.sources;
    const whole = who && found.every((p) => p.specialty === who.name || (p.also || []).includes(who.name));
    const title = whole ? `What ${who.doctors} commonly do, and what it costs` : `${found.length} ${found.length === 1 ? "procedure" : "procedures"} matching “${text}”`;
    const rows = found.map((p) => {
      const e = estimate(data, p, { state }), t = e.total;
      return el("tr", {},
        el("th", { scope: "row" }, el("a", { href: `?p=${p.id}`, "data-id": p.id, text: p.name })),
        el("td", { text: placeText(p, e.setting).label }),
        el("td", { class: "num pc-menu-guess", text: usd(t.mid) }),
        el("td", { class: "num", text: range(t) }),
        el("td", { class: "num", text: exact(t.medicare) }));
    });
    document.title = `${whole ? who.doctor + " prices" : "“" + text + "”"} — Price Check`;
    return el("article", { class: "pc-card pc-menu" },
      el("header", { class: "pc-card-head" },
        el("p", { class: "kicker", text: whole ? who.name : "Price menu" }),
        el("h2", { id: "pc-name", text: title }),
        el("p", { class: "pc-about", text: `Best guesses for the total price with private insurance or paying yourself, ${state ? "in " + state : "U.S. average"}, where each is most often done. Pick one for the full working, other places it can be done, and what to say when you call.` })),
      el("div", { class: "pc-table-wrap" },
        el("table", { class: "chart-table pc-table" },
          el("thead", {}, el("tr", {}, ["Procedure", "Usually done", "Best guess", "Likely range", "Medicare's price"].map((h, i) => el("th", { class: i > 1 ? "num" : null, scope: "col", text: h })))),
          el("tbody", {}, rows))),
      el("div", { class: "pc-notes" }, el("h3", { text: "Where these numbers come from" }),
        el("p", {}, `Each one starts from what Medicare actually paid for the procedure in ${s.doctor.year}: the doctor's fee, plus the surgery center's or hospital's fee where there is one.`, cite("doctor", "center", "hospital"),
          ` Private insurers pay more than Medicare, and studies have measured how much more: about ${percent(m.doctor.mid)} of Medicare's price for doctors`, cite("kff"),
          `, ${percent(m.center.mid)} for surgery centers and ${percent(m.hospital.mid)} for hospital outpatient departments.`, cite("rand"),
          " We multiply each part of the bill by its figure and add the parts up. The range for doctors and hospitals runs from the lowest to the highest figure the studies found. For surgery centers no study gives a range, so that one is our own assumption: from Medicare's price up to what hospitals average. Real prices vary by city, insurer and doctor.")));
  }

  function render(focus) {
    mark();
    if (!current) {
      for (const n of detail.querySelectorAll(".pc-card")) n.remove();
      const found = q.value.trim() ? search(data, q.value) : [];
      $("pc-empty").hidden = found.length > 0;
      if (found.length) detail.append(menu(found));
      else document.title = TITLE;
      if (focus) show();
      return;
    }
    const p = current, state = stateSel.value;
    const e = estimate(data, p, { state, setting, anesthesia });
    setting = e.setting;
    const t = e.total, place = placeText(p, e.setting);
    const scope = `${state && !e.flags.national ? state : "U.S. average"}, ${place.where}`;

    const tabs = e.available.length > 1 && el("div", { class: "pc-where" },
      el("p", { class: "pc-label", id: "pc-where-label", text: "Where it's done" }),
      el("div", { class: "pc-seg", role: "group", "aria-labelledby": "pc-where-label" }, e.available.map((key) => {
        const other = estimate(data, p, { state, setting: key, anesthesia });
        return el("button", { type: "button", "aria-pressed": String(key === e.setting), onclick: () => { setting = key; writeUrl(); render(); } },
          el("span", { class: "pc-seg-name", text: placeText(p, key).label }), el("span", { class: "pc-seg-price", text: usd(other.total.mid) }));
      })));

    const toggle = e.flags.anesthesiaAvailable && el("label", { class: "pc-check" },
      el("input", { type: "checkbox", checked: anesthesia, onchange: (ev) => { anesthesia = ev.target.checked; writeUrl(); render(); } }),
      " Include an anesthesia provider");

    const cosmetic = p.cosmetic && el("aside", { class: "pc-cosmetic" },
      el("h3", { text: "If it's cosmetic" }),
      el("p", {}, "Insurance and Medicare pay only when a procedure is medically necessary. Done for appearance, it is priced on a separate, cash market: ",
        `the ${p.cosmetic.source} says “${p.cosmetic.quote}”, and that ${p.cosmetic.excludes ? "“" + p.cosmetic.excludes + "”" : "other charges may apply"}. It doesn't say which year that average is from. `,
        el("a", { href: p.cosmetic.url, rel: "noopener", text: "Its page on the cost" }), "."));

    const card = el("article", { class: "pc-card" },
      el("header", { class: "pc-card-head" },
        el("p", { class: "kicker", text: p.specialty }),
        el("h2", { id: "pc-name", text: p.name }),
        el("p", { class: "pc-about", text: p.about }),
        el("p", { class: "pc-code" }, "Billing code ", el("strong", { text: p.code }), p.retired ? " (retired in 2026; see below)" : "", ` · Medicare's description: ${p.medicare_description}`)),
      tabs,
      el("div", { class: "pc-hero" },
        el("div", { class: "pc-hero-main" },
          el("p", { class: "pc-label", text: "Best guess, total price" }),
          el("p", { class: "pc-number", text: usd(t.mid) })),
        el("div", { class: "pc-hero-side" },
          el("p", { class: "pc-label", text: "Likely range" }),
          el("p", { class: "pc-number-2", text: `${usd(t.low)} – ${usd(t.high)}` }))),
      el("p", { class: "pc-scope", text: `${scope}. Private insurance or self-pay. Medicare's own price, counting the patient's share, is about ${usd(t.medicare)}.` }),
      rangeFigure(t),
      toggle,
      breakdown(e),
      el("div", { class: "pc-notes" }, el("h3", { text: "How we got this number" }), el("ol", {}, working(p, e)),
        el("p", { class: "pc-fineprint", text: "Medicare's price is the full amount it allows for the service: its own payment plus the patient's share." })),
      el("div", { class: "pc-notes" }, el("h3", { text: "Good to know" }), el("ul", {}, notes(p, e).map((n) => el("li", {}, n)))),
      callScript(p, e),
      cosmetic,
      el("p", { class: "pc-share" }, el("button", { type: "button", class: "pc-copy", onclick: copyLink, text: "Copy link to this estimate" }),
        el("span", { class: "pc-copied", role: "status", "aria-live": "polite" })));

    $("pc-empty").hidden = true;
    for (const n of detail.querySelectorAll(".pc-card")) n.remove();
    detail.append(card);
    document.title = `${p.name}: about ${usd(t.mid)} — Price Check`;
    if (focus) show();
  }

  function show() {
    detail.focus({ preventScroll: true });
    if (matchMedia("(max-width: 900px)").matches) detail.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  }

  function copyLink(ev) {
    const note = ev.target.parentNode.querySelector(".pc-copied");
    const done = (text) => { note.textContent = text; };
    if (navigator.clipboard) navigator.clipboard.writeText(location.href).then(() => done("Copied."), () => done(location.href));
    else done(location.href);
  }

  function choose(id, push) {
    current = byId[id] || null;
    setting = null;
    writeUrl(push);
    render(true);
  }

  // Show the menu for a search (a kind of doctor's button, or Enter in the search box).
  function browse(text) {
    q.value = text;
    current = null;
    setting = null;
    filter();
    writeUrl(true);
    render(true);
  }

  root.addEventListener("click", (ev) => {
    const a = ev.target.closest("a[data-id], a[data-q]");
    if (!a || !data || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.button) return;
    ev.preventDefault();
    if (a.dataset.id) choose(a.dataset.id, true);
    else browse(fold(a.dataset.q) === fold(q.value) && !current ? "" : a.dataset.q);   // a second click clears it
  });
  q.addEventListener("input", () => {
    if (!data) return;
    filter();
    if (!current) { writeUrl(); render(); }
  });
  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    if (!data || !q.value.trim()) return;
    const found = search(data, q.value);
    if (found.length === 1) choose(found[0].id, true);   // one match: straight to its estimate
    else if (found.length) browse(q.value.trim());       // several: the menu
  });
  stateSel.addEventListener("change", () => { if (!data) return; writeUrl(); listPrices(); render(); });
  addEventListener("popstate", () => { if (!data) return; readUrl(); listPrices(); filter(); render(); });

  fetch(`${window.WW_BASE || ""}/prices/data.json`)
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((d) => {
      data = d;
      for (const p of d.procedures) byId[p.id] = p;
      readUrl();
      listPrices();
      filter();
      render();
    })
    .catch(() => {
      count.textContent = "The price data couldn't be loaded. Check your connection and reload the page.";
      count.classList.add("error");
    });
})();
