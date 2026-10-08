// Storm Desk explorer: filters drive three charts and a ranked event list. State lives in the URL
// so any view can be linked from a post or a video description. Data comes from WWData (data.js).
(function () {
  const { line, bars, keep, FORMATS, LABELS } = window.WWCharts;
  const data = window.WWData;
  const BASE = window.WW_BASE || "";
  const form = document.getElementById("filters");
  const sort = document.getElementById("sort");
  const list = document.getElementById("results");
  const more = document.getElementById("more");
  const areaBox = document.getElementById("area-only");
  const nearMe = document.getElementById("near-me");
  const status = document.getElementById("area-status");
  const listScope = document.getElementById("list-scope");
  const PAGE = 25;
  let offset = 0, seq = 0, area = null, lastKey = null;
  // A linked ?area= stays the filter until the reader moves the map. Fitting it to a different-sized
  // screen shows more (or less) around it, and that view mustn't silently become the filter.
  let pinned = false;
  const map = window.WWMap.create({
    el: document.getElementById("map-panel"),
    onPickState: name => setFilter("state", name),
    onMove: bounds => {
      if (pinned) map.redraw(); // the view moved but the filter didn't; just repaint the map
      else if (area) { area = bounds; refresh(); }
    },
  });
  function unpin() {
    if (!pinned) return;
    pinned = false;
    map.outline(null);
  }
  for (const ev of ["pointerdown", "wheel", "keydown"])
    map.map.getContainer().addEventListener(ev, unpin, { passive: true });

  // Restore filters from the URL (old links may carry a "q" search; there's no field for it now).
  const params = new URLSearchParams(location.search);
  for (const [k, v] of params) {
    const el = form.elements[k];
    if (!el) continue;
    // The dropdown lists only states with enough events; a linked marine zone still needs an option.
    if (k === "state" && v && ![...el.options].some(o => o.value === v)) el.add(new Option(v));
    el.value = v;
  }
  if (params.get("sort")) sort.value = params.get("sort");
  const linked = (params.get("area") || "").split(",").map(Number);
  if (linked.length === 4 && linked.every(Number.isFinite)) {
    area = linked;
    pinned = true;
    areaBox.checked = true;
    map.map.fitBounds([[linked[0], linked[1]], [linked[2], linked[3]]]);
    map.outline(linked);
    map.setAreaMode(true);
  }

  function setArea(on) {
    unpin();
    area = on ? map.bounds() : null;
    areaBox.checked = on;
    map.setAreaMode(on);
    refresh();
  }
  areaBox.addEventListener("change", () => { status.textContent = ""; setArea(areaBox.checked); });

  nearMe.addEventListener("click", async () => {
    const wasOn = areaBox.checked;
    unpin();
    nearMe.disabled = true;
    status.textContent = "Finding you…";
    if (!wasOn) { area = map.bounds(); areaBox.checked = true; map.setAreaMode(true); }
    const err = await map.locate();
    nearMe.disabled = false;
    status.textContent = err || "";
    if (err) { if (!wasOn) setArea(false); return; }
    // fitBounds may animate; moveend -> onMove usually refreshes, this covers the no-movement case.
    setTimeout(() => { area = map.bounds(); refresh(); }, 700);
  });

  function current() {
    const f = Object.fromEntries(new FormData(form));
    const { metric, ...filters } = f;
    if (area) filters.area = area.map(x => x.toFixed(3)).join(",");
    return { metric, filters };
  }

  function scopeLabel(f) {
    const parts = [f.event_type || "All event types", f.state || "all states"];
    if (f.year_from || f.year_to) {
      const el = form.elements;
      parts.push(`${f.year_from || el.year_from?.placeholder || "1950"}–${f.year_to || el.year_to?.placeholder || "2024"}`);
    }
    if (f.area) parts.push("in the map area");
    return parts.join(" · ");
  }

  /* Which events the list can show depends on the source WWData used (see docs/STATIC_SITE.md). */
  function describeList(scope, f) {
    if (!listScope) return;
    listScope.textContent = scope === "notable"
      ? "Notable events only: those with deaths, injuries or $250K+ damage. Pick a state or limit to the map area to see every event."
      : scope === "area"
      ? "Every matching event with coordinates in the map area. Zone-reported hazards (heat, winter storms, drought) have none, so they aren't listed."
      : `Every matching event in ${f.state}.`;
  }

  function setFilter(name, value) {
    form.elements[name].value = value;
    refresh();
  }

  /* The area spans too many map tiles to load: drop area mode and ask the reader to zoom in. */
  function areaTooLarge() {
    unpin();
    area = null;
    areaBox.checked = false;
    map.setAreaMode(false);
    status.textContent = "That area is too large to list every event. Zoom in on the map, then turn on “Limit everything to the map area” again.";
    lastKey = null;
    refresh();
  }

  function failed(e) {
    if (e && e.message === "area-too-large") return areaTooLarge();
    list.innerHTML = `<li class="event-row empty">Couldn't load the storm data. Try again in a moment.</li>`;
    more.hidden = true;
  }

  async function refresh() {
    const { metric, filters } = current();
    const key = JSON.stringify([filters, metric, sort.value]);
    if (key === lastKey) return; // e.g. a moveend that didn't change the area
    lastKey = key;
    const my = ++seq;
    const url = new URLSearchParams({ ...filters, metric, sort: sort.value });
    for (const [k, v] of [...url]) if (!v) url.delete(k);
    history.replaceState(null, "", url.toString() ? `?${url}` : location.pathname);

    const scope = scopeLabel(filters);
    map.update(filters, metric);
    let years, types, states;
    try {
      [years, types, states] = await Promise.all([
        data.byYear(filters),
        data.breakdown("event_type", metric, 10, filters),
        data.breakdown("state", metric, 10, filters),
      ]);
    } catch (e) {
      if (my === seq) { lastKey = null; failed(e); }
      return;
    }
    if (my !== seq) return; // a newer request superseded this one

    keep(document.getElementById("chart-years"), (root = document.getElementById("chart-years")) =>
      line(root, { title: `${LABELS[metric]} per year`, sub: scope, metric,
        data: years.map(r => ({ x: r.year, y: r[metric] || 0 })) }));
    keep(document.getElementById("chart-types"), (root = document.getElementById("chart-types")) =>
      bars(root, { title: `Top event types by ${LABELS[metric].toLowerCase()}`, sub: "Click a bar to filter", metric,
        colName: "Event type", data: types, onPick: v => setFilter("event_type", v) }));
    keep(document.getElementById("chart-states"), (root = document.getElementById("chart-states")) =>
      bars(root, { title: `Top states by ${LABELS[metric].toLowerCase()}`, sub: "Click a bar to filter", metric,
        colName: "State", data: states, onPick: v => setFilter("state", v) }));

    offset = 0;
    list.innerHTML = "";
    await loadEvents(my);
  }

  async function loadEvents(my = seq) {
    const { filters } = current();
    let res;
    try {
      res = await data.events(sort.value, PAGE, offset, filters);
    } catch (e) {
      if (my === seq) failed(e);
      return;
    }
    if (my !== seq) return;
    const rows = res.rows;
    describeList(res.scope, filters);
    offset += rows.length;
    more.hidden = rows.length < PAGE;
    if (!rows.length && offset === 0) list.innerHTML = `<li class="event-row empty">No events match these filters.</li>`;
    for (const e of rows) {
      const li = document.createElement("li");
      li.className = "event-row";
      const toll = [
        e.deaths && `${FORMATS.deaths(e.deaths)} killed`,
        e.injuries && `${FORMATS.injuries(e.injuries)} injured`,
        e.damage && `${FORMATS.damage(e.damage)} damage`,
      ].filter(Boolean).join(" · ");
      li.innerHTML = `<a><span class="ev-type"></span><span class="ev-where"></span>
        <span class="ev-year"></span></a><span class="ev-toll"></span>`;
      li.querySelector("a").href = `${BASE}/storms/event/?id=${e.event_id}`;
      li.querySelector(".ev-type").textContent = e.event_type;
      li.querySelector(".ev-where").textContent = `${e.cz_name}, ${e.state}`;
      li.querySelector(".ev-year").textContent = e.begin_date;
      li.querySelector(".ev-toll").textContent = toll;
      list.appendChild(li);
    }
  }

  let t;
  form.addEventListener("input", e => {
    clearTimeout(t);
    t = setTimeout(refresh, e.target.type === "number" ? 400 : 0);
  });
  form.addEventListener("submit", e => { e.preventDefault(); refresh(); });
  sort.addEventListener("change", refresh);
  more.addEventListener("click", () => loadEvents());
  refresh();
})();
