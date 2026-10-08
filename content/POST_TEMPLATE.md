---
title: Your headline here
date: 2026-10-08
section: tech
summary: One sentence that appears under the headline and on cards.
video: https://www.youtube.com/watch?v=VIDEO_ID
tags: tag-one, tag-two
draft: true
---
Copy this file into content/posts/ and rename it (the filename becomes the URL: /post/your-file-name/).
Then rebuild the site: .venv/bin/python scripts/build_site.py

- section: politics | economics | tech | science | storms | channel
- video: optional. Works with YouTube videos/shorts/live, youtu.be links, Twitch VODs
  (twitch.tv/videos/123), and Twitch clips (clips.twitch.tv/... or twitch.tv/name/clip/...).
- draft: true hides the post. Delete that line to publish.

Write the body in Markdown. Link to other pages from the site root, e.g. [Storm Desk](/storms) or
[a story](/post/other-file-name); the build adds the /whatworks base path for you.

To drop in a live chart from the storm database (drawn in the reader's browser):

[[storm-chart event_type="Tornado" state="Oklahoma"]]
[[storm-chart chart="types" metric="damage" state="Texas" year_from="2000"]]

Options: chart = years (default) | types | states | months
         metric = events | deaths | injuries | damage
         event_type, state, year_from, year_to, title, sub, limit
(Narrative search isn't available on the static site, so there is no q option.)
