# Insider Deal Tracker

Static dashboard for US insider deals:

- **Form 4** (insider trades) – All / Buys / Sells
- **Schedule 13D / 13G** (beneficial ownership)

Data is fetched from **SEC EDGAR** using a scheduled GitHub Action and
written into JSON under `data/`.

## How it works

- `scripts/fetch_insider_data.py`:
  - pulls recent daily index files from EDGAR
  - collects:
    - Form 4 ownership XML → per-transaction rows
    - Schedule 13D/13G text headers → filing-level rows
  - writes:
    - `data/form4_transactions.json`
    - `data/schedule_13d13g.json`

- `.github/workflows/update_insider_data.yml` runs this every 6 hours
  and commits updated JSON.

- `index.html` + `assets/*` render an interactive table UI
  that can be hosted via **GitHub Pages**.

## Setup

1. Clone this repo and update the `USER_AGENT` in `scripts/fetch_insider_data.py`
   with your name + contact email (per SEC guidelines).

2. Push to GitHub under your account as `insider_deals`.

3. In the repo settings:
   - Enable **GitHub Pages** (Source: `main` branch, root folder).

4. The dashboard will be served from:

   `https://rachit379.github.io/insider_deals/`

> This is an informal dashboard. Always verify filings directly on
> the SEC website before trading.
