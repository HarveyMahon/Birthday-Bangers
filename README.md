# Birthday Number One

Enter a birthday, see the UK Official Singles Chart and Albums Chart number 1s for that week.

- `index.html` – retro vinyl design (the record slides out of its sleeve)
- `minimal.html` – clean, minimal design

Both pages share `js/app.js` and the files in `data/`. Each page only supplies markup and CSS.

## Privacy

The lookup runs entirely in the visitor's browser. The page loads its own data files once, when it opens, and makes no other requests. The birthday is never sent anywhere, never stored (no cookies, no localStorage, no analytics) and never put in the URL. The "Listen" links are plain Spotify and YouTube search links that contain only the artist and title.

## Repo layout

```
index.html                      vinyl page
minimal.html                    minimal page
css/vinyl.css, css/minimal.css  one stylesheet per design
js/app.js                       data loading, chart-week lookup, rendering (shared)
data/singles.json               built by the script below
data/albums.json
data/meta.json                  counts and date ranges, for reference
scripts/build_data.py           fetches and validates the data from Wikipedia
tests/test_build_data.py        offline tests for the parser and lookup rules
.github/workflows/update-data.yml   weekly data refresh
```

## 1. Build the data locally

Needs Python 3.10 or newer. No packages to install.

```
python scripts/build_data.py
```

On Windows you may need `py scripts\build_data.py`.

It fetches the 16 decade pages (8 for singles, 8 for albums) from Wikipedia's API, prints progress per page, then a summary for each chart: row count, earliest and latest dates, spot checks, and any gaps or overlaps.

- **Warnings** (small date shifts or overlaps) are expected around the times the chart's dating convention changed. The site handles them.
- **Errors** (a missing week, a failed spot check, too few rows) stop the script, and nothing is written. That usually means a Wikipedia page layout has changed. Run with `--check` to see the report without writing anything, or `--force` to write anyway.

Run the parser tests with `python -m unittest discover tests`.

To try the site locally, run `python -m http.server` in the repo folder and open http://localhost:8000. (Opening the HTML file directly won't work, because browsers block loading the data files from `file://`.)

## 2. Deploy to GitHub Pages

1. Create a repo and push everything, including the `data/` folder the script made.
2. In the repo, go to **Settings → Pages**, set **Source** to "Deploy from a branch", choose `main` and `/ (root)`, and save.
3. In **Settings → Actions → General → Workflow permissions**, choose "Read and write permissions" so the weekly job can commit new data.

The site will be at `https://<your-username>.github.io/<repo-name>/` (vinyl) and `.../minimal.html`.

## 3. Weekly updates

`.github/workflows/update-data.yml` runs every Saturday morning and can also be started by hand from the **Actions** tab ("Run workflow"). It runs the tests, rebuilds the data and commits it only if something changed. If validation fails, the job fails and the live data stays as it was. GitHub emails you about failed runs.

## How a birthday is matched to a chart week

Each chart covers the seven days up to and including its "week ending" date. A record's run starts six days before its first week-ending date and lasts until the next number 1's run begins. When the chart's dating convention changed and two charts were more than a week apart, the extra days count as the earlier chart, since it was still the latest number 1. The full rules are in the comment at the top of `js/app.js`.

## Credits

Chart data is compiled by the [Official Charts Company](https://www.officialcharts.com/) and taken from Wikipedia's [lists of UK singles chart number ones](https://en.wikipedia.org/wiki/Lists_of_UK_singles_chart_number_ones) and [lists of UK Albums Chart number ones](https://en.wikipedia.org/wiki/Lists_of_UK_Albums_Chart_number_ones), available under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). This site is not affiliated with either.
