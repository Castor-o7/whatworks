// Front page "On this day in storm history": the most consequential events that began on the
// reader's local calendar day, from WWData.onThisDay. Markup matches the event rows elsewhere.
(function () {
  const list = document.getElementById("on-this-day");
  const sub = document.getElementById("on-this-day-sub");
  if (!list) return;
  const BASE = window.WW_BASE || "";
  const nf = new Intl.NumberFormat("en-US");
  const money = window.WWCharts ? window.WWCharts.FORMATS.damage : v => "$" + nf.format(v);
  const LIMIT = Number(list.dataset.limit) || 4;

  const now = new Date();
  const md = `${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const day = `${now.toLocaleString("en-US", { month: "long" })} ${now.getDate()}`;

  function span(cls, text, parent) {
    const s = document.createElement("span");
    s.className = cls; s.textContent = text;
    parent.appendChild(s);
    return s;
  }

  function row(e) {
    const li = document.createElement("li");
    li.className = "event-row";
    const a = document.createElement("a");
    a.href = `${BASE}/storms/event/?id=${e.id}`;
    span("ev-type", e.type, a);
    span("ev-where", `${e.cz}, ${e.state}`, a);
    span("ev-year", String(e.date).slice(0, 4), a);
    li.appendChild(a);
    span("ev-toll", [
      e.deaths && `${nf.format(e.deaths)} killed`,
      e.injuries && `${nf.format(e.injuries)} injured`,
      e.damage && `${money(e.damage)} damage`,
    ].filter(Boolean).join(" · "), li);
    if (e.excerpt) {
      const p = document.createElement("p");
      p.className = "ev-excerpt";
      p.textContent = e.excerpt + (e.excerpt.length >= 280 ? "…" : "");
      li.appendChild(p);
    }
    return li;
  }

  function message(text) {
    const li = document.createElement("li");
    li.className = "event-row empty";
    li.textContent = text;
    list.replaceChildren(li);
  }

  if (sub) sub.textContent = `${day}, across 75 years of NOAA records`;
  Promise.all([window.WWData.onThisDay(md), window.WWData.meta().catch(() => null)]).then(([rows, meta]) => {
    if (sub && meta && meta.first_year && meta.last_year)
      sub.textContent = `${day}, across ${meta.last_year - meta.first_year + 1} years of NOAA records`;
    if (!rows.length) return message(`No recorded storm events began on ${day}.`);
    list.replaceChildren(...rows.slice(0, LIMIT).map(row));
  }).catch(() => message("Couldn't load storm history right now."));
})();
