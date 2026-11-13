# Concert timeline

The page is served at /concerts/ and linked from the main navigation.

Edit `_data/concerts.yml` to maintain the timeline. Replace its empty `[]` with a YAML list:

```yaml
- date: "2027-01-15"
  title: "Tour name"
  status: upcoming
  headliners: ["Artist"]
  openers: []
  venue: "Venue name"
  location: "City, State"
  companions: []
  notes: ""
```

These are example values, not an actual concert. Use quoted YYYY-MM-DD dates and one record per show. Status must be `upcoming` or `attended`. Upcoming shows sort soonest first; attended shows sort newest first. Change status after confirming attendance; a date passing does not claim you attended.

Use lists for headliners, openers, and companions. Unknown details render as “To be added”; use `["None"]` if there were definitely no openers. Notes are optional plain text. All concert text is HTML-escaped.

Review the names and details before merging: this page is public when deployed with the rest of the site. To preview, run `bundle install` and `bundle exec jekyll serve`, then visit the site's /concerts/ path.

When attendance is confirmed within a range but the exact day is unknown, use `date` for the first possible day (sorting only), add `date_end` for the last possible day, and add a plain-text `date_label` such as “March 8–9, 2026 · exact day unconfirmed”. The card displays this label instead of claiming attendance on the sorting date. Once the day is confirmed, set `date` to it and remove `date_end` and `date_label`.
