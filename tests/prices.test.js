// Price Check's arithmetic and search (app/static/prices.js), run against the committed data:
//     node --test tests/
// The method these check is docs/PRICE_CHECK.md.
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const W = require("../app/static/prices.js");
const data = require("../data_sources/procedure-prices.json");

const byId = Object.fromEntries(data.procedures.map((p) => [p.id, p]));
const ids = (query) => W.search(data, query).map((p) => p.id);
const close = (a, b) => assert.ok(Math.abs(a - b) < 1e-6, `${a} != ${b}`);

test("every procedure has an estimate in every setting it offers", () => {
  for (const p of data.procedures) {
    const offered = W.settings(p);
    assert.ok(offered.length, `${p.id}: no setting`);
    for (const setting of offered) {
      for (const anesthesia of [true, false]) {
        const e = W.estimate(data, p, { setting, anesthesia });
        const t = e.total, where = `${p.id} ${setting}`;
        assert.equal(e.setting, setting, where);
        assert.ok(t.medicare > 0 && Number.isFinite(t.high), where);
        assert.ok(t.low <= t.mid && t.mid <= t.high, `${where}: low <= best guess <= high`);
        for (const k of ["medicare", "low", "mid", "high"]) close(e.parts.reduce((sum, x) => sum + x[k], 0), t[k]);
        for (const x of e.parts) {
          const m = data.multipliers[x.key];
          close(x.low, x.medicare * m.low); close(x.mid, x.medicare * m.mid); close(x.high, x.medicare * m.high);
        }
      }
    }
  }
});

test("the parts of the bill follow the setting", () => {
  const p = byId["upper-eyelid-surgery"], keys = (o) => W.estimate(data, p, o).parts.map((x) => x.key);
  assert.deepEqual(keys({ setting: "center" }), ["doctor", "center", "anesthesia"]);
  assert.deepEqual(keys({ setting: "center", anesthesia: false }), ["doctor", "center"]);
  assert.deepEqual(keys({ setting: "hospital" }), ["doctor", "hospital", "anesthesia"]);
  const office = W.estimate(data, byId["skin-biopsy"], {});
  assert.equal(office.setting, "office");
  assert.deepEqual(office.parts.map((x) => x.key), ["doctor"]);
  assert.equal(office.parts[0].medicare, byId["skin-biopsy"].doctor.office[1]);
});

test("a setting that isn't offered falls back to the usual one", () => {
  const p = byId["skin-biopsy"];
  assert.equal(W.estimate(data, p, { setting: "hospital" }).setting, W.settings(p)[0]);
});

test("the settings rules", () => {
  const fee = (n, allowed) => [n, allowed, allowed * 3];
  const make = (office, facility, extra) => Object.assign({ doctor: { office, facility }, center: 1000, hospital: null, states: {} }, extra);
  // mostly office, and few enough facility cases that those aren't offered
  assert.deepEqual(W.settings(make(fee(950, 100), fee(50, 80))), ["office"]);
  // an office average far below the facility fee is partial bills, not the procedure: not offered
  assert.deepEqual(W.settings(make(fee(5000, 8), fee(3000, 600))), ["center", "hospital"]);
  // both common: the place most cases happen comes first
  assert.deepEqual(W.settings(make(fee(700, 300), fee(300, 250))), ["office", "center", "hospital"]);
  assert.deepEqual(W.settings(make(fee(300, 300), fee(700, 250))), ["center", "hospital", "office"]);
  // no surgery center rate: a hospital only when its own figure is published
  assert.deepEqual(W.settings(make(fee(300, 300), fee(700, 250), { center: null })), ["office"]);
  assert.deepEqual(W.settings(make(fee(300, 300), fee(700, 250), { center: null, hospital: fee(500, 2000) })), ["hospital", "office"]);
});

test("a missing hospital figure is estimated from the surgery center rate, and says so", () => {
  const p = data.procedures.find((x) => !x.hospital && x.center && W.settings(x).includes("hospital"));
  const e = W.estimate(data, p, { setting: "hospital", anesthesia: false });
  const hospital = e.parts.find((x) => x.key === "hospital");
  assert.ok(e.flags.hospitalEstimated && hospital.estimated);
  close(hospital.medicare, p.center * W.hospitalRatio(data));
  const published = data.procedures.find((x) => x.hospital && W.settings(x).includes("hospital"));
  assert.ok(!W.estimate(data, published, { setting: "hospital" }).flags.hospitalEstimated);
});

test("a state's own doctor's fee is used when published, the national one otherwise", () => {
  const p = byId["cataract-surgery"], state = Object.keys(p.states).find((s) => p.states[s].facility);
  const local = W.estimate(data, p, { state, setting: "center" });
  assert.equal(local.flags.state, state);
  assert.equal(local.parts[0].medicare, p.states[state].facility[1]);
  const none = W.estimate(data, p, { state: "Atlantis", setting: "center" });
  assert.ok(none.flags.stateMissing);
  assert.equal(none.parts[0].medicare, p.doctor.facility[1]);
});

