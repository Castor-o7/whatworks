# Price Check (`/prices/`)

Search a medical procedure or a kind of doctor, see a best guess of the total price. Static like the rest of the site: one
JSON file of published Medicare figures, and the estimate is computed in the reader's browser.

```
data_sources/procedures.toml  --scripts/fetch_procedure_prices.py-->  data_sources/procedure-prices.json  (committed)
data_sources/procedure-prices.json  --scripts/build_site.py-->  _site/prices/index.html + _site/prices/data.json
app/static/prices.js   search, the estimate (WWPrices.estimate), the page
tests/prices.test.js   the arithmetic, the settings rules and the search:  node --test tests/
```

## What each number is, and isn't

| Number on the page | Where it comes from | What it doesn't mean |
|---|---|---|
| Medicare's price | CMS's published average *allowed amount* for the billing code in 2024 (surgery centers: the October 2026 rate). CMS defines it as "the sum of the amount Medicare pays, the deductible and coinsurance amounts that the beneficiary is responsible for paying, and any amounts that a third party is responsible for paying". | Not what Medicare alone pays, and not what a private patient pays. |
| Best guess | Each part of the bill × the published average of what private insurers pay relative to Medicare. | Not a quote, and not the reader's share: it is the total paid to the doctor and the facility. |
| Likely range | Each part × the low and high multiplier. For doctors and hospitals those are the lowest and highest averages across published studies; for surgery centers the range is **our assumption** (the page says so). | Not a guarantee: prices in one city or with one insurer can fall outside it. |
| List price | CMS's published average *submitted charge*: what providers billed Medicare. | Not what anyone is usually paid. |
| Cosmetic figure | Quoted from the source named beside it, in its own words. | Not derived from Medicare data. |

## Adding or changing a procedure

Edit `data_sources/procedures.toml` (the fields are explained at its top), then run
`.venv/bin/python scripts/fetch_procedure_prices.py` and rebuild the site. The script prints Medicare's own
description of every code: read it, because a wrong code produces a confident wrong price. A procedure
Medicare paid for fewer than 1,000 times in the year is left out (that is why vasectomy and IUD insertion
are missing: almost nobody on Medicare has them).

Every procedure's `specialty` must have a `[[specialty]]` entry at the top of the list, naming the kind of
doctor (`doctor`, `doctors`) and the words people search for (`aka`). The script refuses a group without
one. For a procedure that another group's doctors also do, give it `also = ["<group name>"]` (the bunion
entry, under Feet and ankles, has `also = ["Bones and joints"]`): searching either kind of doctor then
lists it. For a kind of doctor with no group of their own, add the word to the procedure's `aka` (the eye
exams have "optometrist").

Some entries are priced per unit, because that is how they are billed: physical therapy per 15 minutes,
allergy skin tests per allergen. Say so in the `name` and tell the reader in the `note` to multiply.

Notes in the list must not state dollar figures unless they come with a source (`cosmetic` is the field
for a sourced outside figure). A note that says what insurance or Medicare covers needs a `note_source`
(`{label, url}`, shown as a link after the note) and must say only what that page says. Give an entry
`billed_by` ("physical therapists") when the clinician isn't a physician: its estimate then says the
doctor multiplier was measured for physicians' services and not for them.

## The data file

`procedure-prices.json` holds only what CMS published; nothing in it is estimated. (The `schedule` prices
are CMS's relative value units multiplied by CMS's conversion factor, which is how the schedule states a
price.)

