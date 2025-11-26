import json
import re
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests

# ---------- CONFIG ----------

SEC_HEADERS = {
    # TODO: change to your name + email before running
    "User-Agent": "Rachit Aggarwal rachit@example.com",
}

BASE_DAILY_INDEX_URL = (
    "https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{q}/master.{ymd}.idx"
)

FORM4_DAYS_BACK = 3
FORM4_MAX_FILINGS = 150

SCHED13_DAYS_BACK = 7
SCHED13_MAX_FILINGS = 200

REQUEST_DELAY_SEC = 0.2


def quarter_of_month(m: int) -> int:
    return (m - 1) // 3 + 1


def fetch_master_idx(day: date) -> Optional[str]:
    q = quarter_of_month(day.month)
    url = BASE_DAILY_INDEX_URL.format(year=day.year, q=q, ymd=day.strftime("%Y%m%d"))
    resp = requests.get(url, headers=SEC_HEADERS, timeout=30)
    time.sleep(REQUEST_DELAY_SEC)
    if resp.status_code == 200:
        return resp.text
    return None


def iter_daily_indexes(days_back: int) -> List[Dict[str, Any]]:
    today = date.today()
    out: List[Dict[str, Any]] = []
    for offset in range(days_back):
        d = today - timedelta(days=offset)
        txt = fetch_master_idx(d)
        if not txt:
            continue
        out.append({"date": d, "text": txt})
    return out


def parse_idx_for_forms(idx_text: str, form_predicate) -> List[Dict[str, Any]]:
    lines = idx_text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith("-----"):
            start = i + 1
            break
    if start is None:
        return []

    entries: List[Dict[str, Any]] = []
    for line in lines[start:]:
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) != 5:
            continue
        cik, name, form_type, filed_date, file_name = parts
        form_type = form_type.strip()
        if not form_predicate(form_type):
            continue
        entries.append(
            {
                "cik": cik.strip(),
                "company_name": name.strip(),
                "form_type": form_type,
                "filed_date": filed_date.strip(),
                "file_name": file_name.strip(),
                "filing_url": f"https://www.sec.gov/Archives/{file_name.strip()}",
            }
        )
    return entries


