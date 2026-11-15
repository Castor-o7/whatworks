#!/usr/bin/env python3
"""Download Medicare's public price data for the procedures in data_sources/procedures.toml and write
data_sources/procedure-prices.json, which the Price Check page (/prices/) is built from.

Usage: .venv/bin/python scripts/fetch_procedure_prices.py   (stdlib only; needs the network; ~1 min)

Four public sources from the Centers for Medicare & Medicaid Services (CMS), all keyed by billing code:

  doctor    "Medicare Physician & Other Practitioners - by Geography and Service" (data.cms.gov).
            Per code, nationally and per state, split by place of service (office / facility): how many
            services, the average amount the practitioners billed ("submitted charge", the sticker
            price) and the average amount Medicare allowed (what was actually paid in total, Medicare's
            share plus the patient's).
  hospital  "Medicare Outpatient Hospitals - by Geography and Service" (data.cms.gov). The hospital
            outpatient department's own fee for the same code: average billed and average allowed.
            CMS publishes it per code only for procedures paid as one bundle, so many codes have none.
  center    ASC Addendum AA (cms.gov, quarterly): the national rate Medicare pays an ambulatory surgery
            center for the code. Only the code and the rate are kept; the file's descriptors are not.
  schedule  The Physician Fee Schedule's national relative value file (cms.gov, quarterly). Used for two
            things. It lists the codes in force this year, so a code that has been retired is reported.
            And for scans and tests, which the schedule splits into a technical part (the machine and
            staff) and a professional part (the doctor's reading), it gives Medicare's national price for
            each part and for both together. The "doctor" averages above mix those three kinds of bill,
            so they understate what a whole scan costs; the schedule doesn't. Only codes and amounts are
            kept.

Nothing is estimated here: the file holds the published numbers, and app/static/prices.js turns them
into estimates with the multipliers in MULTIPLIERS below (docs/PRICE_CHECK.md explains the method).

The JSON is committed so the site builds offline; re-run this only to add procedures or to pick up a
new year of data (update the dataset ids and the ASC file below; data.cms.gov lists them).
"""
import csv
import datetime
import io
import json
import re
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIST = ROOT / "data_sources" / "procedures.toml"
OUT = ROOT / "data_sources" / "procedure-prices.json"

API = "https://data.cms.gov/data-api/v1/dataset/{}/data"
DOCTOR = dict(
    id="6fea9d79-0129-4e4c-b1b8-23cd86a4f435", year=2024,
    title="Medicare Physician & Other Practitioners - by Geography and Service",
    url="https://data.cms.gov/provider-summary-by-type-of-service/medicare-physician-other-practitioners/"
        "medicare-physician-other-practitioners-by-geography-and-service")
HOSPITAL = dict(
    id="04baec39-4a54-400e-824d-8e75251ceda9", year=2024,
    title="Medicare Outpatient Hospitals - by Geography and Service",
    url="https://data.cms.gov/provider-summary-by-type-of-service/medicare-outpatient-hospitals/"
        "medicare-outpatient-hospitals-by-geography-and-service")
CENTER = dict(
    file="https://www.cms.gov/files/zip/october-2026-asc-approved-hcpcs-code-payment-rates.zip",
    member=re.compile(r"ASC-AA\.csv$", re.I), period="October 2026",
    title="Ambulatory Surgical Center Payment: Addendum AA, ASC Covered Surgical Procedures",
    url="https://www.cms.gov/medicare/payment/prospective-payment-systems/ambulatory-surgical-center-asc/"
        "asc-payment-rates-addenda")

SCHEDULE = dict(
    file="https://www.cms.gov/files/zip/rvu26d.zip", member=re.compile(r"PPRRVU.*nonQPP\.csv$", re.I),
    period="October 2026", year=2026,
    title="Physician Fee Schedule: National Relative Value File (RVU26D)",
    url="https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files")

