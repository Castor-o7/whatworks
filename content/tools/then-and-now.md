---
title: Then & Now
summary: Are storms getting worse, or are we counting more? Compare two eras of U.S. storm records fairly, with damage in today's dollars and the record's blind spots spelled out.
status: live
url: /storms/then-and-now
source: https://github.com/Castor-o7/whatworks
audience: Anyone weighing today's storms against the storms of yore
order: 2
---
Then & Now sets two spans of years side by side in NOAA's Storm Events Database[^noaa] and compares them only
where a comparison is fair. It's part of the [Storm Desk](/storms), and like the rest of it, it runs entirely in
your browser.

## How to use it

- **Pick two eras.** Set *Then* and *Now* with the year boxes, or start from a preset: 1955–1974 vs 2005–2024 (the
  default), 1975–1994 vs 2005–2024, or 1996–2005 vs 2015–2024. The eras can be different lengths; every number is a
  yearly average, so they still line up.
- **Choose a measure:** recorded events, deaths, injuries or damage. For damage, choose *2024 dollars* (adjusted for
  inflation, the default) or *as reported*.
- **Narrow to a state** if you like. The comparison, the tornado lens and the caveats all follow it.
- **Read down the page.** *The comparison* shows each event type's yearly average then and now as a pair of dots,
  with the change in percent (switch to the table for exact numbers). *The tornado lens* splits recorded tornado
  segments into weak (F/EF0–1) and strong (F/EF2 and up). *Can't be compared yet* lists the event types left out, with the year each
  began being recorded every year. *What the record can't tell us* names the breaks in the record for the eras you chose.
- **Share a comparison** by copying the address bar; the eras, state and measure are saved in the link.

## Reading it honestly

The page is built on a few rules, because how storms were recorded changed a great deal over these years. For
tornadoes, NOAA's Storm Prediction Center says the rise in reports "doesn't mean that actual tornado occurrence has
gone up."[^spc-faq]

- **Only what was recorded in both eras.** An event type is compared only if NOAA recorded it in every year of both
  eras, judged nationally. Before 1993 the database holds only tornadoes, thunderstorm wind and hail, so for
  1955–1974 vs 2005–2024 those three are the whole comparison, and more than 30 types recorded every year lately
  (heat, flash flood and winter storm among them) wait under *Can't be compared yet*.[^types] The same goes for
  deaths, injuries and damage: a toll counts for an era only if the records hold it from the era's first year
  (thunderstorm wind deaths start in 1983, hail and thunderstorm wind damage in 1993).[^types]
- **Recorded every year isn't the same as like with like.** The event types themselves changed after 1996: heat,
  for one, is recorded as both *Heat* and *Excessive Heat*, and *Excessive Heat* appears every year only from
  2007.[^types] When a compared type has a related type that isn't compared, the page says how much the related
  type holds in each era.
- **Recorded events, not storms.** A rise in reports isn't by itself a rise in storms. Tornadoes are recorded once
  per county a track crosses, so the counts are "county-segments of tornado tracks," not tornadoes.[^spc-faq] NOAA's Storm Prediction Center
  notes that tornado reports "increased dramatically in the 1990s" as the National Weather Service installed its
  Doppler radar network and began training storm spotters.[^spc-reports] The tornado lens splits weak (F/EF0–1) from strong
  (F/EF2 and up) tornadoes: the Storm Prediction Center's FAQ says strong to violent tornadoes' records are "much better
  documented and more stable," and that looking at them, "very little overall change has occurred since the
  1950s."[^spc-faq] It also calls rating damage on the original F scale "largely a judgment call--quite inconsistent
  and arbitrary,"[^spc-faq] so even the strong group can shift with rating practice.
- **Damage before 1993 is a category, not an estimate.** Through 1992 the database holds only 6 to 10 distinct
  nonzero damage amounts a year, a ladder of round figures ($250, $2,500, $25,000 and on up by tens) that marks a
  category rather than a dollar estimate. The count rises to 15 in 1993, 50 in 1994, 198 in 1995 and 272 in
  1996.[^types] Comparing those with modern estimates is rough at best, and the page says so when an era reaches
  back that far.
- **Real dollars by default.** Each year's damage is converted to 2024 dollars with that year's average Consumer
  Price Index for All Urban Consumers (CPI-U), from the Bureau of Labor Statistics.[^cpi] That corrects for
  prices only: the page makes no adjustment for growth in population or in what there is to damage. Dollars *as
  reported* are shown without a percent change, since they are dollars of different years.
- **Small numbers get no percent.** When a type averages under one event, death or injury a year in the *Then*
  era, the change is shown as a per-year difference instead of a percent.
- **F and EF are not quite the same scale.** Tornadoes were rated on the Fujita scale until the Enhanced Fujita
  scale was implemented in the U.S. on 1 February 2007.[^ef] Historical tornadoes probably won't be re-rated: NOAA's
  tornado FAQ says that would mean examining tens of thousands of them one by one, and there are "neither plans nor
  money nor staffing" for the task.[^spc-faq] The page merges F and EF by number (F2 with EF2) and keeps unrated tornadoes apart.
- **Deaths and injuries are counted under the event they were recorded with**, so how each one was attributed
  shapes the totals.

## How it's built

Then & Now reads the same pre-summarized files as the Storm Desk, plus three small ones: tornado counts by
rating, the number of distinct damage values per year (so the categorical-damage break is computed from the data
itself), and annual CPI-U averages. The CPI figures come from FRED's copy of the BLS series CPIAUCNS; each year is the
average of its 12 monthly values, saved in the project so the numbers can be rebuilt offline. Every sentence on
the page is generated from those numbers or cites a source. Writers can drop a compact version into a story with
a `[[then-now]]` line.

[^noaa]: NOAA National Centers for Environmental Information, Storm Events Database, 1950–2024. https://www.ncdc.noaa.gov/stormevents/
[^types]: Counted from the database itself: the event types recorded in each year, and the distinct nonzero property-damage values in each year, 1950–2024.
[^spc-reports]: NOAA Storm Prediction Center, "The Enhanced Fujita Scale (EF Scale)." https://www.spc.noaa.gov/efscale/
[^cpi]: U.S. Bureau of Labor Statistics, Consumer Price Index for All Urban Consumers: All Items in U.S. City Average, not seasonally adjusted [CPIAUCNS], retrieved from FRED, Federal Reserve Bank of St. Louis. https://fred.stlouisfed.org/series/CPIAUCNS
[^ef]: NOAA Storm Prediction Center, "Enhanced F Scale for Tornado Damage." https://www.spc.noaa.gov/faq/tornado/ef-scale.html
[^spc-faq]: NOAA Storm Prediction Center, "The Online Tornado FAQ." https://www.spc.noaa.gov/faq/tornado/
