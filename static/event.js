// Storm event page: /storms/event/?id=N. Renders one NOAA record into #event-root from WWData.event,
// with the same structure as the old server-rendered page. All data goes in via textContent.
(function () {
  const root = document.getElementById("event-root");
  if (!root) return;
  const BASE = window.WW_BASE || "";
  const nf = new Intl.NumberFormat("en-US");
  const money = window.WWCharts ? window.WWCharts.FORMATS.damage : v => "$" + nf.format(v);
  // The shell's <title> ends with the site name ("Storm event — What Works? News Center").
  const SITE = document.title.split(" — ").pop() || "What Works? News Center";

  function h(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const k in attrs || {}) {
      if (k === "class") n.className = attrs[k];
      else n.setAttribute(k, attrs[k]);
    }
    for (const k of kids) if (k != null && k !== false) n.append(k);
    return n;
  }

  const desk = `${BASE}/storms/`;
  const back = () => h("p", null, h("a", { href: desk }, "← Back to the Storm Desk"));

  function notFound(id, why) {
    document.title = `Event not found — ${SITE}`;
    root.replaceChildren(
      h("header", null,
        h("a", { class: "kicker", href: desk }, "Storm Desk"),
        h("h1", null, why ? "Couldn't load this event" : "Event not found"),
        h("p", { class: "meta" }, why
          ? "The storm data didn't load. Check your connection and try again."
          : id ? `There's no NOAA storm event with ID ${id} in our records.`
               : "This link is missing an event ID.")),
      h("div", { class: "prose" },
        h("p", null, "Browse and filter every recorded event on the Storm Desk.")),
      back());
  }

  /* NOAA separates paragraphs with "|". */
  const paras = text => String(text || "").split("|").filter(p => p.trim()).map(p => h("p", null, p));

  function stat(num, label) {
    return h("div", { class: "stat" }, h("span", { class: "stat-num" }, num), h("span", { class: "stat-label" }, label));
  }

  function render(e) {
    const where = [e.cz_name, e.state].filter(Boolean).join(", "); // a few records have no state
    document.title = `${e.event_type} — ${where} (${e.year}) — ${SITE}`;
    const meta = [`Began ${e.date}`];
    if (e.tor_f_scale) meta.push(e.tor_f_scale);
    if (e.magnitude) meta.push(`Magnitude ${e.magnitude} ${e.magnitude_type || ""}`.trim());

    const prose = h("div", { class: "prose" });
    if (e.narrative) prose.append(h("h2", null, "What happened"), ...paras(e.narrative));
    if (e.episode_narrative) prose.append(h("h2", null, "The bigger picture"), ...paras(e.episode_narrative));
    if (!e.narrative && !e.episode_narrative)
      prose.append(h("p", null, h("em", null,
        "NOAA has no narrative on file for this event. Narratives are mostly available from 1996 onward.")));

    if (e.fatalities && e.fatalities.length) {
      const body = h("tbody");
      for (const f of e.fatalities)
        body.append(h("tr", null, h("td", null, f.type === "D" ? "Direct" : "Indirect"),
          h("td", null, f.age ? String(f.age) : "—"), h("td", null, f.sex || "—"), h("td", null, f.location || "—")));
      prose.append(h("h2", null, "Fatality records"),
        h("table", null, h("thead", null, h("tr", null, ...["Type", "Age", "Sex", "Location"].map(t => h("th", null, t)))), body));
    }

    let mapEl = null;
    if (e.lat && e.lon) {
      const more = new URLSearchParams({ state: e.state, event_type: e.event_type });
      mapEl = h("div", { class: "map mini", id: "event-map", role: "region", "aria-label": "Event location map" });
      // A few records have no state; a link "in " would land on the national list, so leave it out.
      prose.append(h("h2", null, "Where it began"), mapEl,
        h("p", { class: "map-note" }, `${Number(e.lat).toFixed(4)}, ${Number(e.lon).toFixed(4)}`,
          ...(e.state ? [" · ", h("a", { href: `${desk}?${more}` }, `More ${String(e.event_type).toLowerCase()} events in ${e.state} →`)] : [])));
    }

    root.replaceChildren(
      h("header", null,
        h("a", { class: "kicker", href: desk }, `Storm Desk · Event #${e.id}`),
        h("h1", null, `${e.event_type} in ${where}`),
        h("p", { class: "meta" }, meta.join(" · "))),
      h("div", { class: "stat-row" },
        stat(nf.format(e.deaths || 0), "deaths"), stat(nf.format(e.injuries || 0), "injuries"),
        stat(money(e.damage_property || 0), "property damage"), stat(money(e.damage_crops || 0), "crop damage")),
      prose,
      back());

    if (mapEl && window.L && window.WWMap) miniMap(mapEl, [Number(e.lat), Number(e.lon)]);
  }

  function miniMap(el, at) {
    const map = L.map(el, { preferCanvas: true }).setView(at, 9);
    WWMap.tiles(map);
    WWMap.politeScroll(map);
    const token = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
    const style = () => ({ radius: 8, fillColor: token("--accent"), fillOpacity: 0.9, color: token("--surface"), weight: 2 });
    const dot = L.circleMarker(at, style()).addTo(map);
    const restyle = () => dot.setStyle(style());
    new MutationObserver(restyle).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", restyle);
  }

  const raw = new URLSearchParams(location.search).get("id") || "";
  const id = /^\d+$/.test(raw.trim()) ? Number(raw.trim()) : null;
  if (id == null) notFound(raw.trim());
  else window.WWData.event(id).then(e => (e ? render(e) : notFound(id)), () => notFound(id, true));
})();