# What private insurers pay relative to Medicare, from published research: low, typical (mid), high.
# prices.js multiplies Medicare's amounts by these; the page cites each one.
#   quote   the source's own sentence for `mid`, copied exactly (never a paraphrase), with `page` for a PDF
#   range   in our words: where `low` and `high` come from, and anything a reader should know about them
# Check a figure against its source before changing it: a wrong multiplier moves every estimate.
RAND = ("RAND, Prices Paid to Hospitals by Private Health Plans: Findings from Round 5.1 of an Employer-Led "
        "Transparency Initiative (RR-A1144-2-v2, December 2024; 2022 prices)")
RAND_URL = "https://www.rand.org/pubs/research_reports/RRA1144-2-v2.html"
KFF = "KFF, How Much More Than Medicare Do Private Insurers Pay? A Review of the Literature (2020)"
KFF_URL = ("https://www.kff.org/medicare/issue-brief/how-much-more-than-medicare-do-private-insurers-pay-"
           "a-review-of-the-literature/")
MULTIPLIERS = {
    "doctor": dict(
        low=1.18, mid=1.43, high=1.79, source=KFF, url=KFF_URL,
        quote="For physician services, private insurance paid 143% of Medicare rates, on average, "
              "ranging from 118% to 179% of Medicare rates across studies.",
        range="The lowest and highest averages among the studies KFF reviewed."),
    "center": dict(
        low=1.0, mid=1.70, high=2.79, source=RAND, url=RAND_URL, page="page vii",
        quote="In 2022, prices for common outpatient services performed in ASCs averaged 170 percent of "
              "Medicare prices but, because of differences in Medicare payment models between ASCs and "
              "HOPDs, would have averaged approximately 107 percent of Medicare prices if paid using "
              "Medicare payment rates for HOPDs.",
        range="Our own assumption, not a published range: from Medicare's own surgery center price up to "
              "what hospital outpatient departments average (279%). RAND reports only state averages, "
              "which ran from below Medicare's price in Nevada and Arkansas to nearly 460% in New Jersey "
              "(page 20)."),
    "hospital": dict(
        low=1.50, mid=2.79, high=3.58, source=RAND, url=RAND_URL, page="page vii",
        quote="That year, relative prices for inpatient hospital facility services averaged 254 percent of "
              "Medicare prices, outpatient hospital facility services averaged 279 percent, and all "
              "associated professional services (inpatient plus outpatient) averaged 184 percent of what "
              "Medicare would have paid for the same services.",
        range="The best guess is RAND's figure; the range is from a different source, the outpatient "
              "hospital studies KFF reviewed in 2020, which ranged from 150% to 358% and averaged 264%. "
              "The 358% is a single study of Indiana, a state with few competing hospital systems.",
        range_source=KFF, range_url=KFF_URL),
    "anesthesia": dict(
        low=3.14, mid=3.14, high=3.97,
        source="Duffy, Ly, Adler and Trish, Commercial and Medicare Advantage Payment for Anesthesiology "
               "Services, American Journal of Managed Care 27(6), 2021 (2016 and 2017 claims from three "
               "large insurers)",
        url="https://www.ajmc.com/view/commercial-and-medicare-advantage-payment-for-anesthesiology-services",
        quote="Mean in-network commercial allowed amount CFs for anesthesiology services ($70) are 314% of "
              "the traditional Medicare rate ($22)",
        range="The study gives one average, so it is both the best guess and the low end. The high end "
              "(397%) is from the American Society of Anesthesiologists' 2025 survey of commercial fees, "
              "which we could not read ourselves; a billing company's summary of it reports a national "
              "average commercial rate of $82.43 a unit against Medicare's $20.77. Both sources compare "
              "rates per unit (\"CFs\", conversion factors), not whole bills.",
        range_source="Coronis Health, A New Year's Revelation: Survey Discloses Commercial Payment Patterns "
                     "(January 2026), summarizing the ASA survey",
        range_quote="In contrast, the 2024 national Medicare CF for anesthesia services was $20.77, or 25.2% "
                    "of the contemporaneous mean commercial CF reported.",
        range_url="https://coronishealth.com/blog/a-new-years-revelation-survey-discloses-commercial-"
                  "payment-patterns"),
}
MIN_SERVICES = 50  # a state's figure is kept only when it rests on at least this many services
MIN_NATIONAL = 1000  # a procedure Medicare paid for fewer times than this in the year is left out
NOT_STATES = {"Unknown", "Foreign Country", "Armed Forces Europe", "Armed Forces Pacific",
              "Armed Forces Central/South America"}
