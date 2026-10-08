/* Storm Desk map: a Leaflet map with two views over the same filters.
 *   Locations — located events aggregated to a grid that refines with zoom; individual events up close.
 *   By state  — choropleth of every matching event (zone-reported hazards like heat have no coordinates,
 *               so this is the complete view).
 * Exposes window.WWMap.create(...) for the explorer and window.WWMap.tiles(map) for mini maps. */
(function () {
  const { FORMATS, LABELS } = window.WWCharts;
  const BASE = window.WW_BASE || "";
  const nf = new Intl.NumberFormat("en-US");

  // Sequential blue, light->dark on light; dark->light on dark so low values recede into the surface.
  const RAMP = { light: ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"],
                 dark:  ["#104281", "#1c5cab", "#2a78d6", "#5598e7", "#9ec5f4"] };
  const EMPTY = { light: "#f0efec", dark: "#383835" };
  const ALIASES = { "virgin islands": "united states virgin islands" };

  const isDark = () => {
    const t = document.documentElement.dataset.theme;
    return t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  };
  const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  /* Basemap from site.toml [map]. CSS (--tile-filter) grays it out, and inverts it in dark mode,
   * so the data stays the loudest thing on the map. */
  function tiles(map) {
    const cfg = window.WW_TILES || {};
    L.tileLayer(cfg.tiles || "https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: cfg.attribution || "&copy; OpenStreetMap contributors", maxZoom: 19,
    }).addTo(map);
  }
  function onThemeChange(fn) {
    new MutationObserver(fn).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", fn);
  }

  // Wheel-zoom only after the reader clicks into the map, so scrolling the page doesn't get hijacked.
  function politeScroll(map) {
    map.scrollWheelZoom.disable();
    map.on("click focus", () => map.scrollWheelZoom.enable());
    map.getContainer().addEventListener("mouseleave", () => map.scrollWheelZoom.disable());
  }

  let statesGeo; // loaded once
  async function loadStates() {
    if (!statesGeo) {
      const topo = await (await fetch(`${BASE}/static/vendor/states-10m.json`)).json();
      statesGeo = topojson.feature(topo, topo.objects.states);
    }
    return statesGeo;
  }

  function quantileBreaks(values, n) {
    const v = values.filter(x => x > 0).sort((a, b) => a - b);
    if (!v.length) return [];
    const breaks = [];
    for (let i = 1; i < n; i++) breaks.push(v[Math.min(v.length - 1, Math.floor((i / n) * v.length))]);
    return [...new Set(breaks)];
  }

  function create({ el, onPickState, onMove }) {
    const ui = {
      sub: el.querySelector(".chart-sub"),
      legend: el.querySelector(".map-legend"),
      note: el.querySelector(".map-note"),
      buttons: el.querySelectorAll("[data-view]"),
    };
    const map = L.map(el.querySelector(".map"), { preferCanvas: true, minZoom: 2, maxZoom: 13, worldCopyJump: true })
      .setView([38.5, -96], 4);
    tiles(map);
    politeScroll(map);
    const layer = L.layerGroup().addTo(map);
    let box = null, boxBounds = null; // outline of a linked area the map view doesn't match exactly

    let state = { filters: {}, metric: "events" };
    let view = "points", userChose = false, seq = 0, lastState = null, areaMode = false, you = null;

    ui.buttons.forEach(b => b.addEventListener("click", () => {
      userChose = true;
      setView(b.dataset.view);
      draw();
    }));
    function setView(v) {
      view = v;
      ui.buttons.forEach(b => b.setAttribute("aria-pressed", String(b.dataset.view === v)));
    }

    /* Area mode: the rest of the page is filtered to what the map shows, so only Locations makes sense. */
    function setAreaMode(on) {
      areaMode = on;
      ui.buttons.forEach(b => {
        if (b.dataset.view === "states") {
          b.disabled = on;
          b.title = on ? "Turn off “Limit everything to the map area” to see states" : "";
        }
      });
      if (on) setView("points");
      draw();
    }

    function bounds() {
      const b = map.getBounds();
      return [b.getSouth(), Math.max(-180, b.getWest()), b.getNorth(), Math.min(180, b.getEast())];
    }

    /* Size of the area the page is filtered to (a linked area can differ from the view). */
    function areaSize() {
      const a = (state.filters.area || "").split(",").map(Number);
      const [s, w, n, e] = a.length === 4 && a.every(Number.isFinite) ? a : bounds();
      const lat = (s + n) / 2, lng = (w + e) / 2;
      const km = (p, q) => Math.round(map.distance(p, q) / 1000);
      return `${km([lat, w], [lat, e])} × ${km([s, lng], [n, lng])} km`;
    }

    /* Outline [s, w, n, e] on the map, or remove the outline with null. */
    function outline(b) {
      boxBounds = b;
      if (box) map.removeLayer(box);
      box = b && L.rectangle([[b[0], b[1]], [b[2], b[3]]], { color: css("--accent"), weight: 2, dashArray: "6 4",
        fill: false, interactive: false }).addTo(map);
    }

    /* Center on the reader. The position never leaves the browser; only the
     * map's rectangle is used as a filter. Resolves to an error message, or null on success. */
    function locate() {
      return new Promise(resolve => {
        if (!navigator.geolocation) return resolve("This browser can't share its location.");
        if (!window.isSecureContext) return resolve("Near me needs the site to be served over HTTPS.");
        navigator.geolocation.getCurrentPosition(pos => {
          const at = L.latLng(pos.coords.latitude, pos.coords.longitude);
          if (you) map.removeLayer(you);
          you = L.circleMarker(at, { radius: 7, fillColor: css("--accent"), fillOpacity: 1, color: css("--surface"), weight: 3 })
            .bindTooltip("You are here (approximately)").addTo(map);
          map.setView(at, 9); // roughly 50 miles each way on a desktop-width map
          resolve(null);
        }, err => resolve(err.code === 1
          ? "Location permission was denied. You can still pan the map anywhere and use “Limit everything to the map area”."
          : "Couldn't get your location. Try again, or pan the map and use “Limit everything to the map area”."),
        { enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 });
      });
    }

    async function update(filters, metric) {
      state = { filters, metric };
      if (filters.state && filters.state !== lastState) await zoomToState(filters.state).catch(() => {}); // the outline is a nicety
      lastState = filters.state || null;
      draw(true);
    }

    async function zoomToState(name) {
      const geo = await loadStates();
      const key = ALIASES[name.toLowerCase()] || name.toLowerCase();
      const f = geo.features.find(x => x.properties.name.toLowerCase() === key);
      if (f) map.fitBounds(L.geoJSON(f).getBounds(), { padding: [12, 12], maxZoom: 7 });
    }

    async function draw(auto = false) {
      const my = ++seq;
      const b = map.getBounds();
      const { area, ...filters } = state.filters; // the map's own view box already bounds it
      let pts;
      try {
        pts = await window.WWData.map(map.getZoom(),
          [b.getSouth(), Math.max(-180, b.getWest()), b.getNorth(), Math.min(180, b.getEast())], state.metric, filters);
      } catch (e) {
        if (my !== seq) return;
        layer.clearLayers();
        ui.legend.innerHTML = "";
        ui.note.textContent = "Couldn't load the map data. Try again in a moment.";
        ui.note.classList.add("warn");
        return;
      }
      if (my !== seq) return;
      const cov = pts.coverage, share = cov.total ? cov.located / cov.total : 1;
      // Most of this selection can't be placed on a map -> lead with the complete view.
      if (auto && !userChose && !areaMode) setView(share < 0.5 ? "states" : "points");
      if (view === "points") renderPoints(pts, share);
      else await renderStates(my, share).catch(() => {
        if (my === seq) ui.note.textContent = "Couldn't load the state totals. Try again in a moment.";
      });
    }

    function renderPoints(pts, share) {
      layer.clearLayers();
      const { metric } = state, fmt = FORMATS[metric], label = LABELS[metric].toLowerCase();
      const fill = css("--series-1"), ring = css("--surface");
      const items = pts.items;
      const max = Math.max(1, ...items.map(d => pts.mode === "cells" ? d.value : (metric === "events" ? 1 : d[metric])));
      const r = v => 3 + 13 * Math.sqrt(v / max);

      for (const d of items) {
        const v = pts.mode === "cells" ? d.value : (metric === "events" ? 1 : d[metric]);
        const m = L.circleMarker([d.lat, d.lon], {
          radius: pts.mode === "cells" ? r(v) : metric === "events" ? 5 : 4 + 8 * Math.sqrt(v / max),
          fillColor: fill, fillOpacity: 0.55, color: ring, weight: 1,
        }).addTo(layer);
        if (pts.mode === "cells") {
          const extra = metric === "events" ? "" : ` from ${nf.format(d.events)} events`;
          m.bindTooltip(`<b>${fmt(v)}</b> ${label}${extra}<br><span class="muted">Click to zoom in</span>`, { direction: "top" });
          m.on("click", () => map.setView([d.lat, d.lon], Math.min(map.getZoom() + 2, 9)));
        } else {
          const toll = [d.deaths && `${nf.format(d.deaths)} killed`, d.injuries && `${nf.format(d.injuries)} injured`,
            d.damage && `${FORMATS.damage(d.damage)} damage`].filter(Boolean).join(" · ");
          const t = document.createElement("div");
          t.innerHTML = "<b></b><br><span></span><br><span class='muted'></span>";
          t.children[0].textContent = `${d.event_type} · ${d.begin_date}`;
          t.children[2].textContent = `${d.cz_name}, ${d.state}`;
          t.children[4].textContent = toll || "Click for details";
          m.bindTooltip(t, { direction: "top" });
          m.on("click", () => { location.href = `${BASE}/storms/event/?id=${d.event_id}`; });
        }
      }

      if (you) you.bringToFront();

      if (pts.mode === "cells") {
        const km = Math.round(pts.cell * 111);
        ui.sub.textContent = `${LABELS[metric]} per ${pts.cell}° grid cell (about ${km} km). Zoom in for more detail, down to individual events.`;
        ui.legend.innerHTML = sizeKey([max, max / 4].map(v => [r(v), fmt(Math.round(v))]), fill, ring);
      } else {
        const capped = items.length >= 1500;
        ui.sub.textContent = !capped ? "Individual events in view. Click one for its full NOAA report."
          : metric === "events" ? "Individual events: the 1,500 most recent in view. Click one for its full NOAA report."
          : `Individual events: the top 1,500 in view by ${label}. Click one for its full NOAA report.`;
        ui.legend.innerHTML = "";
      }
      if (areaMode) {
        ui.note.textContent = `Everything on this page is limited to the map area (about ${areaSize()}). ` +
          "Only events with coordinates can be placed in an area. Zone-reported hazards (heat, winter storms, drought, high wind) aren't included.";
        ui.note.classList.add("warn");
        return;
      }
      const pct = Math.round(share * 1000) / 10;
      ui.note.textContent = share >= 0.995
        ? "Every matching event has recorded coordinates."
        : `Shows ${pct}% of matching ${label}, the share with recorded coordinates. ` +
          "Zone-reported hazards (heat, winter storms, drought, high wind) have none, so use By state for the complete picture.";
      ui.note.classList.toggle("warn", share < 0.9);
    }

    function sizeKey(entries, fill, ring) {
      return `<span class="key-title">Circle size</span>` + entries.map(([r, label]) =>
        `<span class="key-item"><svg width="${2 * r + 4}" height="${2 * r + 4}" aria-hidden="true">
          <circle cx="${r + 2}" cy="${r + 2}" r="${r}" fill="${fill}" fill-opacity=".55" stroke="${ring}"/></svg>${label}</span>`).join("");
    }

    async function renderStates(my, share) {
      const { metric, filters } = state, fmt = FORMATS[metric], label = LABELS[metric].toLowerCase();
      const [geo, rows] = await Promise.all([
        loadStates(),
        window.WWData.breakdown("state", metric, 100, filters),
      ]);
      if (my !== seq) return;
      layer.clearLayers();
      const mode = isDark() ? "dark" : "light", ramp = RAMP[mode];
      const byName = new Map(rows.map(r => [ALIASES[r.label.toLowerCase()] || r.label.toLowerCase(), r]));
      // A break equal to the smallest value would leave the first color class empty (and the legend
      // would read "1 | 1–3"), so classes start at the smallest value and breaks must sit above it.
      const positive = rows.map(r => r.value).filter(v => v > 0);
      const min = positive.length ? Math.min(...positive) : 0;
      const breaks = quantileBreaks(positive, ramp.length).filter(b => b > min);
      const color = v => !v ? EMPTY[mode] : ramp[Math.min(breaks.filter(b => v >= b).length, ramp.length - 1)];
      const ranked = rows.slice().sort((a, b) => b.value - a.value);
      const names = new Set(geo.features.map(f => f.properties.name.toLowerCase()));
      const marine = rows.filter(r => !names.has(ALIASES[r.label.toLowerCase()] || r.label.toLowerCase()));

      L.geoJSON(geo, {
        style: f => ({ fillColor: color(byName.get(f.properties.name.toLowerCase())?.value), fillOpacity: 0.85,
                       color: css("--surface"), weight: 1 }),
        onEachFeature: (f, lyr) => {
          const row = byName.get(f.properties.name.toLowerCase());
          const rank = row ? ranked.indexOf(row) + 1 : null;
          lyr.bindTooltip(`<b>${f.properties.name}</b><br>${row ? fmt(row.value) : 0} ${label}` +
            (rank ? `<br><span class="muted">#${rank} of ${ranked.length} · click to filter</span>` : ""), { sticky: true });
          lyr.on("mouseover", () => lyr.setStyle({ weight: 2, color: css("--ink") }));
          lyr.on("mouseout", () => lyr.setStyle({ weight: 1, color: css("--surface") }));
          if (row && onPickState) lyr.on("click", () => onPickState(row.label));
        },
      }).addTo(layer);

      ui.sub.textContent = `${LABELS[metric]} by state. Every matching event is counted, including ones without coordinates.`;
      // Class i holds lo <= v < next break. Counts are integers, so show the inclusive top (next - 1);
      // dollars are continuous, so show "under $X" style bounds instead.
      const edges = positive.length ? [min, ...breaks] : [];
      const whole = metric !== "damage";
      ui.legend.innerHTML = `<span class="key-title">${LABELS[metric]}</span>` + ramp.slice(0, edges.length).map((c, i) => {
        const lo = edges[i], next = edges[i + 1];
        const hi = next === undefined ? null : whole ? next - 1 : next;
        const text = hi === null ? `${fmt(lo)}+` : whole && hi <= lo ? fmt(lo) : `${fmt(lo)}–${whole ? "" : "<"}${fmt(hi)}`;
        return `<span class="key-item"><i style="background:${c}"></i>${text}</span>`;
      }).join("") + `<span class="key-item"><i style="background:${EMPTY[mode]}"></i>None</span>`;
      const marineTotal = marine.reduce((s, r) => s + r.value, 0);
      ui.note.textContent = marineTotal
        ? `${fmt(marineTotal)} ${label} in marine zones (e.g. ${marine.slice(0, 2).map(r => r.label).join(", ")}) have no state to shade.`
        : "";
      ui.note.classList.remove("warn");
    }

    let mt;
    map.on("moveend", () => {
      clearTimeout(mt);
      // In area mode the page re-filters, which calls update() and redraws the map too.
      if (areaMode && onMove) mt = setTimeout(() => onMove(bounds()), 350);
      else if (view === "points") mt = setTimeout(() => draw(), 200);
    });
    onThemeChange(() => { draw(); if (boxBounds) outline(boxBounds); });

    return { update, map, setAreaMode, bounds, locate, outline, redraw: () => draw() };
  }

  window.WWMap = { create, tiles, politeScroll };
})();
