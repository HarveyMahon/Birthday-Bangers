"""Offline tests for the Wikipedia table parser and the lookup rules.

    python -m unittest discover tests
"""
import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_data as bd  # noqa: E402

# Mimics the structure of the real decade pages: one sortable table with
# year sub-heading rows, "re" rows, footnote markers, hidden sort keys,
# a rowspan, plus an unrelated table that must be ignored.
SINGLES_HTML = """
<table class="wikitable"><tr><th>Key</th></tr><tr><td>re</td></tr></table>
<table class="wikitable sortable">
<tr><th>No.</th><th>Artist</th><th>Single</th><th>Record label</th>
    <th>Week ending date<sup class="reference">[1]</sup></th><th>Weeks at number one</th></tr>
<tr><th colspan="6">1989</th></tr>
<tr><td>638</td><td>Band Aid II</td><td>"Do They Know It's Christmas?"</td><td>PWL</td>
    <td><span class="sortkey" style="display:none">1989-12-23</span>23 December 1989</td><td>3</td></tr>
<tr><th colspan="6">1990</th></tr>
<tr><td>639</td><td rowspan="2">New Kids on the Block</td><td>"Hangin' Tough"</td><td>CBS</td>
    <td>13&nbsp;January 1990</td><td>2<sup class="reference">[a]</sup></td></tr>
<tr><td>re</td><td>"Hangin' Tough" / "Step by Step"</td><td>CBS</td><td>27 January 1990</td><td>1</td></tr>
<tr><td>641</td><td>Sin&eacute;ad O'Connor</td><td>“Nothing Compares 2 U”</td><td>Ensign</td>
    <td>3 February 1990</td><td>4</td></tr>
</table>
"""

ALBUMS_HTML = """
<table class="wikitable">
<tr><th>Artist</th><th>Album</th><th>Record label</th>
    <th>Reached number one (for the week ending)</th><th>Weeks at number one</th></tr>
<tr><td>Frank Sinatra</td><td><i>Songs for Swingin' Lovers!</i></td><td>Capitol</td><td>28 July 1956</td><td>2</td></tr>
</table>
"""


class ParserTests(unittest.TestCase):
    def test_singles_rows(self):
        rows = bd.extract_entries(SINGLES_HTML, "singles")
        self.assertEqual([r["title"] for r in rows], [
            "Do They Know It's Christmas?",
            "Hangin' Tough",
            "Hangin' Tough / Step by Step",
            "Nothing Compares 2 U",
        ])
        self.assertEqual(rows[2]["artist"], "New Kids on the Block")   # from rowspan
        self.assertEqual(rows[1]["week_ending_date"], "1990-01-13")    # &nbsp; handled
        self.assertEqual(rows[1]["weeks_at_number_one"], 2)            # footnote stripped
        self.assertEqual(rows[0]["week_ending_date"], "1989-12-23")    # sort key ignored
        self.assertEqual(rows[3]["artist"], "Sinéad O'Connor")
        self.assertEqual(rows[3]["title"], "Nothing Compares 2 U")       # ‡ marker stripped

    def test_albums_rows(self):
        rows = bd.extract_entries(ALBUMS_HTML, "albums")
        self.assertEqual(rows, [{
            "artist": "Frank Sinatra", "title": "Songs for Swingin' Lovers!",
            "week_ending_date": "1956-07-28", "weeks_at_number_one": 2}])


class LookupTests(unittest.TestCase):
    def setUp(self):
        self.rows = bd.extract_entries(SINGLES_HTML, "singles")

    def find(self, y, m, d):
        found = bd.lookup(self.rows, dt.date(y, m, d))
        return " + ".join(e["title"] for e in found) or None

    def test_week_boundaries(self):
        # Band Aid II: weeks ending 23 Dec, 30 Dec, 6 Jan -> covers 17 Dec .. 6 Jan
        self.assertIsNone(self.find(1989, 12, 16))
        self.assertEqual(self.find(1989, 12, 17), "Do They Know It's Christmas?")
        self.assertEqual(self.find(1990, 1, 6), "Do They Know It's Christmas?")
        self.assertEqual(self.find(1990, 1, 7), "Hangin' Tough")
        # last entry: 3 Feb + 3 more weeks -> covered until 24 Feb
        self.assertEqual(self.find(1990, 2, 24), "Nothing Compares 2 U")
        self.assertIsNone(self.find(1990, 2, 25))

    def test_joint_and_overlapping_runs(self):
        rows = [
            {"artist": "A", "title": "Song A", "week_ending_date": "1957-01-05", "weeks_at_number_one": 4},
            {"artist": "B", "title": "Song B", "week_ending_date": "1957-01-12", "weeks_at_number_one": 1},
            {"artist": "C", "title": "Song C", "week_ending_date": "1957-02-02", "weeks_at_number_one": 2},
            {"artist": "D", "title": "Song D", "week_ending_date": "1957-02-02", "weeks_at_number_one": 1},
        ]
        # B arrives inside A's run and wins that week; A covers again afterwards
        self.assertEqual(" + ".join(e["title"] for e in bd.lookup(rows, dt.date(1957, 1, 10))), "Song B")
        self.assertEqual(" + ".join(e["title"] for e in bd.lookup(rows, dt.date(1957, 1, 17))), "Song A")
        # joint number 1, then C alone
        self.assertEqual(" + ".join(e["title"] for e in bd.lookup(rows, dt.date(1957, 2, 1))), "Song C + Song D")
        self.assertEqual(" + ".join(e["title"] for e in bd.lookup(rows, dt.date(1957, 2, 8))), "Song C")
        errors, warnings = bd.validate("singles", rows)
        self.assertFalse([e for e in errors if "GAP" in e or "duplicate" in e])
        self.assertTrue(any("joint" in w for w in warnings))

    def test_validation_flags_gap(self):
        rows = [dict(r) for r in self.rows]
        rows[3]["week_ending_date"] = "1990-02-24"   # three weeks missing
        errors, _ = bd.validate("singles", rows)
        self.assertTrue(any("GAP" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
