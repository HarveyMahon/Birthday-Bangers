#!/usr/bin/env python3
"""
Build data/singles.json and data/albums.json from Wikipedia's
"List of UK singles chart number ones of the <decade>" and
"List of UK Albums Chart number ones of the <decade>" pages.

Standard library only - no pip install needed.

    python scripts/build_data.py            # fetch, validate, write
    python scripts/build_data.py --check    # fetch and validate, write nothing
    python scripts/build_data.py --force    # write even if validation finds errors

Exit codes: 0 = OK (files written or unchanged), 1 = validation errors
(nothing written unless --force), 2 = a page could not be fetched/parsed.
"""
if __name__ == "__main__":
    print("build_data.py: started - fetching UK number ones from Wikipedia...", flush=True)

import argparse
import datetime as dt
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

API = "https://en.wikipedia.org/w/api.php"
# Wikimedia asks every client to send a descriptive User-Agent.
USER_AGENT = "uk-birthday-number-one/1.0 (static GitHub Pages hobby site; data build script)"

FIRST_DECADE = 1950
CHARTS = {
    "singles": "List of UK singles chart number ones of the {decade}s",
    "albums": "List of UK Albums Chart number ones of the {decade}s",
}

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}
for _name, _num in list(MONTHS.items()):
    MONTHS[_name[:3]] = _num
MONTHS["sept"] = 9

DATE_RE = re.compile(r"(\d{1,2})\s+([A-Za-z]+)\.?,?\s+(\d{4})")
INT_RE = re.compile(r"\d+")


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def fetch_page_html(title: str) -> str | None:
    """Return the rendered HTML of a page, or None if the page doesn't exist."""
    params = {
        "action": "parse", "page": title, "prop": "text", "format": "json",
        "formatversion": "2", "redirects": "1", "disablelimitreport": "1",
        "disableeditsection": "1",
    }
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_err = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if "error" in payload:
                if payload["error"].get("code") == "missingtitle":
                    return None
                raise RuntimeError(payload["error"].get("info", "unknown API error"))
            return payload["parse"]["text"]
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code not in (429, 500, 502, 503, 504):
                break
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
        wait = 2 ** (attempt + 1)
        print(f"    retrying in {wait}s ({last_err})", flush=True)
        time.sleep(wait)
    raise RuntimeError(f"could not fetch '{title}': {last_err}")


# ---------------------------------------------------------------------------
# HTML table parsing
# ---------------------------------------------------------------------------