| Field | Contents |
|---|---|
| `sources`, `retrieved` | Which CMS files (`doctor`, `hospital`, `center`, `schedule`), which year, when fetched |
| `multipliers.{doctor,center,hospital,anesthesia}` | `low`, `mid`, `high`: what private insurers pay as a multiple of Medicare, with `source`, `url`, `quote` (the source's sentence for `mid`, **copied exactly**; `page` for a PDF) and `range` (our words: where `low` and `high` come from). `range_source`, `range_quote`, `range_url` when the range has a source of its own |
| `states` | The states and territories with at least one figure |
| `specialties[]` | `name`, `doctor` ("Dermatologist"), `doctors` ("dermatologists"), `aka` (search words; the first is what the page's button searches) |
| `procedures[]` | `id, name, aka, specialty, also?, billed_by?, code, about, note?, note_source?, cosmetic?, medicare_description` plus the figures below. `cosmetic` is `{fee, quote, excludes, source, url}`, with `quote` and `excludes` in the source's exact words |
| `doctor.office`, `doctor.facility` | `[services, average Medicare allowed amount, average billed amount]`, national |
| `states.<State>.office` / `.facility` | The same triple for a state, kept only when it rests on 50 or more services |
| `center` | The national rate Medicare pays a surgery center (ASC Addendum AA), or null |
| `hospital` | `[services, allowed, billed]` for a hospital outpatient department, or null (CMS reports it per code only for procedures paid as one bundle) |
| `schedule` | For a scan or test the fee schedule splits in two: `{global, professional, technical, hospital}` in dollars, national, from the relative value file (units × conversion factor, before the local adjustment). `global` is the whole scan with its reading, outside a hospital; `hospital` is the hospital outpatient rate for the technical part, or null when the file doesn't carry one |
| `retired` | `{ask, note}` when the code is no longer in force (see below) |
| `anesthesia` | `{code, medicare_description, fee: [services, allowed, billed]}` when the list names an anesthesia code |

"Allowed amount" is what was actually paid in total: Medicare's share plus the patient's. The page calls
it "Medicare's price".

## The multipliers and their sources

Set in `MULTIPLIERS` in `scripts/fetch_procedure_prices.py`. Each was read in its source on 2026-11-15;
a `quote` must be the source's exact words. Check the source again before changing one.

| Part | low / mid / high | Source of `mid` | Where the range comes from |
|---|---|---|---|
| Doctor | 118% / 143% / 179% | KFF's 2020 review of studies | The same sentence: the lowest and highest study averages |
| Surgery center | 100% / 170% / 279% | RAND round 5.1 (2022 prices), page vii. 170% is relative to Medicare's *surgery center* rates, which is what we multiply; relative to hospital rates RAND puts it near 107% | **Our assumption**: Medicare's price up to the hospital average. RAND gives only state averages (below Medicare in Nevada and Arkansas, nearly 460% in New Jersey) |
| Hospital outpatient | 150% / 279% / 358% | RAND round 5.1, page vii | KFF's 2020 review (a different source from `mid`): average 264%; the 358% is one Indiana study |
| Anesthesia | 314% / 314% / 397% | Duffy and others, AJMC 2021 (2016–2017 claims, three insurers) | High end: the ASA's 2025 fee survey **as summarized by a billing company**; we could not read the survey itself |

The surgery center range stays our assumption: Josh decided on 2026-11-15 to keep it rather than use
RAND's state range (which one outlier state would stretch to 460%), on condition that the page is clear
about it. So the page says it in four places, and they must stay in step: the starred range and footnote
in an estimate's table, the "How we got this number" step for the surgery center, the "How we come up
with these numbers" section, and the Sources list.

An earlier draft used 289% for hospitals. That number is not in the RAND report; it says 279%.

## The estimate (`WWPrices.estimate` in `prices.js`)

1. **Settings.** Office is offered when at least 10% of Medicare's cases happen there and the office fee is
   at least 60% of the facility fee (a far lower office average comes from partial bills, not from doing
   the procedure in an office). Surgery center and hospital are offered when at least 10% of cases happen
   in facilities and a facility fee is known. The default is where most cases happen.
2. **Parts.** Office: the doctor's office fee. Surgery center: the doctor's facility fee + the center rate.
   Hospital: the doctor's facility fee + the hospital figure. Anesthesia is added in facilities when the
   procedure has an anesthesia code and the reader leaves the box ticked.
   **Scans and tests** (`schedule` present): the "office" setting is an imaging center, priced at
   `schedule.global`, national, instead of the office average. That average mixes bills for a whole
   scan with bills for the scan alone or the reading alone, so it understates the whole (brain MRI: $155
   average, $195 on the schedule). When the schedule carries the hospital's rate and CMS publishes no
   hospital or surgery center figure for the code, a hospital setting is offered: the doctor's facility
   fee (the reading; a state's own when published) + `schedule.hospital`. The schedule's price for a
   reading agrees with the facility averages within a few percent, which is the check that both describe
   the same thing (there is a test for it).
3. **A missing hospital figure** is estimated as the center rate × the median hospital-to-center ratio among
   the procedures that have both (about 1.85), and labelled "estimated".
4. **Medicare → private.** Each part × its multiplier: `mid` gives the best guess, `low` and `high` the
   likely range. Totals are sums of the parts. The page shows this arithmetic under "How we got this
   number", each step with its source.
5. **State.** The doctor's fee is the state's own when published, else national (the page says which).
   Facility and anesthesia fees are national.
6. **Rounding.** To $1 under $20, $5 under $100, $10 under $1,000, $50 under $10,000, else $100.

## Retired codes

Billing codes change every January. The fetch script warns when a procedure's code isn't in this year's
fee schedule. Medicare's figures for the old code are still the best available until a year of data
exists under the new ones, so the entry stays, with a `retired = {ask, note}` table in
`procedures.toml`: the page then says the code is retired, and "When you call" asks for the procedure
by name (`ask`) and which code will be billed, instead of quoting a dead code. Prostate biopsy (55700,
replaced in 2026 by 55705 to 55715) is the one such entry.

## Search and the price menu

`WWPrices.search` needs every word of the search to match the entry: the procedure's name, its `aka`, its
group's doctor words (and those of any group in its `also`), or its code and descriptions. A word matches
a text when one of the text's words starts with it (one or two letters must be the whole word, so "PT"
doesn't find "ptosis"); a name also matches inside a word for words of four letters or more. Searching a kind of
doctor therefore lists that doctor's whole group. With a search and no procedure chosen, the page shows a
price menu of the matches (`WWPrices.specialtyFor` gives the heading when the search names one kind of
doctor). Enter opens the menu, or the estimate when there is exactly one match.

## Known limits

- The anesthesia multipliers compare rates per unit of anesthesia, from 2016–2017 claims and a 2025
  survey, and are applied to Medicare's average anesthesia bill. CMS's documentation doesn't say what
  one "service" is for anesthesia codes; the averages (about $100 to $140 a service) fit one bill per
  provider per case, not one time unit. When an anesthesiologist supervises a nurse anesthetist, both
  bill, so a case's anesthesia total can be higher than the average bill.
- The research is national and some of it is old (KFF's review is from 2020; RAND's prices are 2022).
- The multipliers are national research averages applied to every procedure. Real ratios differ by
  service, market and insurer. The doctor multiplier comes from studies of physician services as a
  whole; it is also applied to therapists, physical therapists, chiropractors and optometrists, whose
  private rates relative to Medicare we have no separate source for.
- Medicare patients are mostly over 65, so procedures common in younger people rest on less data.
- Surgery center rates and the fee schedule prices used for scans are 2026; the physician and hospital
  averages are 2024.
- The hospital rate for a scan is read from the fee schedule file's imaging-cap columns (the file's
  documentation: "the physician fee schedule amount is compared to the OPPS payment amount and the lower
  amount is used"), not from the hospital rate table itself. It exists only for the scans that cap
  applies to: MRI, CT and the echocardiogram here, not the mammogram or the sleep study.
- CMS's hospital outpatient rate table (OPPS Addendum B) sits behind a license click-through, so it isn't
  fetched; hence step 3.
- Billing codes are CPT codes (American Medical Association). The page shows the code numbers and CMS's
  consumer descriptions from its public data files; names and explanations are our own.

## URLs and DOM

`/prices/?p=<id>&state=<State>&where=office|center|hospital&anesthesia=no` is an estimate;
`/prices/?q=<search>&state=<State>` is a price menu. The list (`nav.pc-list`) and the kind-of-doctor
buttons (`.pc-doctors a[data-q]`) are rendered at build time as links; `prices.js` fills the list's prices
and ranges in, filters it from `#pc-q`, and renders the estimate or the menu into `#pc-detail`. The
numbered citations in an estimate link to the Sources list in `prices.html` (`SOURCE_NUMBER` in
`prices.js` must match its order).
