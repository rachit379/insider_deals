import os
import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests
from xml.etree import ElementTree as ET

# ----------------- config -----------------

# Be polite to SEC (2 req/sec)
REQUEST_DELAY_SEC = 0.5

# Form 4 lookback
FORM4_DAYS_BACK = 3        # last 3 calendar days
FORM4_MAX_FILINGS = 400    # safety cap

# Schedule 13D/13G lookback
SCHED13_DAYS_BACK = 30     # last 30 days to ensure some data
SCHED13_MAX_FILINGS = 200

# IMPORTANT: put your real email here
SEC_HEADERS = {
    "User-Agent": "Rachit Aggarwal (insider_deals; contact: rachitagg406@gmail.com)",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}


# ----------------- daily index helpers -----------------

def quarter_for_month(m: int) -> int:
    return (m - 1) // 3 + 1


def fetch_daily_index(d: date) -> Optional[str]:
    """
    Fetch master.YYYYMMDD.idx for given date.
    Returns text, or None if index not found (e.g. weekend/holiday/403).
    """
    year = d.year
    q = quarter_for_month(d.month)
    yyyymmdd = d.strftime("%Y%m%d")
    url = f"https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{q}/master.{yyyymmdd}.idx"

    try:
        resp = requests.get(url, headers=SEC_HEADERS, timeout=30)
        time.sleep(REQUEST_DELAY_SEC)
    except Exception as e:
        print(f"Error fetching index for {d}: {e}")
        return None

    if resp.status_code != 200:
        print(f"No index for {d} (HTTP {resp.status_code})")
        return None

    return resp.text


def iter_daily_indexes(days_back: int):
    """
    Yield {"date": date, "text": index_text} for the last `days_back` days
    where an index exists.
    """
    today = date.today()
    for i in range(days_back):
        d = today - timedelta(days=i)
        text = fetch_daily_index(d)
        if text:
            yield {"date": d, "text": text}


def parse_idx_for_forms(text: str, predicate) -> List[Dict[str, Any]]:
    """
    Parse a master.idx text and return filings where predicate(form_type) is True.
    """
    lines = text.splitlines()
    start_idx = None

    for i, line in enumerate(lines):
        if line.startswith("CIK|Company Name|Form Type|Date Filed|File Name"):
            start_idx = i + 1
            break

    if start_idx is None:
        return []

    filings: List[Dict[str, Any]] = []

    for line in lines[start_idx:]:
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) < 5:
            continue

        cik, company, form, date_filed, file_name = parts[:5]
        form = form.strip()
        if not predicate(form):
            continue

        fd_raw = date_filed.strip()
        if len(fd_raw) == 8 and fd_raw.isdigit():
            filed_date = f"{fd_raw[0:4]}-{fd_raw[4:6]}-{fd_raw[6:8]}"
        else:
            filed_date = fd_raw

        file_name = file_name.strip().lstrip("/")
        filing_url = f"https://www.sec.gov/Archives/{file_name}"

        filings.append(
            {
                "cik": cik.strip(),
                "company_name": company.strip(),
                "form_type": form,
                "filed_date": filed_date,
                "raw_filed_date": fd_raw,
                "file_name": file_name,
                "filing_url": filing_url,
            }
        )

    return filings


# ----------------- Form 4 XML helpers -----------------

def extract_ownership_xml_from_txt(text: str) -> Optional[str]:
    """
    Extract the <ownershipDocument>...</ownershipDocument> XML block
    from inside a .txt Form 4 filing.

    Many Form 4 .txt filings embed the XML like:
      <XML>
        <?xml version="1.0"?>
        <ownershipDocument>...</ownershipDocument>
      </XML>
    """
    m = re.search(
        r"<ownershipDocument[\s\S]*?</ownershipDocument>",
        text,
        flags=re.IGNORECASE,
    )
    if not m:
        return None

    xml_body = m.group(0)

    # Look for XML declaration immediately before the ownershipDocument
    prefix = text[: m.start()]
    decl = re.search(r"<\?xml[^>]*\?>", prefix)
    if decl:
        return decl.group(0) + "\n" + xml_body

    # Otherwise, add a basic declaration
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_body