test("rounding doesn't claim more precision than an estimate has", () => {
  assert.equal(W.round(83), 85);
  assert.equal(W.round(832), 830);
  assert.equal(W.round(3349), 3350);
  assert.equal(W.round(38649), 38600);
  assert.equal(W.round(5.18), 5);
  assert.equal(W.round(13.6), 14);
  assert.equal(W.round(0.2), 1);
});

test("searching a kind of doctor lists everything in their group", () => {
  for (const s of data.specialties) {
    const group = data.procedures.filter((p) => p.specialty === s.name).map((p) => p.id);
    for (const word of s.aka) {
      const found = ids(word);
      for (const id of group) assert.ok(found.includes(id), `"${word}" should find ${id}`);
    }
    assert.equal(W.specialtyFor(data, s.aka[0]).name, s.name);
  }
  const skin = data.procedures.filter((p) => p.specialty === "Skin" || (p.also || []).includes("Skin")).map((p) => p.id);
  assert.deepEqual(ids("dermatologist").sort(), skin.sort());
  assert.ok(skin.includes("ingrown-toenail"), "a podiatrist's procedure a dermatologist also does");
  assert.ok(ids("orthopedic surgeon").includes("bunion-surgery"));
  assert.equal(W.specialtyFor(data, "dermatologists").name, "Skin");
  assert.equal(W.specialtyFor(data, "cataract"), null);
});

test("search matches whole words or their beginnings, not letters inside other words", () => {
  assert.ok(!ids("urologist").includes("botox-migraine"), "urologist is not neurologist");
  assert.ok(ids("neurologist").includes("botox-migraine"));
  assert.ok(!ids("PT").includes("droopy-eyelid-repair"), "PT is not ptosis");
  assert.ok(ids("PT").includes("pt-exercise"));
  assert.ok(ids("eye").includes("upper-eyelid-surgery"), "three letters still match a word's beginning");
  assert.equal(ids("ENT").length, data.procedures.filter((p) => p.specialty === "Ear, nose and throat").length);
  assert.deepEqual(ids("cataracts").slice(0, 1), ["cataract-surgery"]);
  assert.ok(ids("scopy").includes("colonoscopy"));
  assert.deepEqual(ids("15823"), ["upper-eyelid-surgery"]);
  assert.deepEqual(ids("zzzz"), []);
  assert.equal(ids("").length, data.procedures.length);
});

test("every procedure's group names its kind of doctor", () => {
  const names = new Set(data.specialties.map((s) => s.name));
  for (const p of data.procedures) for (const s of [p.specialty].concat(p.also || [])) assert.ok(names.has(s), `${p.id}: ${s}`);
});

test("a scan is priced from the fee schedule: whole outside a hospital, reading plus the hospital's part inside", () => {
  const p = byId["mri-brain"];
  assert.deepEqual(W.settings(p).slice().sort(), ["hospital", "office"]);
  const center = W.estimate(data, p, { setting: "office", state: "Oregon" });
  assert.deepEqual(center.parts.map((x) => x.key), ["doctor"]);
  assert.equal(center.parts[0].medicare, p.schedule.global);
  assert.ok(p.schedule.global > p.doctor.office[1], "the whole scan costs more than the mixed average bill");
  assert.ok(center.flags.national && !center.flags.state && !center.flags.stateMissing);
  const hospital = W.estimate(data, p, { setting: "hospital" });
  assert.deepEqual(hospital.parts.map((x) => [x.key, x.medicare]), [["doctor", p.doctor.facility[1]], ["hospital", p.schedule.hospital]]);
  assert.ok(!hospital.flags.hospitalEstimated);
  assert.ok(hospital.total.mid > center.total.mid);
});

test("the fee schedule doesn't replace a hospital or surgery center figure CMS publishes", () => {
  const p = byId["heart-catheterization"];
  assert.ok(p.schedule && p.hospital && p.center);
  const e = W.estimate(data, p, { setting: "hospital", anesthesia: false });
  assert.equal(e.parts.find((x) => x.key === "hospital").medicare, p.hospital[1]);
  // no hospital rate in the schedule: the scan is priced outside a hospital only
  assert.deepEqual(W.settings(byId["screening-mammogram"]), ["office"]);
});

test("the schedule's price for a reading agrees with what Medicare paid doctors in facilities", () => {
  for (const p of data.procedures.filter((x) => x.schedule && x.doctor.facility && x.doctor.facility[0] > 10000)) {
    const ratio = p.schedule.professional / p.doctor.facility[1];
    assert.ok(ratio > 0.85 && ratio < 1.15, `${p.id}: ${p.schedule.professional} vs ${p.doctor.facility[1]}`);
  }
});

test("a retired code says so and names what to ask for", () => {
  for (const p of data.procedures.filter((x) => x.retired)) assert.ok(p.retired.ask && p.retired.note, p.id);
  assert.ok(byId["prostate-biopsy"].retired);
});