AGENT = {"User-Agent": "whatworks-fetch-prices/1.0"}


def get(url, params=None, tries=4):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=90) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt == tries - 1:
                raise SystemExit(f"Could not download {url}: {e}\nAre you offline? "
                                 f"{OUT.relative_to(ROOT)} was left unchanged.")
            time.sleep(2 * (attempt + 1))


def rows(dataset, **filters):
    params = {f"filter[{k}]": v for k, v in filters.items()}
    params["size"] = 1000
    return json.loads(get(API.format(dataset["id"]), params))


def money(text):
    return round(float(text), 2)


def doctor_rows(code):
    """-> (description, {"National"|state: {"office"|"facility": [services, allowed, billed]}})."""
    out, desc = {}, ""
    for r in rows(DOCTOR, HCPCS_Cd=code):
        desc = r["HCPCS_Desc"]
        place = {"O": "office", "F": "facility"}[r["Place_Of_Srvc"]]
        geo = "National" if r["Rndrng_Prvdr_Geo_Lvl"] == "National" else r["Rndrng_Prvdr_Geo_Desc"]
        out.setdefault(geo, {})[place] = [round(float(r["Tot_Srvcs"])), money(r["Avg_Mdcr_Alowd_Amt"]),
                                          money(r["Avg_Sbmtd_Chrg"])]
    return desc, out


def hospital_row(code):
    """The hospital outpatient department's fee for a code, nationally: [services, allowed, billed]."""
    found = [r for r in rows(HOSPITAL, HCPCS_Cd=code, Rndrng_Prvdr_Geo_Lvl="National")]
    if not found:
        return None
    r = max(found, key=lambda r: float(r["CAPC_Srvcs"]))
    return [round(float(r["CAPC_Srvcs"])), money(r["Avg_Mdcr_Alowd_Amt"]), money(r["Avg_Tot_Sbmtd_Chrgs"])]


def center_rates():
    """{code: rate} from ASC Addendum AA: codes with a payment rate of their own (packaged ones have none)."""
    archive = zipfile.ZipFile(io.BytesIO(get(CENTER["file"])))
    name = next((n for n in archive.namelist() if CENTER["member"].search(n)), None)
    if not name:
        raise SystemExit(f"No Addendum AA csv inside {CENTER['file']}: {archive.namelist()}")
    rates = {}
    for line in csv.reader(io.StringIO(archive.read(name).decode("latin-1"))):
        if len(line) < 7 or not re.fullmatch(r"[0-9A-Z]{5}", line[0].strip()):
            continue
        rate = re.sub(r"[$,\s]", "", line[-1])
        if re.fullmatch(r"[0-9]+(\.[0-9]+)?", rate) and float(rate) > 0:
            rates[line[0].strip()] = float(rate)
    if len(rates) < 1000:
        raise SystemExit(f"Only {len(rates)} rates read from {name}; the file's layout may have changed")
    return rates


