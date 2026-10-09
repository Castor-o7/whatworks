---
title: Storm Desk
summary: Explore 75 years of U.S. storm records (1.9 million events) by place, type, year and toll, right in your browser.
status: live
url: /storms
source: https://github.com/Castor-o7/whatworks
audience: Anyone curious how today's storms compare with the storms of the past
order: 1
---
The Storm Desk puts NOAA's Storm Events Database, every recorded U.S. storm event from 1950 through 2024,
into an explorer anyone can use.[^noaa] There's nothing to install and no account to make, and every chart
is computed in your own browser.

## How to use it

- **Filter** by event type, state, years and measure (events, deaths, injuries or damage). Every chart,
  the map and the event list update together.
- **Map:** *Locations* shows where events happened, grouped into a grid that sharpens as you zoom, down to
  single events you can click. *By state* shades every state, including events that have no coordinates.
- **Near me** centers the map on you. **Limit everything to the map area** then narrows the whole page
  to what's on the map. Your exact location never leaves your browser.
- **Share a view** by copying the address bar. Filters and map area are saved in the link.
- **Click any event** for NOAA's own account of what happened, the toll and where it began.

## Reading the data honestly

Storm records changed far more than storms did, and that matters most when comparing today with the past.
To compare two eras fairly, with damage adjusted for inflation, use [Then & Now](/storms/then-and-now).

[[storm-chart title="Recorded events per year" sub="All event types · NOAA Storm Events"]]

- **Record-keeping changed.** The database holds only tornadoes for 1950–1954, and only tornadoes,
  thunderstorm wind and hail from 1955 through 1992. The modern list arrives in 1996: 34 different event
  types that year, and about 50 a year lately.[^types] The jump in the chart above is mostly paperwork, not
  weather. Compare like with like: the same event type, in years when it was recorded the same way.
- **Damage is in nominal dollars.** A 1960 dollar isn't a 2024 dollar, and the figures aren't adjusted
  for inflation.
- **Deaths count only when they're attributed to a weather event,** and attribution practices vary across
  places and over time.
- **Not everything has a location.** About 61% of events have coordinates. Zone-reported hazards like heat,
  winter storms and drought don't, so the *By state* view is the complete one.

## How it's built

The database is pre-summarized into compressed files that your browser downloads and queries as you
explore, so the Storm Desk runs as a plain static website with no server. The code is open source.

[^noaa]: NOAA National Centers for Environmental Information, Storm Events Database. https://www.ncdc.noaa.gov/stormevents/
[^types]: Counted from the database itself: the number of distinct event types recorded in each year, 1950–2024.