class TableParser(HTMLParser):
    """Collects every <table> as a list of rows of cells.

    Each cell is {"text", "rowspan", "colspan"}. Footnote markers
    (<sup class="reference">), hidden sort keys, <style> blocks and
    anything with display:none are dropped from the text.
    """

    VOID = {"br", "img", "hr", "meta", "link", "input", "wbr", "col"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []      # finished tables
        self.stack = []       # open tables: {"rows": [...], "row": None, "cell": None}
        self.skip_depth = 0   # >0 while inside content we ignore
        self.tag_stack = []   # (tag, started_skip)

    def _skip_this(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        style = (a.get("style") or "").replace(" ", "").lower()
        if tag in ("style", "script"):
            return True
        if tag == "sup" and "reference" in cls:
            return True
        if "sortkey" in cls or "display:none" in style:
            return True
        if "mw-ref" in cls or "noprint" in cls:
            return True
        return False

    def handle_starttag(self, tag, attrs):
        if tag in self.VOID:
            if tag == "br" and self.skip_depth == 0:
                self._text(" ")
            return
        skip = self._skip_this(tag, attrs)
        self.tag_stack.append((tag, skip))
        if skip:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag == "table":
            self.stack.append({"rows": [], "row": None, "cell": None})
        elif not self.stack:
            return
        elif tag == "tr":
            t = self.stack[-1]
            t["row"] = []
            t["rows"].append(t["row"])
        elif tag in ("td", "th"):
            t = self.stack[-1]
            if t["row"] is None:
                t["row"] = []
                t["rows"].append(t["row"])
            a = dict(attrs)
            t["cell"] = {
                "text": "",
                "rowspan": _span(a.get("rowspan")),
                "colspan": _span(a.get("colspan")),
                "header": tag == "th",
            }
            t["row"].append(t["cell"])

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        # pop to the matching open tag (tolerates sloppy HTML)
        while self.tag_stack:
            open_tag, skipped = self.tag_stack.pop()
            if skipped:
                self.skip_depth -= 1
            elif self.skip_depth == 0 and self.stack:
                if open_tag == "table":
                    self.tables.append(self.stack.pop()["rows"])
                elif open_tag in ("td", "th"):
                    self.stack[-1]["cell"] = None
                elif open_tag == "tr":
                    self.stack[-1]["row"] = None
            if open_tag == tag:
                break

    def handle_data(self, data):
        if not self.skip_depth:
            self._text(data)

    def _text(self, s):
        if self.stack and self.stack[-1]["cell"] is not None:
            self.stack[-1]["cell"]["text"] += s


def _span(v):
    try:
        return max(1, int(str(v).strip().split()[0]))
    except (TypeError, ValueError, IndexError):
        return 1


def clean(s: str) -> str:
    s = s.replace(" ", " ")
    s = re.sub(r"\[[^\]]{0,12}\]", "", s)   # leftover [a], [12], [nb 1]
    s = re.sub(r"\s+", " ", s).strip()
    return s


def expand_grid(rows):
    """Turn rows with rowspan/colspan into a rectangular list of text rows."""
    grid, carry = [], {}   # carry[col] = [remaining_rows, cell]
    for row in rows:
        out, col, cells = [], 0, list(row)
        while cells or col in carry:
            if col in carry:
                remaining, cell = carry[col]
                out.append(cell)
                if remaining <= 1:
                    del carry[col]
                else:
                    carry[col] = [remaining - 1, cell]
                col += 1
                continue
            cell = cells.pop(0)
            for _ in range(cell["colspan"]):
                out.append(cell)
                if cell["rowspan"] > 1:
                    carry[col] = [cell["rowspan"] - 1, cell]
                col += 1
        grid.append(out)
    return grid


def parse_date(text: str):
    m = DATE_RE.search(text)
    if not m:
        return None
    day, month, year = m.groups()
    month_num = MONTHS.get(month.lower())
    if not month_num:
        return None
    try:
        return dt.date(int(year), month_num, int(day))
    except ValueError:
        return None


def find_columns(header_cells, chart):
    names = [clean(c["text"]).lower() for c in header_cells]
    title_words = ("single", "song") if chart == "singles" else ("album",)
    cols = {}
    for i, n in enumerate(names):
        if "artist" in n and "artist" not in cols:
            cols["artist"] = i
        elif any(w in n for w in title_words) and "title" not in cols and "week" not in n:
            cols["title"] = i
        elif ("week ending" in n or "date" in n or "reached" in n) and "date" not in cols:
            cols["date"] = i
        elif "weeks" in n and "weeks" not in cols:
            cols["weeks"] = i
    if "title" not in cols:   # fall back to a generic "Title" column
        for i, n in enumerate(names):
            if n.startswith("title"):
                cols["title"] = i
    return cols if {"artist", "title", "date", "weeks"} <= cols.keys() else None


def extract_entries(html: str, chart: str):
    parser = TableParser()
    parser.feed(html)
    parser.close()
    entries = []
    for rows in parser.tables:
        grid = expand_grid(rows)
        cols, header_index = None, None
        for idx, row in enumerate(grid[:4]):          # header is in the first few rows
            cols = find_columns(row, chart)
            if cols:
                header_index = idx
                break
        if not cols:
            continue
        for row in grid[header_index + 1:]:
            if len(row) <= max(cols.values()):
                continue                               # year sub-heading or short row
            date = parse_date(clean(row[cols["date"]]["text"]))
            weeks_m = INT_RE.search(clean(row[cols["weeks"]]["text"]))
            artist = clean(row[cols["artist"]]["text"])
            title = clean(row[cols["title"]]["text"])
            if chart == "singles":
                # song titles are quoted on Wikipedia, e.g. "A" / "B" for double A-sides
                title = re.sub(r'["“”]', "", title).strip()
            if not date or not weeks_m or not artist or not title:
                continue
            if row[cols["artist"]] is row[cols["date"]]:
                continue                               # a full-width merged row
            entries.append({
                "artist": artist,
                "title": title,
                "week_ending_date": date.isoformat(),
                "weeks_at_number_one": int(weeks_m.group()),
            })
    return entries


# ---------------------------------------------------------------------------
# Lookup (mirrors js/app.js - see the comment there for the rules)
# ---------------------------------------------------------------------------

def lookup(entries, day: dt.date):
    """Return the entry at number 1 in the chart week containing `day`, or None."""
    found = None
    for e in entries:
        start = dt.date.fromisoformat(e["week_ending_date"]) - dt.timedelta(days=6)
        if start <= day:
            found = e
        else:
            break
    if found is entries[-1] and found is not None:
        if day > coverage_end(found):
            return None
    return found


def coverage_end(e):
    return dt.date.fromisoformat(e["week_ending_date"]) + dt.timedelta(
        days=7 * (e["weeks_at_number_one"] - 1))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

SPOT_CHECKS = {
    "singles": [
        ("first", None, "here in my heart"),
        ("date", dt.date(1991, 9, 1), "everything i do"),
        ("date", dt.date(1997, 10, 5), "candle in the wind"),
        ("date", dt.date(2017, 3, 1), "shape of you"),
    ],
    "albums": [
        ("first", None, "swingin"),
        ("date", dt.date(1967, 8, 1), "sgt. pepper"),
        ("date", dt.date(2011, 3, 1), "=21"),
    ],
}
MIN_ROWS = {"singles": 1400, "albums": 900}


def validate(chart, entries):
    """Return (errors, warnings) as lists of strings."""
    errors, warnings = [], []
    if len(entries) < MIN_ROWS[chart]:
        errors.append(f"only {len(entries)} rows (expected at least {MIN_ROWS[chart]})")

    for a, b in zip(entries, entries[1:]):
        a_date = dt.date.fromisoformat(a["week_ending_date"])
        b_date = dt.date.fromisoformat(b["week_ending_date"])
        expected = a_date + dt.timedelta(days=7 * a["weeks_at_number_one"])
        delta = (b_date - expected).days
        where = f"{a['week_ending_date']} '{a['title']}' -> {b['week_ending_date']} '{b['title']}'"
        if b_date <= a_date:
            errors.append(f"out of order / duplicate: {where}")
        elif delta >= 14:
            errors.append(f"GAP of {delta} days (at least one chart week missing): {where}")
        elif delta > 0:
            warnings.append(f"{delta}-day shift (chart-day convention change?): {where}")
        elif delta < 0:
            warnings.append(f"overlap of {-delta} days (weeks count disagrees with next entry): {where}")

    for kind, day, expected in SPOT_CHECKS[chart]:
        entry = entries[0] if kind == "first" else lookup(entries, day)
        got = entry["title"].lower() if entry else ""
        ok = got == expected[1:] if expected.startswith("=") else expected in got
        label = "first entry" if kind == "first" else day.isoformat()
        if not ok:
            errors.append(f"spot check failed for {label}: expected '{expected.lstrip('=')}', got '{got or 'nothing'}'")
        else:
            print(f"    spot check OK  {label}: {entry['title']}", flush=True)
    return errors, warnings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_chart(chart):
    print(f"\n[{chart}]", flush=True)
    this_decade = dt.date.today().year // 10 * 10
    all_entries = []
    for decade in range(FIRST_DECADE, this_decade + 10, 10):
        title = CHARTS[chart].format(decade=decade)
        print(f"  fetching {title} ...", end=" ", flush=True)
        html = fetch_page_html(title)
        if html is None:
            raise RuntimeError(f"page not found: {title}")
        rows = extract_entries(html, chart)
        print(f"{len(rows)} rows", flush=True)
        if not rows:
            raise RuntimeError(f"no table rows parsed from '{title}' - has the page layout changed?")
        all_entries.extend(rows)
        time.sleep(1)   # be polite to Wikipedia

    # Decade pages repeat the single/album that carried over from the previous
    # decade, so de-duplicate on (date, title) and keep the first one seen.
    seen, unique = set(), []
    for e in sorted(all_entries, key=lambda e: e["week_ending_date"]):
        key = (e["week_ending_date"], e["title"].lower())
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique


def write_if_changed(path: Path, obj) -> bool:
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="validate only, don't write files")
    ap.add_argument("--force", action="store_true", help="write files even if validation fails")
    args = ap.parse_args()

    results, any_errors = {}, False
    try:
        for chart in CHARTS:
            results[chart] = build_chart(chart)
    except RuntimeError as e:
        print(f"\nERROR: {e}\nNothing was written.", flush=True)
        return 2

    print("\n=== Summary ===", flush=True)
    meta = {"source": "Wikipedia lists of UK number ones (Official Charts Company data)"}
    for chart, entries in results.items():
        print(f"\n{chart}: {len(entries)} number ones", flush=True)
        print(f"  earliest week ending: {entries[0]['week_ending_date']}  ({entries[0]['title']})")
        print(f"  latest week ending:   {entries[-1]['week_ending_date']}  ({entries[-1]['title']})")
        print(f"  covered up to:        {coverage_end(entries[-1]).isoformat()}")
        errors, warnings = validate(chart, entries)
        for w in warnings:
            print(f"  warning: {w}")
        for e in errors:
            print(f"  ERROR:   {e}")
        print(f"  {len(errors)} error(s), {len(warnings)} warning(s)", flush=True)
        any_errors |= bool(errors)
        meta[chart] = {
            "count": len(entries),
            "first_week_ending": entries[0]["week_ending_date"],
            "covered_until": coverage_end(entries[-1]).isoformat(),
        }

    if args.check:
        print("\n--check given: nothing written.")
        return 1 if any_errors else 0
    if any_errors and not args.force:
        print("\nValidation failed: nothing written. Fix the parser, or rerun with --force to write anyway.")
        return 1

    DATA_DIR.mkdir(exist_ok=True)
    changed = [name for name, obj in (("singles.json", results["singles"]),
                                      ("albums.json", results["albums"]),
                                      ("meta.json", meta))
               if write_if_changed(DATA_DIR / name, obj)]
    print("\nWrote: " + ", ".join(changed) if changed else "\nData unchanged: nothing to write.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