def schedule_rates():
    """{code: None | {global, professional, technical, hospital}} from the fee schedule's relative value
    file: every code Medicare pays under the schedule this year. A code the schedule splits into a
    technical part (modifier TC) and a professional part (modifier 26) gets Medicare's national price, in
    dollars, for both together when done outside a hospital (`global`), and for each part. `hospital` is
    what Medicare pays a hospital outpatient department for the technical part, where the file carries it:
    the file holds that amount, as relative values, for the scans whose technical payment the law caps at
    the hospital rate (the file's documentation: "the physician fee schedule amount is compared to the
    OPPS payment amount and the lower amount is used"). Price = relative value units x conversion factor,
    before the adjustment for local costs."""
    archive = zipfile.ZipFile(io.BytesIO(get(SCHEDULE["file"])))
    name = next((n for n in archive.namelist() if SCHEDULE["member"].search(n)), None)
    if not name:
        raise SystemExit(f"No relative value csv inside {SCHEDULE['file']}: {archive.namelist()}")
    lines = list(csv.reader(io.StringIO(archive.read(name).decode("latin-1"))))
    head = next((i for i, r in enumerate(lines) if r and r[0].strip() == "HCPCS"), None)
    top = [" ".join(lines[i][c].strip() for i in range(head - 4, head + 1)).split() for c in range(len(lines[head]))] \
        if head and head >= 4 else []
    want = {11: ["NON-FACILITY", "TOTAL"], 13: ["PCTC", "IND"], 25: ["CONV", "FACTOR"], 29: ["NON-FACILITY", "PE", "USED",
            "FOR", "OPPS", "PAYMENT", "AMOUNT"], 31: ["MP", "USED", "FOR", "OPPS", "PAYMENT", "AMOUNT"]}
    if not top or any(top[c] != words for c, words in want.items()):
        raise SystemExit(f"{name}: the columns aren't where they were; check the file's layout before trusting it")
    by_code = {}
    for r in lines[head + 1:]:
        if len(r) > 31 and re.fullmatch(r"[0-9A-Z]{5}", r[0].strip()):
            by_code.setdefault(r[0].strip(), {})[r[1].strip()] = r
    if len(by_code) < 5000:
        raise SystemExit(f"Only {len(by_code)} codes read from {name}; the file's layout may have changed")

    def price(r, *columns):
        return round(sum(float(r[c]) for c in columns) * float(r[25]), 2)

    rates = {}
    for code, mods in by_code.items():
        rates[code] = None
        if {"", "26", "TC"} <= set(mods) and all(mods[m][3].strip() == "A" for m in ("", "26", "TC")):
            cap = price(mods["TC"], 29, 31)
            rates[code] = dict(professional=price(mods["26"], 11), technical=price(mods["TC"], 11),
                               hospital=cap if float(mods["TC"][29]) > 0 else None)
            rates[code]["global"] = price(mods[""], 11)
    return rates


