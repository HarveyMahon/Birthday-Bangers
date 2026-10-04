/*
 * Birthday Number One - shared logic for index.html and minimal.html.
 *
 * PRIVACY: the birthday never leaves this page. The only network requests are
 * for the bundled data files, made once when the page loads (before anyone
 * types anything). Nothing is stored: no cookies, no localStorage, and the
 * form never submits, so the date never appears in the URL.
 *
 * ELEMENT CONTRACT - each page provides elements with these ids; how they look
 * is entirely up to that page's CSS.
 *
 *   #lookup-form        <form> containing #birthday (input type=date) and a submit button
 *   #status             message area (role="status"), used for errors and notices
 *   #result             wrapper, hidden until a lookup succeeds; gets data-reveal="on"
 *                       each time a new result is shown (pages hook animations to it)
 *   #result-heading     filled with "On 7 March 1990" (focus moves here, tabindex=-1)
 *   #single, #album     one block per chart, each containing:
 *     #<chart>-title, #<chart>-artist, #<chart>-week,
 *     #<chart>-spotify, #<chart>-youtube   (<a> elements)
 *     #<chart>-joint     optional, shown only for a joint number 1
 *   #album-note         shown instead of #album when there was no albums chart yet
 *   #data-range         optional: filled with "Charts from ... to ..."
 *
 * The <html> element gets data-data="loading" | "ready" | "error".
 */
