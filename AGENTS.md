# AGENTS.md

"koiene" is a Python CLI that scrapes live NTNUI Koiene (Norwegian hiking cabin)
availability and prints JSON. Small repo: one CLI + a `koiene/` package. No tests,
no linter/CI config, no git repo.

## Run

Dependencies are pinned in `requirements.txt`. A uv-managed venv (Python 3.13)
already exists — use it, don't rely on `python` being on PATH:

```sh
.venv/bin/python koiene_cli.py --date 2026-08-18 --available-only
# reinstall deps if needed:
uv pip install -r requirements.txt
```

Output is JSON on stdout (use `| jq`). `--from X --to Y` is a range; `--date` is a
single day (default: today). Filters compose and run client-side after fetching.

## Architecture

- `koiene/client.py` — `KoieneClient` does all scraping. Two source hosts:
  `www.koiene.no` for day-by-day availability, `koiene.org.ntnu.no` for the static
  cabin matrix + detail pages. Both are live external sites; **the CLI needs
  network access and its "tests" are real requests**.
- `koiene/models.py` — dataclasses. Fields default to `0`/`""`/`None` meaning
  *unknown*, not "zero". Filters (e.g. `by_walking_time`) deliberately skip `0`.
- `koiene/filters.py` — pure list filters over `Cabin`.
- `__init__.py` re-exports the public API; import from `koiene`, not submodules.

## Gotchas

- `fetch_range` pages the overview in **7-day windows** because the source page
  only shows a week at a time. Keep that logic when touching availability fetches.
- `_enrich_prices` hardcodes a request date (`"2026-08-18"`); prices aren't
  date-dependent but the param is required. Don't assume it reflects the query date.
- Parsing is brittle HTML selector/regex scraping. Network/parse failures are
  swallowed (`except requests.RequestException: continue`, `if not x: return`),
  so a broken selector shows up as missing/zero fields, not an error.
- `--detail` makes one extra request per cabin; avoid it for broad queries.
- The matrix is cached per `KoieneClient` instance (`_matrix_cache`).
