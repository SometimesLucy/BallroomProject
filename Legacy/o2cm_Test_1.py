"""
Scraper for o2cm.com ballroom competition scoresheets.
Parses each dance table into a structured dictionary of results.

Usage:
    python scrape_o2cm.py

Dependencies:
    pip install requests beautifulsoup4
"""

import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass, field
from pprint import pprint


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DanceResult:
    """Results for a single dance."""
    dance: str                        # e.g. "Waltz"
    judges: list[str]                 # ordered list of judge codes, e.g. ["AA", "BB", ...]
    scores: dict[str, dict[str, str]] # {couple_code: {judge_code: placement}}

@dataclass
class HeatResults:
    """All results for a single heat/final."""
    url: str
    event: str
    heat_id: str
    dances: list[DanceResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Scraping logic
# ---------------------------------------------------------------------------

def scrape_scoresheet(url: str) -> HeatResults:
    """
    Fetch and parse an o2cm scoresheet page.

    Args:
        url: Full URL to the scoresheet, e.g.
             https://results.o2cm.com/scoresheet3.asp?event=mit26&heatid=40328530&...

    Returns:
        A HeatResults dataclass containing all parsed dance results.
    """
    # Parse event/heat from URL for metadata
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    event   = params.get("event",  ["unknown"])[0]
    heat_id = params.get("heatid", ["unknown"])[0]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    heat_results = HeatResults(url=url, event=event, heat_id=heat_id)

    # Each dance is rendered as a separate <table> on the page.
    # The dance name appears in a <td> or header row just before each table,
    # or as the first row inside the table — we handle both patterns.
    tables = soup.find_all("table")

    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue  # skip trivially empty tables

        # ---- Header row: first cell is dance name, remaining cells are judge codes ----
        header_cells = rows[0].find_all(["th", "td"])
        if not header_cells:
            continue

        dance_name = header_cells[0].get_text(strip=True)

        # Skip tables that don't look like score tables
        # (dance name should be non-empty and not purely numeric)
        if not dance_name or dance_name.isdigit():
            continue

        judges = [cell.get_text(strip=True) for cell in header_cells[1:] if cell.get_text(strip=True)]

        if not judges:
            continue

        # ---- Data rows: first cell is couple code, remaining are placements ----
        scores: dict[str, dict[str, str]] = {}

        for row in rows[1:]:
            cells = row.find_all(["th", "td"])
            if not cells:
                continue

            couple_code = cells[0].get_text(strip=True)
            if not couple_code:
                continue

            placements = [cell.get_text(strip=True) for cell in cells[1:]]

            # Map each judge to their placement for this couple
            couple_scores: dict[str, str] = {}
            for judge, placement in zip(judges, placements):
                couple_scores[judge] = placement

            scores[couple_code] = couple_scores

        if scores:  # only keep tables that yielded actual data
            heat_results.dances.append(
                DanceResult(dance=dance_name, judges=judges, scores=scores)
            )

    return heat_results


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def print_results(heat: HeatResults) -> None:
    """Pretty-print a HeatResults object to the console."""
    print(f"\n{'=' * 60}")
    print(f"  Event : {heat.event}")
    print(f"  Heat  : {heat.heat_id}")
    print(f"  URL   : {heat.url}")
    print(f"{'=' * 60}\n")

    for dance_result in heat.dances:
        print(f"  ── {dance_result.dance} ──")
        print(f"     Judges : {', '.join(dance_result.judges)}")
        print(f"     {'Couple':<10}", end="")
        for judge in dance_result.judges:
            print(f"  {judge:>4}", end="")
        print()

        for couple, judge_scores in sorted(dance_result.scores.items()):
            print(f"     {couple:<10}", end="")
            for judge in dance_result.judges:
                placement = judge_scores.get(judge, "—")
                print(f"  {placement:>4}", end="")
            print()
        print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    URL = (
        "https://results.o2cm.com/scoresheet3.asp"
        "?event=mit26&heatid=40328530&bclr=#FFFFFF&tclr=#000000"
    )

    print(f"Fetching: {URL}")
    results = scrape_scoresheet(URL)

    if not results.dances:
        print("No dance tables found. The page structure may have changed.")
    else:
        print_results(results)

        # The HeatResults object is ready for further analysis.
        # Example: access scores for a specific dance and couple:
        #
        #   waltz = next(d for d in results.dances if d.dance == "Waltz")
        #   print(waltz.scores["123"])   # {"AA": "1", "BB": "2", ...}
        #
        # Or iterate over all dances:
        #   for dance in results.dances:
        #       for couple, scores in dance.scores.items():
        #           ...

        print(f"\nParsed {len(results.dances)} dance(s) successfully.")
        pprint({d.dance: list(d.scores.keys()) for d in results.dances})