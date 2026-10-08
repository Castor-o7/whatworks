/* Tiny SVG chart kit for the Storm Desk: a single-series line/area chart over years and a
 * horizontal ranked bar chart. Both get a hover tooltip and a table view. No dependencies. */
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const nf = new Intl.NumberFormat("en-US");

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

  function niceTicks(max, count = 4) {
    if (max <= 0) return [0, 1];
    const raw = max / count, mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw);
    const ticks = [];
    for (let v = 0; v <= max + step * 0.001; v += step) ticks.push(v);
    if (ticks[ticks.length - 1] < max) ticks.push(ticks[ticks.length - 1] + step);
    return ticks;
  }
  function shortNum(v) {
    if (v >= 1e9) return (v / 1e9).toFixed(v % 1e9 ? 1 : 0) + "B";
    if (v >= 1e6) return (v / 1e6).toFixed(v % 1e6 ? 1 : 0) + "M";
    if (v >= 1e3) return (v / 1e3).toFixed(v % 1e3 ? 1 : 0) + "K";
    return String(v);
  }

  /* Frame: title, subtitle, table toggle, a chart body and a hidden table. */
  function frame(root, title, sub, rows, colName, fmt) {
    root.innerHTML = "";
    const head = document.createElement("div");
    head.className = "chart-head";
    head.innerHTML = `<p class="chart-title"></p><button type="button" class="chart-toggle">Table</button>`;
    head.firstChild.textContent = title;
    root.appendChild(head);
    const s = document.createElement("p");
    s.className = "chart-sub"; s.textContent = sub || "";
    root.appendChild(s);
    const body = document.createElement("div");
    body.className = "chart";
    root.appendChild(body);
    const table = document.createElement("table");
    table.className = "chart-table"; table.hidden = true;
    table.innerHTML = `<thead><tr><th></th><th class="num"></th></tr></thead><tbody></tbody>`;
    table.querySelector("th").textContent = colName;
    table.querySelector("th.num").textContent = title;
    const tb = table.querySelector("tbody");
    rows.forEach(([k, v]) => {
      const tr = document.createElement("tr");
      tr.innerHTML = "<td></td><td class='num'></td>";
      tr.children[0].textContent = k; tr.children[1].textContent = fmt(v);
      tb.appendChild(tr);
    });
    root.appendChild(table);
    const btn = head.querySelector("button");
    btn.onclick = () => {
      table.hidden = !table.hidden; body.hidden = !table.hidden;
      btn.textContent = table.hidden ? "Table" : "Chart";
    };
    const tip = document.createElement("div");
    tip.className = "chart-tip"; tip.hidden = true;
    root.appendChild(tip);
    return { body, tip };
  }

  function showTip(root, tip, x, y, html) {
    const r = root.getBoundingClientRect();
    tip.innerHTML = html; tip.hidden = false;
    const w = tip.offsetWidth / 2;
    tip.style.left = Math.max(w, Math.min(r.width - w, x)) + "px";
    tip.style.top = y + "px";
  }

  /* Years on x, one measure on y. data: [{x: 1950, y: 223}, ...] */
  function line(root, { title, sub, data, metric = "events" }) {
    const fmt = FORMATS[metric];
    const { body, tip } = frame(root, title, sub, data.map(d => [d.x, d.y]), "Year", fmt);
    if (!data.length) { body.innerHTML = `<p class="chart-loading">No matching events.</p>`; return; }
    const W = Math.max(body.clientWidth, 280), H = Math.round(Math.min(300, Math.max(200, W * 0.32)));
    const m = { t: 10, r: 12, b: 24, l: 44 };
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": title }, body);
    const x0 = data[0].x, x1 = data[data.length - 1].x;
    const ticks = niceTicks(Math.max(...data.map(d => d.y)));
    const yMax = ticks[ticks.length - 1];
    const X = v => m.l + (x1 === x0 ? 0.5 : (v - x0) / (x1 - x0)) * (W - m.l - m.r);
    const Y = v => H - m.b - (v / yMax) * (H - m.t - m.b);

    ticks.forEach(t => {
      el("line", { class: "grid-line", x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t) }, svg);
      el("text", { x: m.l - 8, y: Y(t) + 4, "text-anchor": "end" }, svg).textContent =
        metric === "damage" ? "$" + shortNum(t) : shortNum(t);
    });
    const span = x1 - x0, step = span > 40 ? 10 : span > 15 ? 5 : span > 6 ? 2 : 1;
    for (let yr = Math.ceil(x0 / step) * step; yr <= x1; yr += step)
      el("text", { x: X(yr), y: H - 6, "text-anchor": "middle" }, svg).textContent = yr;

    const pts = data.map(d => `${X(d.x).toFixed(1)},${Y(d.y).toFixed(1)}`);
    el("path", { class: "area", d: `M${X(x0)},${Y(0)}L${pts.join("L")}L${X(x1)},${Y(0)}Z` }, svg);
    el("path", { class: "line", d: "M" + pts.join("L") }, svg);
    const last = data[data.length - 1];
    el("circle", { class: "dot", cx: X(last.x), cy: Y(last.y), r: 4 }, svg);

    const cursor = el("line", { class: "cursor", y1: m.t, y2: H - m.b, visibility: "hidden" }, svg);
    const hot = el("circle", { class: "dot", r: 5, visibility: "hidden" }, svg);
    const hit = el("rect", { x: m.l, y: 0, width: W - m.l - m.r, height: H, fill: "transparent" }, svg);
    const byX = new Map(data.map(d => [d.x, d]));
    function move(ev) {
      const p = svg.getBoundingClientRect(), scale = W / p.width;
      const yr = Math.round(x0 + ((ev.clientX - p.left) * scale - m.l) / (W - m.l - m.r) * (x1 - x0));
      const d = byX.get(Math.max(x0, Math.min(x1, yr))) || { x: yr, y: 0 };
      cursor.setAttribute("x1", X(d.x)); cursor.setAttribute("x2", X(d.x)); cursor.setAttribute("visibility", "visible");
      hot.setAttribute("cx", X(d.x)); hot.setAttribute("cy", Y(d.y)); hot.setAttribute("visibility", "visible");
      const rb = root.getBoundingClientRect();
      showTip(root, tip, p.left - rb.left + X(d.x) / scale, p.top - rb.top + Y(d.y) / scale,
        `${d.x} · <b>${fmt(d.y)}</b> ${LABELS[metric].toLowerCase()}`);
    }
    hit.addEventListener("pointermove", move);
    hit.addEventListener("pointerleave", () => {
      tip.hidden = true; cursor.setAttribute("visibility", "hidden"); hot.setAttribute("visibility", "hidden");
    });
  }

  /* Ranked horizontal bars. data: [{label, value}, ...] already sorted. */
  function bars(root, { title, sub, data, metric = "events", colName = "", onPick }) {
    const fmt = FORMATS[metric];
    const { body, tip } = frame(root, title, sub, data.map(d => [d.label, d.value]), colName, fmt);
    if (!data.length) { body.innerHTML = `<p class="chart-loading">No matching events.</p>`; return; }
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
          `${d.label} · <b>${fmt(d.value)}</b>${onPick ? " · click to filter" : ""}`);
      });
      hit.addEventListener("pointerleave", () => {
        tip.hidden = true; svg.querySelectorAll(".mark").forEach(n => n.classList.remove("dim"));
      });
      if (onPick) hit.addEventListener("click", () => onPick(d.label));
    });
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
    fig.innerHTML = `<p class="chart-loading">Loading chart…</p>`;
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
      fig.innerHTML = `<p class="chart-loading">Chart unavailable: the storm data couldn't be loaded.</p>`;
    }
  }
  document.querySelectorAll("figure.storm-chart").forEach(renderShortcode);

  window.WWCharts = { line, bars, keep, FORMATS, LABELS };
})();