def _text_or_none(parent: Optional[ET.Element], path: str) -> Optional[str]:
    if parent is None:
        return None
    el = parent.find(path)
    if el is None or el.text is None:
        return None
    return el.text.strip()


def _to_float(s: Optional[str]) -> Optional[float]:
    if s is None:
        return None
    s = s.replace(",", "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_form4_xml_transactions(xml_text: str) -> List[Dict[str, Any]]:
    """
    Parse a Form 4 ownershipDocument XML into a list of flat transaction rows.
    Only Table I (non-derivative) is handled here.
    """
    root = ET.fromstring(xml_text)

    issuer = root.find("issuer")
    issuer_name = _text_or_none(issuer, "issuerName")
    issuer_cik = _text_or_none(issuer, "issuerCik")
    issuer_trading_symbol = _text_or_none(issuer, "issuerTradingSymbol")

    reporting_owners = root.findall("reportingOwner")
    if not reporting_owners:
        return []

    # Use first reporting owner
    ro = reporting_owners[0]
    ro_id = ro.find("reportingOwnerId")
    ro_rel = ro.find("reportingOwnerRelationship")

    owner_name = _text_or_none(ro_id, "rptOwnerName")
    owner_cik = _text_or_none(ro_id, "rptOwnerCik")
    is_director = _text_or_none(ro_rel, "isDirector") in ("1", "true", "True")
    is_officer = _text_or_none(ro_rel, "isOfficer") in ("1", "true", "True")
    is_ten_percent = _text_or_none(ro_rel, "isTenPercentOwner") in ("1", "true", "True")
    officer_title = _text_or_none(ro_rel, "officerTitle")

    non_deriv_table = root.find("nonDerivativeTable")
    if non_deriv_table is None:
        return []

    rows: List[Dict[str, Any]] = []

    for txn in non_deriv_table.findall("nonDerivativeTransaction"):
        security_title = _text_or_none(txn, "securityTitle/value")
        transaction_date = _text_or_none(txn, "transactionDate/value")
        transaction_code = _text_or_none(txn.find("transactionCoding"), "transactionCode")

        amounts = txn.find("transactionAmounts")
        txn_shares = _to_float(_text_or_none(amounts, "transactionShares/value"))
        txn_price = _to_float(_text_or_none(amounts, "transactionPricePerShare/value"))

        post_amounts = txn.find("postTransactionAmounts")
        shares_after = _to_float(
            _text_or_none(post_amounts, "sharesOwnedFollowingTransaction/value")
        )

        ownership_nature = txn.find("ownershipNature")
        direct_or_indirect = _text_or_none(ownership_nature, "directOrIndirectOwnership")

        rows.append(
            {
                "issuer_cik": issuer_cik,
                "issuer_name": issuer_name,
                "issuer_trading_symbol": issuer_trading_symbol,
                "owner_cik": owner_cik,
                "owner_name": owner_name,
                "owner_is_director": is_director,
                "owner_is_officer": is_officer,
                "owner_is_ten_percent": is_ten_percent,
                "owner_officer_title": officer_title,
                "security_title": security_title,
                "transaction_date": transaction_date,
                "transaction_code": transaction_code,
                "transaction_shares": txn_shares,
                "transaction_price": txn_price,
                "shares_owned_after": shares_after,
                "direct_or_indirect_ownership": direct_or_indirect,
            }
        )

    return rows


# ----------------- Form 4 collector -----------------

def collect_recent_form4_filings(days_back: int, max_filings: int) -> List[Dict[str, Any]]:
    """
    Use daily master index for the last N days and return a list of Form 4 filings.
    """
    filings: List[Dict[str, Any]] = []

    def is_form4(ft: str) -> bool:
        ft = ft.upper()
        return ft in ("4", "4/A")

    for d in iter_daily_indexes(days_back):
        day_filings = parse_idx_for_forms(d["text"], is_form4)
        filings.extend(day_filings)

    filings.sort(key=lambda f: (f["raw_filed_date"], f["file_name"]), reverse=True)
    return filings[:max_filings]


def collect_form4_transactions(days_back: int, max_filings: int) -> List[Dict[str, Any]]:
    """
    Fetch recent Form 4s and flatten into transaction rows.
    """
    filings = collect_recent_form4_filings(days_back, max_filings)
    print(f"Found {len(filings)} Form 4 filings in the last {days_back} days.")

    all_rows: List[Dict[str, Any]] = []

    for f in filings:
        filing_url = f["filing_url"]
        filed_date = f["filed_date"]
        form_type = f["form_type"]

        try:
            resp = requests.get(filing_url, headers=SEC_HEADERS, timeout=30)
            time.sleep(REQUEST_DELAY_SEC)
        except Exception as e:
            print(f"Error fetching Form 4 txt {filing_url}: {e}")
            continue

        if resp.status_code != 200:
            print(f"Form 4 txt fetch failed ({resp.status_code}) for {filing_url}")
            continue

        txt = resp.text
        xml_text = extract_ownership_xml_from_txt(txt)
        if not xml_text:
            print(f"No ownershipDocument XML found inside {filing_url}")
            continue

        try:
            txs = parse_form4_xml_transactions(xml_text)
        except Exception as e:
            print(f"Error parsing ownership XML for {filing_url}: {e}")
            continue

        if not txs:
            print(f"No non-derivative transactions parsed for {filing_url}")
            continue

        for row in txs:
            row["filing_url"] = filing_url
            row["filed_date"] = filed_date
            row["form_type"] = form_type

        all_rows.extend(txs)

    all_rows.sort(
        key=lambda r: (
            r.get("transaction_date") or "",
            r.get("filed_date") or "",
        ),
        reverse=True,
    )
    return all_rows


# ----------------- Schedule 13D/13G collector -----------------

SCHED13_FORMS = {
    "SC 13D",
    "SC 13D/A",
    "SC 13G",
    "SC 13G/A",
}


def collect_recent_sched13_filings(days_back: int, max_filings: int) -> List[Dict[str, Any]]:
    """
    Use daily master index to collect recent Schedule 13D/13G filings.
    We keep it filing-level (no deep XML parsing) for now.
    """
    filings: List[Dict[str, Any]] = []

    def is_sched13(ft: str) -> bool:
        return ft.upper() in SCHED13_FORMS

    for d in iter_daily_indexes(days_back):
        day_filings = parse_idx_for_forms(d["text"], is_sched13)
        filings.extend(day_filings)

    filings.sort(key=lambda f: (f["raw_filed_date"], f["file_name"]), reverse=True)
    return filings[:max_filings]


# ----------------- JSON writer -----------------

def write_json(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(payload.get('rows', []))} rows to {path}")


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ----------------- main -----------------

def main() -> None:
    # Form 4
    print("Collecting Form 4 transactions...")
    form4_rows = collect_form4_transactions(FORM4_DAYS_BACK, FORM4_MAX_FILINGS)
    form4_payload = {
        "last_updated_utc": now_utc_iso(),
        "source": "SEC EDGAR (Form 4 XML + daily index)",
        "rows": form4_rows,
    }
    write_json(os.path.join("data", "form4_transactions.json"), form4_payload)

    # Schedule 13D/13G
    print("Collecting Schedule 13D/13G filings...")
    sched13_rows = collect_recent_sched13_filings(SCHED13_DAYS_BACK, SCHED13_MAX_FILINGS)
    sched13_payload = {
        "last_updated_utc": now_utc_iso(),
        "source": "SEC EDGAR (Schedule 13D/13G + daily index)",
        "rows": sched13_rows,
    }
    write_json(os.path.join("data", "schedule_13d13g.json"), sched13_payload)


if __name__ == "__main__":
    main()
