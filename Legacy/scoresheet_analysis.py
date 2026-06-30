"""
scoresheet_analysis.py

Scrape an o2cm scoresheet final and summarize:
  - Each couple's placement from every judge, per dance
  - Each judge's relative markings vs. the panel consensus
  - Per-judge mean deviation and Spearman rank correlation with consensus
  - Cross-dance judge tendency summary

o2cm page structure (from reverse-engineering scoresheet3.asp):
  - Tables 0:   empty wrapper
  - Tables 1-4: one per dance (Waltz / Tango / Foxtrot / Viennese Waltz)
      Row 0: dance name (single cell)
      Row 1: header — ['', judge_id, judge_id, ..., '', '1','1-2',...,'P','']
      Rows 2+: ['couple_num', place, place, ..., '', maj, ...,'final_place','']
  - Table 5:   summary (W/T/F/V totals per couple)
  - Table 6:   responsive info block (couples + judges listed in all rows)

Long-term goal: feed results from many competitions into a judge-bias pipeline.

Usage:
    python scoresheet_analysis.py
    python scoresheet_analysis.py --url "https://results.o2cm.com/scoresheet3.asp?event=xxx&heatid=yyy"
"""

from __future__ import annotations

import re
import argparse
import statistics
from collections import defaultdict

import requests
from bs4 import BeautifulSoup

DEFAULT_URL = (
    "https://results.o2cm.com/scoresheet3.asp?event=mit25&heatid=40328530"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Connection": "keep-alive",
}