(() => {
  "use strict";

  const DAY = 86400000;
  const DATA_FILES = { singles: "data/singles.json", albums: "data/albums.json" };

  /* ---------------------------------------------------------------------
   * WHICH CHART WEEK CONTAINS A DATE?
   *
   * Each Wikipedia row gives the FIRST "week ending" date a record was at
   * number 1, and how many weeks it stayed there. We treat every chart as
   * covering the seven days up to and including its week-ending date:
   *
   *     chart dated Sat 13 Jan 1990  ->  Sun 7 Jan .. Sat 13 Jan 1990
   *
   * The weekday a chart week ends on has changed over the decades - most
   * recently in July 2015, when new releases moved to Fridays and charts
   * became dated on Thursdays. We never hard-code those weekdays; the dates
   * in the data already carry them. (Wikipedia's albums lists date charts by
   * their first day since 1999; scripts/build_data.py shifts those to the
   * week-ending convention, so both files mean the same thing.) Instead:
   *
   *   1. A row's weeks at number 1 are its first week-ending date plus
   *      7, 14, ... days, for as many weeks as Wikipedia lists.
   *   2. For a date, the relevant chart is the latest chart week that had
   *      started by then. When the convention changed and two charts were
   *      8-13 days apart, the in-between days get the earlier chart - it was
   *      still the latest number 1 on those days. Nothing falls in a hole.
   *   3. If several rows cover that chart (in the 1950s two versions of a
   *      song swapped places, so runs overlap), the row that reached number 1
   *      most recently wins. Rows with the same date are a joint number 1,
   *      and all of them are shown.
   *   4. After the newest chart we have, we say the data hasn't caught up
   *      yet rather than guess.
   *
   * scripts/build_data.py uses the same rules for its spot checks.
   * ------------------------------------------------------------------- */

  /** Days since 1970-01-01 for a calendar date (no time zones involved). */
  const dayNumber = (y, m, d) => Math.floor(Date.UTC(y, m - 1, d) / DAY);
  const isoToDay = (iso) => {
    const [y, m, d] = iso.split("-").map(Number);
    return dayNumber(y, m, d);
  };
  const todayNumber = () => {
    const t = new Date();
    return dayNumber(t.getFullYear(), t.getMonth() + 1, t.getDate());
  };

  function prepare(rows) {
    return rows
      .map((r) => ({ ...r, end: isoToDay(r.week_ending_date) }))
      .sort((a, b) => a.end - b.end)
      .map((r) => ({ ...r, start: r.end - 6, lastWeek: r.end + 7 * (r.weeks_at_number_one - 1) }));
  }

  /**
   * Returns { status: "found", entries, weekEnding, inGap } | { status: "before" } | { status: "after" }
   * entries has more than one item for a joint number 1. inGap is true for
   * the odd days between two charts at a convention change.
   */
  function lookup(rows, day) {
    if (!rows.length || day < rows[0].start) return { status: "before" };

    // Latest chart week that had started by `day` (rule 2).
    let chart = -Infinity;
    for (const r of rows) {
      if (r.start > day) break;                       // rows are sorted by date
      const k = Math.min(r.weeks_at_number_one - 1, Math.floor((day + 6 - r.end) / 7));
      chart = Math.max(chart, r.end + 7 * k);
    }
    if (day > maxCovered(rows)) return { status: "after" };

    // Rows covering that chart; the most recent arrival wins (rule 3).
    const covering = rows.filter((r) => r.end <= chart && chart <= r.lastWeek);
    const newest = Math.max(...covering.map((r) => r.end));
    return {
      status: "found",
      entries: covering.filter((r) => r.end === newest),
      weekEnding: chart,
      inGap: day > chart,
    };
  }

  const maxCovered = (rows) => rows.reduce((m, r) => Math.max(m, r.lastWeek), -Infinity);

  /* ------------------------------ formatting ------------------------------ */

  const dateFmt = new Intl.DateTimeFormat("en-GB", {
    day: "numeric", month: "long", year: "numeric", timeZone: "UTC",
  });
  const fmt = (day) => dateFmt.format(new Date(day * DAY));

  const spotifyUrl = (q) => "https://open.spotify.com/search/" + encodeURIComponent(q);
  const youtubeUrl = (q) => "https://www.youtube.com/results?search_query=" + encodeURIComponent(q);

  /* ------------------------------ page wiring ----------------------------- */

  const $ = (id) => document.getElementById(id);
  const root = document.documentElement;
  let charts = null;

  const dataReady = Promise.all(
    Object.entries(DATA_FILES).map(([name, url]) =>
      fetch(url, { cache: "no-cache", credentials: "omit", referrerPolicy: "no-referrer" })
        .then((r) => {
          if (!r.ok) throw new Error(url + " returned " + r.status);
          return r.json();
        })
        .then((rows) => [name, prepare(rows)])
    )
  ).then((pairs) => {
    charts = Object.fromEntries(pairs);
    root.dataset.data = "ready";
    const range = $("data-range");
    if (range && charts.singles.length) {
      const s = charts.singles;
      range.textContent =
        `Charts from the week ending ${fmt(s[0].end)} to the week ending ${fmt(maxCovered(s))}.`;
    }
  }).catch((err) => {
    root.dataset.data = "error";
    console.error(err);
    showStatus("The chart data couldn't be loaded, so lookups won't work right now. Reload the page to try again.");
  });

  root.dataset.data = "loading";

  function showStatus(message) {
    const el = $("status");
    el.textContent = message;
    el.hidden = !message;
  }

  function fillChart(prefix, found) {
    const { entries, weekEnding, inGap } = found;
    const [entry, ...others] = entries;
    const title = $(prefix + "-title");
    title.textContent = entry.title;
    title.dataset.length = entry.title.length > 34 ? "long" : "short";   // themes may resize long titles
    $(prefix + "-artist").textContent = entry.artist;
    $(prefix + "-week").textContent = inGap
      ? `Latest chart at the time: week ending ${fmt(weekEnding)}`
      : `Chart week ${fmt(weekEnding - 6)} to ${fmt(weekEnding)}`;
    const joint = $(prefix + "-joint");
    if (joint) {
      joint.hidden = !others.length;
      joint.textContent = others.length
        ? "Joint number 1 with " + others.map((o) => `${o.title} by ${o.artist}`).join(" and ")
        : "";
    }
    const q = `${entry.artist} ${entry.title}`;
    const spotify = $(prefix + "-spotify");
    const youtube = $(prefix + "-youtube");
    spotify.href = spotifyUrl(q);
    youtube.href = youtubeUrl(q);
    spotify.setAttribute("aria-label", `Search Spotify for ${entry.title} by ${entry.artist}`);
    youtube.setAttribute("aria-label", `Search YouTube for ${entry.title} by ${entry.artist}`);
  }

  function hideResult() {
    const result = $("result");
    result.hidden = true;
    result.removeAttribute("data-reveal");
  }

  async function onSubmit(event) {
    event.preventDefault();          // never submit: the date must not reach a URL
    const value = $("birthday").value;   // "YYYY-MM-DD" or ""
    hideResult();

    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
      showStatus("Enter your birthday as a full date - day, month and year.");
      $("birthday").focus();
      return;
    }
    await dataReady;
    if (!charts) return;

    const day = isoToDay(value);
    const today = todayNumber();
    if (day > today) {
      showStatus("That date hasn't happened yet. Pick a date up to today.");
      return;
    }

    const single = lookup(charts.singles, day);
    if (single.status === "before") {
      showStatus(`The first UK singles chart was for the week ending ${fmt(charts.singles[0].end)}, so there was no number 1 on ${fmt(day)} yet. Try a later date.`);
      return;
    }
    if (single.status === "after") {
      showStatus(`The chart for ${fmt(day)} hasn't been added yet. Our data currently runs to ${fmt(maxCovered(charts.singles))} and updates every week.`);
      return;
    }

    showStatus("");
    $("result-heading").textContent = `On ${fmt(day)}`;
    fillChart("single", single);

    const album = lookup(charts.albums, day);
    const albumEl = $("album");
    const note = $("album-note");
    if (album.status === "found") {
      fillChart("album", album);
      albumEl.hidden = false;
      note.hidden = true;
    } else {
      albumEl.hidden = true;
      note.hidden = false;
      note.textContent = album.status === "before"
        ? `There was no albums chart yet. The first one was for the week ending ${fmt(charts.albums[0].end)}.`
        : `The albums chart for this week hasn't been added yet.`;
    }

    const result = $("result");
    result.hidden = false;
    void result.offsetWidth;         // restart CSS animations for a new lookup
    result.dataset.reveal = "on";
    $("result-heading").focus({ preventScroll: true });
    result.scrollIntoView({
      behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
      block: "nearest",
    });
  }


  document.addEventListener("DOMContentLoaded", () => {
    $("lookup-form").addEventListener("submit", onSubmit);
    $("birthday").addEventListener("input", () => showStatus(""));
  });

  // Handy for checking lookups from the browser console; not used by the pages.
  window.__birthdayNumberOne = { lookup, prepare, isoToDay };
})();
