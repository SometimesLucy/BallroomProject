# BallroomProject Memory

## Project Summary
Scrapes/analyzes o2cm.com ballroom competition scoresheet results. Goal: detect judge bias across many competitions.

## o2cm scoresheet3.asp HTML Structure
URL pattern: `https://results.o2cm.com/scoresheet3.asp?event=<code>&heatid=<id>`

Table layout (indices):
- **Table 0**: empty wrapper
- **Tables 1–4**: one per dance (Waltz / Tango / Foxtrot / Viennese Waltz)
  - Row 0: `['dance_name']` (single cell)
  - Row 1: `['', judge_id, judge_id, ..., '', '1', '1-2', ..., '1-6', 'P', '']`
  - Rows 2+: `['couple_num', place, place, ..., '', majority_counts, ..., final_place, '']`
- **Table 5**: summary table (W/T/F/V totals + final placement per couple)
- **Table 6**: responsive info block — Row 0 is one long flat row containing:
  `'' 'Couples' couple_num name ... '' '' '' 'Judges' judge_id name ... '' 'Scrutineer' '' name`

Judge IDs: 2-digit integers (e.g. 11–28). Majority columns use `'1'`, `'1-2'` etc. (contain hyphens or are single-digit). Couple numbers: 3-digit integers.

## Key Files
- `scoresheet_analysis.py` — main analysis script (requests + BeautifulSoup)
- `o2cm_Test_1.py` — early direct scraping test
- `Form_Testing.py` — Selenium stub for interactive pages

## Python Version
Python 3.8.5 — must use `from __future__ import annotations` for modern type hint syntax.

## Analysis Approach
Per-dance metrics per judge:
- **Deviation** = judge_placement − consensus_placement (consensus = panel mean; avg always ~0 by math)
- **MAD** = mean absolute deviation (lower = more consistent with panel)
- **Spearman ρ** = rank correlation with consensus ordering (1.0 = identical)

Cross-competition bias detection plan: pool (judge, couple) deviation records across competitions; look for systematic patterns.

Outlier judges on mit25 heat 40328530: Didi Von Deck (26, ρ≈0.07), David Wright (28, ρ≈0.31), Mariko Cantley (13, ρ≈0.45).
