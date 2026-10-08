/* Client data layer for the static site: window.WWData answers the questions the old FastAPI
 * endpoints did, from precomputed JSON under ${WW_BASE}/data/ (see docs/STATIC_SITE.md).
 * Every method returns a Promise. Fetched files and derived lookups are cached in memory. */
(function () {
  const BASE = () => `${window.WW_BASE || ""}/data`;
  const METRICS = ["events", "deaths", "injuries", "damage"];
  const MAX_AREA_TILES = 80;
  const MAP_EVENT_LIMIT = 1500;

  // ---- Fetching -----------------------------------------------------------------------
  const files = new Map(); // path -> Promise of parsed JSON
  function load(path) {
    if (!files.has(path)) {
      // Data files are stored gzipped (<path>.gz) to fit GitHub Pages' 1 GB limit; Pages serves them
      // as plain application/gzip, so we decompress here rather than relying on Content-Encoding.
      const p = fetch(`${BASE()}/${path}.gz`).then(r => {
        if (!r.ok) throw Object.assign(new Error(`${path}: HTTP ${r.status}`), { status: r.status });
        return new Response(r.body.pipeThrough(new DecompressionStream("gzip"))).json();
      });
      p.catch(() => files.delete(path)); // let a later call retry
      files.set(path, p);
    }
    return files.get(path);
  }

  /* meta.json plus the lookups every query needs: label -> index maps and tile/block sets. */
  let metaP;
  function info() {
    if (!metaP) {
      metaP = load("meta.json").then(meta => ({
        meta,
        stateIx: new Map(meta.states.map((s, i) => [s, i])),
        typeIx: new Map(meta.types.map((t, i) => [t, i])),
        tiles: new Set(meta.tiles || []),
        blocks: new Set(meta.grid025_blocks || []),
      }));
      metaP.catch(() => { metaP = null; });
    }
    return metaP;
  }

  const colIx = cols => Object.fromEntries(cols.map((c, i) => [c, i]));

  /* Tabular file -> typed columns, so the hot loops never touch per-row arrays. */
  function columnar(table, intCols) {
    const n = table.rows.length, ix = colIx(table.cols), out = { n, cell: table.cell };
    for (const c of table.cols) {
      const a = intCols.includes(c) ? new Int32Array(n) : new Float64Array(n), k = ix[c];
      for (let i = 0; i < n; i++) a[i] = table.rows[i][k] || 0;
      out[c] = a;
    }
    return out;
  }
  const derived = new Map(); // path -> Promise of columnar table
  function loadColumnar(path, intCols) {
    if (!derived.has(path)) {
      const p = load(path).then(t => columnar(t, intCols));
      p.catch(() => derived.delete(path));
      derived.set(path, p);
    }
    return derived.get(path);
  }
  const cube = () => loadColumnar("cube.json", ["s", "t", "y", "m"]);
  const grid = path => loadColumnar(path, ["s", "t", "y"]);

  // ---- Filters ------------------------------------------------------------------------
  function toInt(v) {
    if (v === "" || v == null) return null;
    const n = parseInt(v, 10);
    return Number.isFinite(n) ? n : null;
  }

  /* 'south,west,north,east' or [s, w, n, e] -> rounded array, or null if absent/invalid. */
  function parseArea(area) {
    if (!area) return null;
    const v = (Array.isArray(area) ? area : String(area).split(",")).map(x => Math.round(parseFloat(x) * 1000) / 1000);
    if (v.length !== 4 || !v.every(Number.isFinite)) return null;
    const [s, w, n, e] = v;
    return -90 <= s && s < n && n <= 90 && -180 <= w && w < e && e <= 180 ? v : null;
  }

  /* Filters object -> indices the loops can test cheaply. A state or type label that isn't in the
   * data matches nothing (as the old SQL did); empty values and unknown keys are ignored. */
  function compile(f, I) {
    f = f || {};
    const c = { s: -1, types: null, y0: toInt(f.year_from), y1: toInt(f.year_to), area: parseArea(f.area),
                none: false, state: f.state || null };
    if (f.state) {
      c.s = I.stateIx.has(f.state) ? I.stateIx.get(f.state) : -1;
      if (c.s < 0) c.none = true;
    }
    const names = String(f.event_type || "").split(",").map(t => t.trim()).filter(Boolean);
    if (names.length) {
      c.types = new Uint8Array(I.meta.types.length);
      let any = false;
      for (const t of names) if (I.typeIx.has(t)) { c.types[I.typeIx.get(t)] = 1; any = true; }
      if (!any) c.none = true;
    }
    if (c.y0 == null) c.y0 = -Infinity;
    if (c.y1 == null) c.y1 = Infinity;
    return c;
  }
  const keep = (c, s, t, y) => (c.s < 0 || s === c.s) && (!c.types || c.types[t] === 1) && y >= c.y0 && y <= c.y1;
  const metricOf = m => (METRICS.includes(m) ? m : "events");

  // ---- Area queries over tiles ----------------------------------------------------------
  /* Existing 1° tile keys whose square touches the box [s, w, n, e]. */
  function tileKeys(I, [s, w, n, e]) {
    const keys = [];
    for (let la = Math.floor(s); la <= Math.floor(n); la++)
      for (let lo = Math.floor(w); lo <= Math.floor(e); lo++) {
        const k = `${la}_${lo}`;
        if (I.tiles.has(k)) keys.push(k);
      }
    return keys;
  }
  const loadTiles = keys => Promise.all(keys.map(k => load(`tiles/${k}.json`)));

  /* Call fn(row, ix) for every tile row matching the filters and inside the box. */
  function eachTileRow(tiles, c, [s, w, n, e], fn) {
    if (c.none) return;
    for (const tile of tiles) {
      const ix = colIx(tile.cols), iS = ix.s, iT = ix.t, iD = ix.date, iLa = ix.lat, iLo = ix.lon;
      for (const r of tile.rows) {
        const lat = r[iLa], lon = r[iLo];
        if (lat < s || lat > n || lon < w || lon > e || lat === 0) continue;
        if (!keep(c, r[iS], r[iT], Math.floor(r[iD] / 10000))) continue;
        fn(r, ix);
      }
    }
  }

  /* The located events inside f.area, or Error("area-too-large") past MAX_AREA_TILES tiles. */
  async function areaRows(I, c) {
    const keys = tileKeys(I, c.area);
    if (keys.length > MAX_AREA_TILES) throw new Error("area-too-large");
    const tiles = await loadTiles(keys), out = [];
    let ix = null;
    eachTileRow(tiles, c, c.area, (r, x) => { out.push(r); ix = ix || x; });
    return { rows: out, ix: ix || { id: 0, date: 1, s: 2, t: 3, cz: 4, deaths: 5, injuries: 6, damage: 7, lat: 8, lon: 9 } };
  }

  // ---- Public queries ---------------------------------------------------------------------
  async function byYear(f) {
    const I = await info(), c = compile(f, I);
    const acc = new Map(); // year -> {year, events, deaths, injuries, damage}
    const add = (y, ev, de, inj, dmg) => {
      let r = acc.get(y);
      if (!r) acc.set(y, r = { year: y, events: 0, deaths: 0, injuries: 0, damage: 0 });
      r.events += ev; r.deaths += de; r.injuries += inj; r.damage += dmg;
    };
    if (c.area) {
      const { rows, ix } = await areaRows(I, c);
      for (const r of rows) add(Math.floor(r[ix.date] / 10000), 1, r[ix.deaths], r[ix.injuries], r[ix.damage]);
    } else if (!c.none) {
      const C = await cube();
      for (let i = 0; i < C.n; i++)
        if (keep(c, C.s[i], C.t[i], C.y[i])) add(C.y[i], C.events[i], C.deaths[i], C.injuries[i], C.damage[i]);
    }
    return [...acc.values()].filter(r => r.events > 0).sort((a, b) => a.year - b.year);
  }

  async function breakdown(by = "event_type", metric = "events", limit = 12, f) {
    by = ["event_type", "state", "month"].includes(by) ? by : "event_type";
    metric = metricOf(metric);
    limit = toInt(limit) ?? 12;
    const I = await info(), c = compile(f, I);
    const sums = new Map(); // group index -> value
    const add = (k, v) => sums.set(k, (sums.get(k) || 0) + v);
    if (c.area) {
      const { rows, ix } = await areaRows(I, c);
      const mk = metric === "events" ? -1 : ix[metric];
      const gk = by === "event_type" ? ix.t : by === "state" ? ix.s : -1;
      for (const r of rows) add(gk < 0 ? Math.floor(r[ix.date] / 100) % 100 : r[gk], mk < 0 ? 1 : r[mk]);
    } else if (!c.none) {
      const C = await cube(), V = C[metric], G = by === "event_type" ? C.t : by === "state" ? C.s : C.m;
      for (let i = 0; i < C.n; i++) if (keep(c, C.s[i], C.t[i], C.y[i]) && V[i]) add(G[i], V[i]);
    }
    const names = by === "event_type" ? I.meta.types : by === "state" ? I.meta.states : null;
    const rows = [];
    for (const [k, v] of sums) if (v > 0) rows.push({ label: names ? names[k] : k, value: v });
    if (by === "month") rows.sort((a, b) => a.label - b.label);
    else rows.sort((a, b) => b.value - a.value || (a.label < b.label ? -1 : 1));
    return rows.slice(0, limit);
  }

  async function coverage(metric = "events", f) {
    metric = metricOf(metric);
    const I = await info(), c = compile(f, I);
    let total = 0, located = 0;
    if (c.area) {
      // Only located events can fall inside an area, so the two agree.
      const { rows, ix } = await areaRows(I, c);
      const mk = metric === "events" ? -1 : ix[metric];
      for (const r of rows) total += mk < 0 ? 1 : r[mk];
      located = total;
    } else if (!c.none) {
      const C = await cube(), V = C[metric], L = C["l_" + metric];
      for (let i = 0; i < C.n; i++)
        if (keep(c, C.s[i], C.t[i], C.y[i])) { total += V[i]; located += L[i]; }
    }
    return { total, located };
  }

  /* events(): sorted index lists are cached so "Load more" doesn't re-filter and re-sort. */
  const sorted = new Map(); // key -> Promise of {scope, rows, ix, s}
  const SORT_COL = { date: "date", deaths: "deaths", injuries: "injuries", damage: "damage" };

  async function matching(sort, I, c) {
    const key = JSON.stringify([sort, c.s, c.types && [...c.types], c.y0, c.y1, c.area, c.none]);
    if (sorted.has(key)) return sorted.get(key);
    const p = (async () => {
      let scope, rows, ix, stateIx = c.s;
      if (c.area) {
        scope = "area";
        ({ rows, ix } = await areaRows(I, c));
      } else if (c.s >= 0 || c.none) {
        scope = "state";
        if (c.none) { rows = []; ix = {}; }
        else {
          const t = await load(`state/${c.s}.json`);
          ix = colIx(t.cols);
          const iT = ix.t, iD = ix.date;
          rows = t.rows.filter(r => keep(c, c.s, r[iT], Math.floor(r[iD] / 10000)));
        }
      } else {
        scope = "notable";
        const t = await load("notable.json");
        ix = colIx(t.cols);
        const iS = ix.s, iT = ix.t, iD = ix.date;
        rows = t.rows.filter(r => keep(c, r[iS], r[iT], Math.floor(r[iD] / 10000)));
      }
      const k = ix[SORT_COL[sort]], iD = ix.date, iId = ix.id;
      // Biggest first; ties go to the most recent, then the highest id, so paging is stable.
      rows.sort((a, b) => (b[k] - a[k]) || (b[iD] - a[iD]) || (b[iId] - a[iId]));
      return { scope, rows, ix, stateIx };
    })();
    p.catch(() => sorted.delete(key));
    sorted.set(key, p);
    if (sorted.size > 12) sorted.delete(sorted.keys().next().value);
    return p;
  }

  const isoDate = d => {
    const s = String(d);
    return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
  };

  async function events(sort = "date", limit = 25, offset = 0, f) {
    sort = SORT_COL[sort] ? sort : "date";
    limit = Math.max(0, toInt(limit) ?? 25);
    offset = Math.max(0, toInt(offset) ?? 0);
    const I = await info(), c = compile(f, I);
    const { scope, rows, ix, stateIx } = await matching(sort, I, c);
    return {
      scope,
      rows: rows.slice(offset, offset + limit).map(r => ({
        event_id: r[ix.id],
        begin_date: isoDate(r[ix.date]),
        state: I.meta.states[ix.s === undefined ? stateIx : r[ix.s]],
        cz_name: r[ix.cz],
        event_type: I.meta.types[r[ix.t]],
        deaths: r[ix.deaths],
        injuries: r[ix.injuries],
        damage: r[ix.damage],
      })),
    };
  }

  // ---- Map ------------------------------------------------------------------------------
  // SQLite's round(): halves go away from zero (JS Math.round sends -0.5 to -0).
  const sqlRound = v => (v < 0 ? -Math.round(-v) : Math.round(v));

  async function map(zoom = 4, bbox, metric = "events", f) {
    zoom = toInt(zoom) ?? 4;
    metric = metricOf(metric);
    const I = await info();
    const { area, ...rest } = f || {}; // the bbox already bounds the map
    const c = compile(rest, I);
    // Snap the box outward, as the old server did, so small pans reuse the same files.
    const raw = (Array.isArray(bbox) ? bbox : String(bbox || "-90,-180,90,180").split(",")).map(Number);
    const snap = zoom <= 6 ? 5 : 1;
    const box = [Math.max(-90, Math.floor(raw[0] / snap) * snap), Math.max(-180, Math.floor(raw[1] / snap) * snap),
                 Math.min(90, Math.ceil(raw[2] / snap) * snap), Math.min(180, Math.ceil(raw[3] / snap) * snap)];
    const [s, w, n, e] = box;
    const cov = coverage(metric, rest);

    if (zoom >= 9) {
      const tiles = await loadTiles(tileKeys(I, box));
      let rows = [], ix = null;
      eachTileRow(tiles, c, box, (r, x) => { rows.push(r); ix = ix || x; });
      if (ix) {
        const k = metric === "events" ? ix.date : ix[metric], iD = ix.date, iId = ix.id;
        if (metric !== "events") rows = rows.filter(r => r[k] > 0);
        rows.sort((a, b) => (b[k] - a[k]) || (b[iD] - a[iD]) || (b[iId] - a[iId]));
        rows.length = Math.min(rows.length, MAP_EVENT_LIMIT);
      }
      const items = rows.map(r => ({
        event_id: r[ix.id], begin_date: isoDate(r[ix.date]), state: I.meta.states[r[ix.s]], cz_name: r[ix.cz],
        event_type: I.meta.types[r[ix.t]], deaths: r[ix.deaths], injuries: r[ix.injuries], damage: r[ix.damage],
        lat: r[ix.lat], lon: r[ix.lon],
      }));
      return { mode: "events", coverage: await cov, items };
    }

    // Cells: accumulate into slots keyed by integer cell indices (no per-row allocation).
    const cell = zoom <= 4 ? 1 : zoom <= 6 ? 0.25 : zoom === 7 ? 0.125 : 0.0625;
    const slots = new Map(); // key -> {lat, lon, value, events}
    const add = (lat, lon, value, count) => {
      const key = (Math.round(lat / cell) + 3000) * 8192 + (Math.round(lon / cell) + 4096);
      let d = slots.get(key);
      if (!d) slots.set(key, d = { lat, lon, value: 0, events: 0 });
      d.value += value; d.events += count;
    };
    if (!c.none) {
      if (zoom <= 6) {
        let parts;
        if (zoom <= 4) parts = [await grid("grid1.json")];
        else {
          const keys = [];
          for (let la = Math.floor(s / 5) * 5; la <= n; la += 5)
            for (let lo = Math.floor(w / 5) * 5; lo <= e; lo += 5)
              if (I.blocks.has(`${la}_${lo}`)) keys.push(`${la}_${lo}`);
          parts = await Promise.all(keys.map(k => grid(`grid025/${k}.json`)));
        }
        for (const G of parts) {
          const V = G[metric];
          for (let i = 0; i < G.n; i++) {
            const lat = G.lat[i], lon = G.lon[i];
            if (lat < s || lat > n || lon < w || lon > e) continue;
            if (keep(c, G.s[i], G.t[i], G.y[i])) add(lat, lon, V[i], G.events[i]);
          }
        }
      } else {
        const tiles = await loadTiles(tileKeys(I, box));
        eachTileRow(tiles, c, box, (r, ix) => {
          add(sqlRound(r[ix.lat] / cell) * cell, sqlRound(r[ix.lon] / cell) * cell,
              metric === "events" ? 1 : r[ix[metric]], 1);
        });
      }
    }
    const items = [];
    for (const d of slots.values()) if (d.value > 0) items.push(d);
    return { mode: "cells", cell, coverage: await cov, items };
  }

  // ---- Single records -------------------------------------------------------------------
  async function event(id) {
    id = toInt(id);
    if (id == null || id < 0) return null;
    const I = await info(), shards = I.meta.shards || 4096;
    // A shard that doesn't exist just means no record lives there.
    const shard = (path, key) => load(path).then(o => o[key] || null, e => {
      if (e.status === 404) return null;
      throw e;
    });
    const rec = await shard(`events/${id % shards}.json`, id);
    if (!rec) return null;
    // A record carries its own episode_narrative only when it differs from the episode's usual one.
    if (rec.episode_narrative != null) return rec;
    const episode = rec.episode_id == null ? null
      : await shard(`episodes/${rec.episode_id % shards}.json`, rec.episode_id);
    return { ...rec, episode_narrative: episode };
  }

  function onThisDay(md) {
    if (!/^\d\d-\d\d$/.test(md || "")) return Promise.resolve([]);
    return load(`onthisday/${md}.json`);
  }

  window.WWData = {
    meta: () => info().then(I => I.meta),
    byYear, breakdown, events, coverage, map, event, onThisDay,
  };
})();