# Judge IDs are 2-digit integers on o2cm (e.g. 11–28); distinct from majority
# columns ("1", "1-2", ...) and couple numbers (3+ digits).
JUDGE_ID_RE = re.compile(r"^\d{2}$")
COUPLE_NUM_RE = re.compile(r"^\d{3,5}$")


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def fetch_soup(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


# ---------------------------------------------------------------------------
# Parsing — couples and judges
# ---------------------------------------------------------------------------

def parse_info_table(soup: BeautifulSoup) -> tuple[dict, dict]:
    """
    Extract couples and judges from the responsive info table (table index 6).

    That table's row 0 is one long flat row containing:
        '' 'Couples' couple_num name couple_num name ... '' '' ''
        'Judges' judge_id name judge_id name ... '' 'Scrutineer' '' name

    Returns:
        couples  {couple_num_str: display_name}
        judges   {judge_id_str:  full_name}
    """
    tables = soup.find_all("table")
    if len(tables) < 7:
        return {}, {}

    cells = [c.get_text(strip=True) for c in tables[6].find_all("tr")[0].find_all("td")]

    couples: dict[str, str] = {}
    judges: dict[str, str] = {}

    # Parse couples section (between 'Couples' and 'Judges')
    try:
        couple_start = cells.index("Couples") + 1
        judge_start = cells.index("Judges")
    except ValueError:
        couple_start, judge_start = 0, len(cells)

    i = couple_start
    while i < judge_start - 1:
        num, name = cells[i], cells[i + 1]
        if COUPLE_NUM_RE.match(num) and name:
            couples[num] = name
        i += 2

    # Parse judges section (after 'Judges', pairs of id + name until 'Scrutineer')
    i = judge_start + 1
    while i < len(cells) - 1:
        jid, name = cells[i], cells[i + 1]
        if jid == "Scrutineer":
            break
        if JUDGE_ID_RE.match(jid) and name:
            judges[jid] = name
        i += 2

    return couples, judges


# ---------------------------------------------------------------------------
# Parsing — dance tables
# ---------------------------------------------------------------------------

def parse_dance_tables(soup: BeautifulSoup) -> list[tuple[str, list[str], dict]]:
    """
    Parse all four dance result tables (table indices 1–4).

    Each dance table structure:
        Row 0: ['dance_name']
        Row 1: ['', judge_id, ..., '', '1', '1-2', ..., 'P', '']
        Row 2+: ['couple_num', place, ..., '', maj, ..., final_place, '']

    Returns list of (dance_name, judge_ids, results) where:
        judge_ids  — ordered list of judge ID strings
        results    — {couple_num: {judge_id: placement_int}}
    """
    all_tables = soup.find_all("table")
    dance_data = []

    # Dance tables are at indices 1, 2, 3, 4
    for table in all_tables[1:5]:
        rows = [row.find_all("td") for row in table.find_all("tr")]
        if len(rows) < 3:
            continue

        # Row 0 → dance name
        dance_name = rows[0][0].get_text(strip=True) if rows[0] else "Unknown"

        # Row 1 → headers: find which column indices hold judge IDs
        header_texts = [c.get_text(strip=True) for c in rows[1]]
        judge_col_indices = [i for i, h in enumerate(header_texts) if JUDGE_ID_RE.match(h)]
        judge_ids = [header_texts[i] for i in judge_col_indices]

        if not judge_ids:
            continue

        # Rows 2+ → couple data
        results: dict[str, dict[str, int]] = {}
        for row_cells in rows[2:]:
            texts = [c.get_text(strip=True) for c in row_cells]
            if not texts or not COUPLE_NUM_RE.match(texts[0]):
                continue
            couple_num = texts[0]
            placements: dict[str, int] = {}
            for col_idx, jid in zip(judge_col_indices, judge_ids):
                if col_idx < len(texts):
                    try:
                        placements[jid] = int(texts[col_idx])
                    except ValueError:
                        pass
            if placements:
                results[couple_num] = placements

        dance_data.append((dance_name, judge_ids, results))

    return dance_data


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------

def consensus_placements(results: dict) -> dict:
    """Mean placement per couple across all judges (lower = better)."""
    return {
        couple: statistics.mean(list(placements.values()))
        for couple, placements in results.items()
        if placements
    }


def judge_deviations(results: dict, consensus: dict) -> dict:
    """
    deviation[judge_id][couple_num] = judge_placement − consensus_placement

    Positive  → judge ranked couple lower than peers  (relatively harsh)
    Negative  → judge ranked couple higher than peers (relatively generous)
    """
    devs: dict[str, dict[str, float]] = defaultdict(dict)
    for couple, placements in results.items():
        for jid, placement in placements.items():
            if couple in consensus:
                devs[jid][couple] = placement - consensus[couple]
    return devs


def spearman_rho(judge_placements: dict, consensus: dict) -> float | None:
    """Spearman ρ between a judge's ordering and the panel consensus."""
    couples = [c for c in judge_placements if c in consensus]
    n = len(couples)
    if n < 2:
        return None
    d_sq = sum((judge_placements[c] - consensus[c]) ** 2 for c in couples)
    return round(1 - (6 * d_sq) / (n * (n**2 - 1)), 3)


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def _short(name: str, width: int) -> str:
    return name[:width].ljust(width)


def print_dance_summary(
    dance_name: str,
    judge_ids: list[str],
    results: dict,
    couples: dict,
    judges: dict,
) -> dict:
    """Print per-dance grid and deviation table. Returns structured data."""
    print(f"\n{'─' * 76}")
    print(f"  {dance_name.upper()}")
    print(f"{'─' * 76}")

    if not results:
        print("  (no data)")
        return {}

    consensus = consensus_placements(results)
    deviations = judge_deviations(results, consensus)

    # ── Placement grid ───────────────────────────────────────────────────────
    COL = 4
    NAME_W = 20

    header = (
        f"{'Couple':<{NAME_W}}"
        + "".join(f"{jid:>{COL}}" for jid in judge_ids)
        + f"  {'Consensus':>9}"
    )
    print(header)
    print("  " + "·" * (len(header) - 2))

    sorted_couples = sorted(results.keys(), key=lambda c: consensus.get(c, 99))
    for couple_num in sorted_couples:
        display = couples.get(couple_num, couple_num)
        row = _short(display, NAME_W)
        for jid in judge_ids:
            val = results[couple_num].get(jid, "–")
            row += f"{val:>{COL}}"
        row += f"  {consensus[couple_num]:>9.2f}"
        print(row)

    # ── Per-judge deviation table ────────────────────────────────────────────
    print(f"\n  Relative markings per judge  (dev = judge − consensus)")
    print(f"  Note: avg_dev is always ~0 by definition (deviations from a mean sum to 0).")
    print(f"  MAD = mean absolute deviation (lower → tighter with panel).")
    print(f"  ρ = Spearman rank correlation with consensus (1.0 = identical ordering).")
    print()
    print(f"  {'Judge':<32}  {'Avg dev':>8}  {'MAD':>6}  {'ρ':>6}  Couple deviations")
    print(f"  {'─' * 32}  {'─' * 8}  {'─' * 6}  {'─' * 6}  {'─' * 30}")

    judge_stats: dict[str, dict] = {}
    for jid in judge_ids:
        judge_name = judges.get(jid, f"Judge {jid}")
        devs = deviations.get(jid, {})
        if not devs:
            continue
        avg_dev = statistics.mean(devs.values())
        mad = statistics.mean(abs(v) for v in devs.values())
        rho = spearman_rho(
            {c: results[c][jid] for c in results if jid in results[c]},
            consensus,
        )
        label = f"{jid} – {judge_name}"
        # Sort couple deviations by magnitude (most divergent first)
        dev_parts = "  ".join(
            f"{_short(couples.get(c, c), 8).strip()}:{v:+.1f}"
            for c, v in sorted(devs.items(), key=lambda x: abs(x[1]), reverse=True)
        )
        print(f"  {_short(label, 32)}  {avg_dev:>+8.2f}  {mad:>6.2f}  {str(rho):>6}  {dev_parts}")
        judge_stats[jid] = {"avg_dev": avg_dev, "mad": mad, "spearman": rho, "devs": devs}

    return {
        "dance": dance_name,
        "consensus": consensus,
        "deviations": deviations,
        "judge_stats": judge_stats,
    }


def print_overall_summary(all_dance_data: list[dict], judges: dict, couples: dict) -> None:
    """Aggregate judge deviations across all dances and print summary."""
    judge_all_devs: dict[str, list[float]] = defaultdict(list)
    for d in all_dance_data:
        for jid, devs in d.get("deviations", {}).items():
            judge_all_devs[jid].extend(devs.values())

    if not judge_all_devs:
        return

    print(f"\n{'═' * 76}")
    print("  OVERALL JUDGE TENDENCIES  (aggregated across all dances)")
    print("  MAD = mean absolute deviation; ρ = avg Spearman vs consensus per dance")
    print(f"{'═' * 76}")
    print(f"  {'Judge':<35}  {'MAD':>6}  {'Avg ρ':>6}  Tendency")
    print(f"  {'─' * 35}  {'─' * 6}  {'─' * 6}  {'─' * 38}")

    for jid in sorted(judge_all_devs.keys(), key=lambda x: int(x)):
        devs = judge_all_devs[jid]
        avg = statistics.mean(devs)
        mad = statistics.mean(abs(v) for v in devs)
        label = f"{jid} – {judges.get(jid, f'Judge {jid}')}"
        # avg is always ~0 (mathematical identity); use MAD + ρ for tendency
        rhos = [
            d["judge_stats"].get(jid, {}).get("spearman")
            for d in all_dance_data
            if jid in d.get("judge_stats", {})
        ]
        avg_rho = statistics.mean(r for r in rhos if r is not None) if rhos else None
        if mad > 1.5 and (avg_rho is None or avg_rho < 0.6):
            note = "outlier — large deviations AND low rank agreement"
        elif mad > 1.5:
            note = "high spread (often differs in magnitude)"
        elif avg_rho is not None and avg_rho < 0.7:
            note = "reorders couples differently from peers"
        else:
            note = "consistent with panel consensus"
        avg_rho_str = f"{avg_rho:.3f}" if avg_rho is not None else "  N/A"
        print(f"  {_short(label, 35)}  {mad:>6.2f}  {avg_rho_str:>6}  {note}")

    # ── Per-couple cross-judge consistency ───────────────────────────────────
    print(f"\n  COUPLE SUMMARY — cross-dance consensus placements")
    print(f"  {'Couple':<25}  {'W':>4}  {'T':>4}  {'F':>4}  {'V':>4}  {'Avg':>6}")
    print(f"  {'─' * 25}  {'─' * 4}  {'─' * 4}  {'─' * 4}  {'─' * 4}  {'─' * 6}")

    # Gather all couple numbers across dances
    all_couples: set[str] = set()
    for d in all_dance_data:
        all_couples.update(d.get("consensus", {}).keys())

    for cnum in sorted(all_couples):
        cname = _short(couples.get(cnum, cnum), 25)
        vals = [d["consensus"].get(cnum) for d in all_dance_data]
        cells = [f"{v:>4.1f}" if v is not None else "   –" for v in vals]
        valid = [v for v in vals if v is not None]
        avg_str = f"{statistics.mean(valid):>6.2f}" if valid else "     –"
        print(f"  {cname}  {'  '.join(cells)}  {avg_str}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def analyze(url: str) -> None:
    print(f"Fetching: {url}\n")
    soup = fetch_soup(url)

    couples, judges = parse_info_table(soup)
    dance_data_list = parse_dance_tables(soup)

    # ── Header ───────────────────────────────────────────────────────────────
    title = soup.find("title")
    print(f"{'═' * 76}")
    print(f"  {title.get_text(strip=True) if title else 'o2cm Scoresheet'}")
    print(f"{'═' * 76}")

    print(f"\nCouples ({len(couples)}):")
    for num, name in sorted(couples.items()):
        print(f"  {num}: {name}")

    print(f"\nJudges ({len(judges)}):")
    for jid, name in sorted(judges.items(), key=lambda x: int(x[0])):
        print(f"  {jid}: {name}")

    if not dance_data_list:
        print("\n[WARNING] No dance tables found — inspect the page structure.")
        return

    # ── Per-dance analysis ───────────────────────────────────────────────────
    all_dance_data = []
    for dance_name, judge_ids, results in dance_data_list:
        data = print_dance_summary(dance_name, judge_ids, results, couples, judges)
        all_dance_data.append(data)

    # ── Cross-dance summary ──────────────────────────────────────────────────
    print_overall_summary(all_dance_data, judges, couples)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analyze an o2cm final scoresheet for judge bias."
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="Full scoresheet URL")
    args = parser.parse_args()
    analyze(args.url)