def main():
    listed = tomllib.loads(LIST.read_text(encoding="utf-8"))
    wanted, specialties = listed["procedure"], listed.get("specialty", [])
    ids = [p["id"] for p in wanted]
    if dupes := {i for i in ids if ids.count(i) > 1}:
        raise SystemExit(f"{LIST.relative_to(ROOT)}: id used twice: {', '.join(sorted(dupes))}")
    known = {s["name"] for s in specialties}
    if unknown := sorted({s for p in wanted for s in [p["specialty"], *p.get("also", [])]} - known):
        raise SystemExit(f"{LIST.relative_to(ROOT)}: no [[specialty]] entry named: {', '.join(unknown)}")
    print(f"Reading surgery center rates ({CENTER['period']})...")
    centers = center_rates()
    print(f"Reading the physician fee schedule ({SCHEDULE['period']})...")
    schedule = schedule_rates()
    procedures, states, problems = [], set(), []
    for p in wanted:
        desc, geo = doctor_rows(p["code"])
        national = geo.pop("National", None)
        if not national:
            problems.append(f"{p['id']}: code {p['code']} isn't in Medicare's {DOCTOR['year']} data; left out")
            continue
        if sum(v[0] for v in national.values()) < MIN_NATIONAL:
            problems.append(f"{p['id']}: code {p['code']} has under {MIN_NATIONAL} services nationally, too few "
                            "to estimate from; left out")
            continue
        entry = {k: p[k] for k in ("id", "name", "aka", "specialty", "also", "billed_by", "code", "about", "note", "note_source", "cosmetic",
                                  "retired")
                 if k in p}
        entry["medicare_description"] = desc
        entry["doctor"] = national
        entry["center"] = centers.get(p["code"])
        entry["hospital"] = hospital_row(p["code"])
        if p["code"] not in schedule:
            if "retired" not in p:
                problems.append(f"{p['id']}: code {p['code']} isn't in the {SCHEDULE['year']} fee schedule. It may have been "
                                "retired: find its replacement, and give the entry a `retired` note meanwhile")
        elif "retired" in p:
            problems.append(f"{p['id']}: has a `retired` note, but code {p['code']} is in the {SCHEDULE['year']} fee schedule")
        elif schedule[p["code"]]:
            entry["schedule"] = schedule[p["code"]]
        if p.get("anesthesia"):
            a_desc, a_geo = doctor_rows(p["anesthesia"])
            a = (a_geo.get("National") or {}).get("facility")
            if a:
                entry["anesthesia"] = dict(code=p["anesthesia"], medicare_description=a_desc, fee=a)
            else:
                problems.append(f"{p['id']}: anesthesia code {p['anesthesia']} has no facility data; left out")
        entry["states"] = {}
        for state, places in sorted(geo.items()):
            kept = {place: v for place, v in places.items() if v[0] >= MIN_SERVICES}
            if kept and state not in NOT_STATES:
                entry["states"][state] = kept
                states.add(state)
        procedures.append(entry)
        n = national
        print(f"  {p['code']}  {p['name'][:44]:44}  {desc[:60]}")
        print(f"         office {n.get('office', ['-'] * 3)[1]:>9}  facility {n.get('facility', ['-'] * 3)[1]:>9}"
              f"  center {entry['center'] or '-':>9}  hospital {(entry['hospital'] or ['-'] * 2)[1]:>9}"
              + (f"  anesthesia {entry['anesthesia']['fee'][1]} ({entry['anesthesia']['medicare_description'][:50]})"
                 if "anesthesia" in entry else "")
              + ("  schedule: whole {global}, reading {professional}, hospital's part {hospital}".format(**entry["schedule"])
                 if "schedule" in entry else ""))
    if len(procedures) < len(wanted) * 0.8:
        raise SystemExit(f"Only {len(procedures)} of {len(wanted)} procedures found; refusing to overwrite {OUT}")
    out = {
        "retrieved": datetime.date.today().isoformat(),
        "method": "Published Medicare figures only; nothing in this file is estimated. Each fee is "
                  "[services, average Medicare allowed amount, average billed amount] in dollars. A state's "
                  f"figure is kept when it rests on at least {MIN_SERVICES} services.",
        "sources": {"doctor": {k: v for k, v in DOCTOR.items() if k != "id"} | {"dataset": DOCTOR["id"]},
                    "hospital": {k: v for k, v in HOSPITAL.items() if k != "id"} | {"dataset": HOSPITAL["id"]},
                    "center": {k: v for k, v in CENTER.items() if k != "member"},
                    "schedule": {k: v for k, v in SCHEDULE.items() if k != "member"}},
        "multipliers": MULTIPLIERS,
        "states": sorted(states),
        "specialties": [{k: s[k] for k in ("name", "doctor", "doctors", "aka")} for s in specialties
                        if any(p["specialty"] == s["name"] for p in procedures)],
        "procedures": procedures,
    }
    head = {k: v for k, v in out.items() if k != "procedures"}
    text = json.dumps(head, indent=1, ensure_ascii=False)[:-2] + ',\n "procedures": [\n' + ",\n".join(
        "  " + json.dumps(p, ensure_ascii=False, separators=(",", ":")) for p in procedures) + "\n ]\n}\n"
    json.loads(text)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(OUT)
    print(f"Wrote {OUT.relative_to(ROOT)}: {len(procedures)} procedures, {len(states)} states and territories")
    for line in problems:
        print(f"  warning: {line}")


if __name__ == "__main__":
    sys.exit(main())