def _extract_sec_header_block(text: str) -> Optional[str]:
    m = re.search(
        r"<SEC-HEADER>(.*?)(</SEC-HEADER>|<DOCUMENT>)",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    m = re.search(r"<SEC-HEADER>(.*)$", text, flags=re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


def _parse_key_value_line(line: str) -> Optional[tuple]:
    if ":" not in line:
        return None
    k, v = line.split(":", 1)
    k = k.strip()
    v = v.strip()
    if not k:
        return None
    return k, v


def safe_float(x: Optional[str]) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(x.replace(",", ""))
    except Exception:
        return None


def safe_int_from_float(x: Optional[str]) -> Optional[int]:
    f = safe_float(x)
    if f is None:
        return None
    return int(round(f))


def get_accession_base_url(file_name: str) -> str:
    """
    Build the accession folder URL from the master.idx file_name, e.g.:

    edgar/data/1009759/0001009759-25-000062.txt
    edgar/data/1009759/0001009759-25-000062/0001009759-25-000062.txt
    """
    path = file_name

    # strip .txt if present
    if path.endswith(".txt"):
        path = path[:-4]

    parts = path.split("/")
    # If path ends with ACCESSION/ACCESSION, drop the last segment
    #   edgar/data/CIK/ACC/ACC  -> edgar/data/CIK/ACC
    if len(parts) >= 2 and parts[-1] == parts[-2]:
        parts = parts[:-1]

    accession_dir = "/".join(parts)
    return "https://www.sec.gov/Archives/" + accession_dir + "/"


def find_ownership_xml_url(filing_url: str) -> Optional[str]:
    base = get_accession_base_url(filing_url)
    index_url = urljoin(base, "index.json")
    resp = requests.get(index_url, headers=SEC_HEADERS, timeout=30)
    time.sleep(REQUEST_DELAY_SEC)
    if resp.status_code != 200:
        return None
    data = resp.json()
    items = data.get("directory", {}).get("item", [])
    xml_candidates = [it["name"] for it in items if it["name"].lower().endswith(".xml")]
    if not xml_candidates:
        return None
    preferred = [n for n in xml_candidates if "doc4" in n.lower() or "ownership" in n.lower()]
    name = (preferred or xml_candidates)[0]
    return urljoin(base, name)


def parse_form4_xml_transactions(xml_text: str) -> List[Dict[str, Any]]:
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml_text)

    def get(node, path, default=None):
        if node is None:
            return default
        el = node.find(path)
        return el.text.strip() if el is not None and el.text is not None else default

    issuer_node = root.find("issuer")
    issuer_cik = get(issuer_node, "issuerCik")
    issuer_name = get(issuer_node, "issuerName")
    issuer_symbol = get(issuer_node, "issuerTradingSymbol")

    owners = []
    for ro in root.findall("reportingOwner"):
        name = get(ro, "reportingOwnerId/rptOwnerName")
        cik = get(ro, "reportingOwnerId/rptOwnerCik")
        rel_node = ro.find("reportingOwnerRelationship")

        def norm_bool(val: Optional[str]) -> bool:
            if not val:
                return False
            return val.strip().upper() in {"1", "Y", "YES", "TRUE"}

        is_dir = norm_bool(get(rel_node, "isDirector"))
        is_off = norm_bool(get(rel_node, "isOfficer"))
        is_10p = norm_bool(get(rel_node, "isTenPercentOwner"))
        is_other = norm_bool(get(rel_node, "isOther"))
        officer_title = get(rel_node, "officerTitle")

        rel_parts = []
        if is_off:
            rel_parts.append("Officer")
        if is_dir:
            rel_parts.append("Director")
        if is_10p:
            rel_parts.append("10% Owner")
        if is_other and not rel_parts:
            rel_parts.append("Other")
        relation = ", ".join(rel_parts) if rel_parts else "Other"

        owners.append(
            {
                "insider_name": name,
                "insider_cik": cik,
                "relation": relation,
                "officer_title": officer_title,
            }
        )

    txs: List[Dict[str, Any]] = []

    for tx in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        tx_date = get(tx, "transactionDate/value")
        tx_code = get(tx, "transactionCoding/transactionCode")
        tx_desc = get(tx, "transactionCoding/transactionDescription")
        tx_shares = get(tx, "transactionAmounts/transactionShares/value")
        tx_price = get(tx, "transactionAmounts/transactionPricePerShare/value")
        tx_shares_after = get(
            tx, "postTransactionAmounts/sharesOwnedFollowingTransaction/value"
        )
        ownership = get(tx, "ownershipNature/directOrIndirectOwnership/value")
        timeliness = get(tx, "transactionTimeliness/value")

        is_buy = tx_code == "P"
        is_sale = tx_code == "S"

        if not tx_desc:
            if is_buy:
                tx_desc = "Purchase (Open Market)"
            elif is_sale:
                tx_desc = "Sale"
            else:
                tx_desc = f"Code {tx_code or '?'}"

        base = {
            "issuer_name": issuer_name,
            "issuer_symbol": issuer_symbol,
            "issuer_cik": issuer_cik,
            "transaction_date": tx_date,
            "transaction_code": tx_code,
            "transaction_description": tx_desc,
            "shares_traded": safe_int_from_float(tx_shares),
            "price": safe_float(tx_price),
            "shares_held_after": safe_int_from_float(tx_shares_after),
            "owner_type": ownership,
            "timeliness": timeliness,
            "is_buy": is_buy,
            "is_sale": is_sale,
        }

        if not owners:
            txs.append({**base, "insider_name": None, "insider_cik": None,
                        "relation": None, "officer_title": None})
        else:
            for o in owners:
                txs.append({**base, **o})

    return txs


def collect_form4_transactions(days_back: int, max_filings: int) -> List[Dict[str, Any]]:
    """
    Collect recent Form 4 insider transactions.

    - Uses the EDGAR daily master index for the last `days_back` days
    - Filters for Form 4 / 4/A
    - For each filing, finds the ownership XML in the accession folder via index.json
    - Parses non-derivative (Table I) transactions into a flat list of rows

    Depends on:
      - iter_daily_indexes
      - parse_idx_for_forms
      - find_ownership_xml_url(file_name: str)
      - parse_form4_xml_transactions
      - SEC_HEADERS, REQUEST_DELAY_SEC
    """
    # 1) Get all Form 4 filings from the last N days
    idx_days = iter_daily_indexes(days_back)

    def is_form4(ft: str) -> bool:
        return ft in ("4", "4/A")

    filings: List[Dict[str, Any]] = []
    for d in idx_days:
        filings.extend(parse_idx_for_forms(d["text"], is_form4))

    # Sort by filed_date (string YYYYMMDD) descending and limit
    filings = sorted(filings, key=lambda x: x["filed_date"], reverse=True)[:max_filings]

    # 2) For each filing, fetch & parse the ownership XML
    all_txs: List[Dict[str, Any]] = []

    for f in filings:
        filing_url = f["filing_url"]   # for the link in UI
        file_name = f["file_name"]     # edgar/data/CIK/ACC.txt (from master.idx)

        try:
            # Find XML in accession folder via index.json
            xml_url = find_ownership_xml_url(file_name)
            if not xml_url:
                print("No ownership XML for", filing_url)
                continue

            resp = requests.get(xml_url, headers=SEC_HEADERS, timeout=30)
            time.sleep(REQUEST_DELAY_SEC)
            if resp.status_code != 200:
                print("XML fetch failed", xml_url, resp.status_code)
                continue

            txs = parse_form4_xml_transactions(resp.text)
            if not txs:
                # Useful debug if you want to see filings with only derivative/etc.
                # print("No non-derivative transactions in", filing_url)
                pass

            # Attach filing metadata to each transaction row
            for tx in txs:
                tx["filing_url"] = filing_url
                tx["filed_date"] = f["filed_date"]

            all_txs.extend(txs)

        except Exception as e:
            print("Error parsing Form 4:", filing_url, e)

    # 3) Sort transactions by transaction_date then filed_date (both strings)
    all_txs = sorted(
        all_txs,
        key=lambda x: (x.get("transaction_date") or "", x.get("filed_date") or ""),
        reverse=True,
    )

    return all_txs


def collect_schedule_13d_13g(days_back: int, max_filings: int) -> List[Dict[str, Any]]:
    idx_days = iter_daily_indexes(days_back)

    def is_sched13(ft: str) -> bool:
        ft = ft.upper()
        return ft.startswith("SC 13D") or ft.startswith("SC 13G")

    filings: List[Dict[str, Any]] = []
    for d in idx_days:
        filings.extend(parse_idx_for_forms(d["text"], is_sched13))

    filings = sorted(filings, key=lambda x: x["filed_date"], reverse=True)[:max_filings]

    results: List[Dict[str, Any]] = []
    for f in filings:
        filing_url = f["filing_url"]
        try:
            resp = requests.get(filing_url, headers=SEC_HEADERS, timeout=30)
            time.sleep(REQUEST_DELAY_SEC)
            if resp.status_code != 200:
                print("13D/G fetch failed", filing_url, resp.status_code)
                continue
            header = parse_13d_13g_header(resp.text)
            row = {
                "form_type": f["form_type"],
                "filing_url": filing_url,
                "filed_date": f["filed_date"],
                "issuer_name": header.get("subject_company_name") or f["company_name"],
                "issuer_cik": header.get("subject_company_cik") or f["cik"],
                "filer_name": header.get("filer_name"),
                "filer_cik": header.get("filer_cik"),
                "period_of_report": header.get("period_of_report"),
            }
            results.append(row)
        except Exception as e:
            print("Error parsing 13D/G:", filing_url, e)
    results = sorted(results, key=lambda x: x["filed_date"], reverse=True)
    return results


def main():
    print("Collecting Form 4 transactions...")
    form4 = collect_form4_transactions(FORM4_DAYS_BACK, FORM4_MAX_FILINGS)
    form4_payload = {
        "last_updated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "source": "SEC EDGAR (Form 4 XML + daily index)",
        "rows": form4,
    }
    with open("data/form4_transactions.json", "w", encoding="utf-8") as f:
        json.dump(form4_payload, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(form4)} Form 4 transactions.")

    print("Collecting Schedule 13D/13G filings...")
    sched13 = collect_schedule_13d_13g(SCHED13_DAYS_BACK, SCHED13_MAX_FILINGS)
    sched13_payload = {
        "last_updated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "source": "SEC EDGAR (Schedule 13D/13G + daily index)",
        "rows": sched13,
    }
    with open("data/schedule_13d13g.json", "w", encoding="utf-8") as f:
        json.dump(sched13_payload, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(sched13)} Schedule 13D/13G filings.")


if __name__ == "__main__":
    main()
