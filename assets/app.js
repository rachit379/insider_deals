// assets/app.js

// ---------- Helpers ----------

const BUY_CODES = new Set(["P", "A"]); // P = Purchase, A = grant/award (treat as buy-ish)
const SELL_CODES = new Set(["S"]);

function fmtDate(isoStr) {
  if (!isoStr) return "";
  // Expecting YYYY-MM-DD
  const parts = isoStr.split("-");
  if (parts.length !== 3) return isoStr;
  const [y, m, d] = parts;
  return `${y}-${m}-${d}`; // simple; tweak if you want fancy format
}

function fmtNumber(n) {
  if (n === null || n === undefined) return "";
  return Number(n).toLocaleString("en-US");
}

function fmtMoney(n) {
  if (n === null || n === undefined) return "";
  return "$" + Number(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtPct(x) {
  if (x === null || x === undefined) return "";
  return (x * 100).toFixed(1) + "%";
}

function codeToLabel(code) {
  if (!code) return "";
  const c = code.toUpperCase();
  if (c === "P") return "Purchase";
  if (c === "S") return "Sale";
  if (c === "A") return "Award";
  return c;
}

function buildRelation(row) {
  const rel = [];
  if (row.owner_is_officer) rel.push("Officer");
  if (row.owner_is_director) rel.push("Director");
  if (row.owner_is_ten_percent) rel.push("10% Owner");
  if (row.owner_officer_title) rel.push(row.owner_officer_title);
  return rel.join(" · ") || "—";
}

function isBuy(row) {
  return BUY_CODES.has((row.transaction_code || "").toUpperCase());
}

function isSell(row) {
  return SELL_CODES.has((row.transaction_code || "").toUpperCase());
}

function matchesSearch(row, term) {
  if (!term) return true;
  const t = term.toLowerCase();
  return (
    (row.issuer_trading_symbol || "").toLowerCase().includes(t) ||
    (row.issuer_name || "").toLowerCase().includes(t) ||
    (row.owner_name || "").toLowerCase().includes(t)
  );
}

// ---------- Global state ----------

const state = {
  form4: {
    allRows: [],
    filteredRows: [],
    currentPage: 1,
    pageSize: 25,
    filterType: "all", // all | buys | sells
    searchTerm: ""
  },
  sched13: {
    allRows: [],
    filteredRows: [],
    currentPage: 1,
    pageSize: 25,
    searchTerm: ""
  }
};

// ---------- Form 4 rendering ----------

function applyForm4Filters() {
  const s = state.form4;
  const { allRows, filterType, searchTerm } = s;

  let rows = allRows;

  if (filterType === "buys" || filterType === "trader") {
    rows = rows.filter(isBuy);
  } else if (filterType === "sells") {
    rows = rows.filter(isSell);
  }
  if (searchTerm) {
    rows = rows.filter((r) => matchesSearch(r, searchTerm));
  }

  s.filteredRows = rows;
  s.currentPage = 1;
  renderForm4Table();
}

function renderForm4Table() function renderForm4Table() {
  const tbody = document.getElementById("form4TableBody");
  const pageInfo = document.getElementById("form4PageInfo");
  const s = state.form4;
  const { filteredRows, currentPage, pageSize } = s;

  tbody.innerHTML = "";

  if (!filteredRows.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 15; // total number of columns
    td.textContent = "No results.";
    tr.appendChild(td);
    tbody.appendChild(tr);
    pageInfo.textContent = "Page 0 of 0";
    return;
  }

  const totalPages = Math.max(1, Math.ceil(filteredRows.length / pageSize));
  const page = Math.min(currentPage, totalPages);
  s.currentPage = page;

  const start = (page - 1) * pageSize;
  const end = start + pageSize;
  const rows = filteredRows.slice(start, end);

  rows.forEach((row) => {
    const tr = document.createElement("tr");

    // 1) Transaction Date + type (Purchase/Sale/Award)
    const tdTransDate = document.createElement("td");
    tdTransDate.innerHTML =
      `<div class="cell-main">${fmtDate(row.transaction_date)}</div>` +
      `<div class="cell-sub">${codeToLabel(row.transaction_code)}</div>`;
    tr.appendChild(tdTransDate);

    // 2) Reported Date (filed date)
    const tdReported = document.createElement("td");
    tdReported.textContent = fmtDate(row.filed_date);
    tr.appendChild(tdReported);

    // 3) Company
    const tdCompany = document.createElement("td");
    tdCompany.textContent = row.issuer_name || "";
    tr.appendChild(tdCompany);

    // 4) Symbol (link to Yahoo Finance)
    const tdSymbol = document.createElement("td");
    const sym = row.issuer_trading_symbol || "";
    if (sym) {
      const a = document.createElement("a");
      a.href = `https://finance.yahoo.com/quote/${encodeURIComponent(sym)}`;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = sym;
      tdSymbol.appendChild(a);
    }
    tr.appendChild(tdSymbol);

    // 5) Insider Relationship (name + role)
    const tdInsider = document.createElement("td");
    tdInsider.innerHTML =
      `<div class="cell-main">${row.owner_name || ""}</div>` +
      `<div class="cell-sub">${buildRelation(row)}</div>`;
    tr.appendChild(tdInsider);

    // 6) Shares Traded
    const tdSharesTraded = document.createElement("td");
    tdSharesTraded.className = "num";
    tdSharesTraded.textContent = fmtNumber(row.transaction_shares);
    tr.appendChild(tdSharesTraded);

    // 7) Average Price
    const tdPrice = document.createElement("td");
    tdPrice.className = "num";
    tdPrice.textContent = fmtMoney(row.transaction_price);
    tr.appendChild(tdPrice);

    // 8) Total Amount (shares * price)
    const tdAmount = document.createElement("td");
    tdAmount.className = "num";
    const total =
      row.transaction_shares != null && row.transaction_price != null
        ? row.transaction_shares * row.transaction_price
        : null;
    tdAmount.textContent = fmtMoney(total);
    tr.appendChild(tdAmount);

    // 9) Shares Owned (after) + direct/indirect
    const tdOwned = document.createElement("td");
    tdOwned.className = "num";
    const owned = fmtNumber(row.shares_owned_after);
    const dirInd = row.direct_or_indirect_ownership || "";
    tdOwned.innerHTML =
      `<div class="cell-main">${owned}</div>` +
      (dirInd ? `<div class="cell-sub">(${dirInd})</div>` : "");
    tr.appendChild(tdOwned);

    // 10) 1M Return
    const td1m = document.createElement("td");
    td1m.className = "num";
    if (row.ret_1m !== null && row.ret_1m !== undefined) {
      td1m.textContent = fmtPct(row.ret_1m);
      if (row.ret_1m > 0.001) td1m.classList.add("pos");
      else if (row.ret_1m < -0.001) td1m.classList.add("neg");
    }
    tr.appendChild(td1m);

    // 11) 3M Return
    const td3m = document.createElement("td");
    td3m.className = "num";
    if (row.ret_3m !== null && row.ret_3m !== undefined) {
      td3m.textContent = fmtPct(row.ret_3m);
      if (row.ret_3m > 0.001) td3m.classList.add("pos");
      else if (row.ret_3m < -0.001) td3m.classList.add("neg");
    }
    tr.appendChild(td3m);

    // 12) 1Y Return
    const td1y = document.createElement("td");
    td1y.className = "num";
    if (row.ret_1y !== null && row.ret_1y !== undefined) {
      td1y.textContent = fmtPct(row.ret_1y);
      if (row.ret_1y > 0.001) td1y.classList.add("pos");
      else if (row.ret_1y < -0.001) td1y.classList.add("neg");
    }
    tr.appendChild(td1y);

    // 13) From 52W High
    const tdHi = document.createElement("td");
    tdHi.className = "num";
    if (row.pct_from_52w_high !== null && row.pct_from_52w_high !== undefined) {
      tdHi.textContent = fmtPct(row.pct_from_52w_high);
      if (row.pct_from_52w_high > 0.001) tdHi.classList.add("pos");
      else if (row.pct_from_52w_high < -0.001) tdHi.classList.add("neg");
    }
    tr.appendChild(tdHi);

    // 14) From 52W Low
    const tdLo = document.createElement("td");
    tdLo.className = "num";
    if (row.pct_from_52w_low !== null && row.pct_from_52w_low !== undefined) {
      tdLo.textContent = fmtPct(row.pct_from_52w_low);
      if (row.pct_from_52w_low > 0.001) tdLo.classList.add("pos");
      else if (row.pct_from_52w_low < -0.001) tdLo.classList.add("neg");
    }
    tr.appendChild(tdLo);

    // 15) Filing link
    const tdFiling = document.createElement("td");
    if (row.filing_url) {
      const a = document.createElement("a");
      a.href = row.filing_url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = "View";
      tdFiling.appendChild(a);
    }
    tr.appendChild(tdFiling);

    tbody.appendChild(tr);
  });

  const totalPagesText = Math.max(
    1,
    Math.ceil(filteredRows.length / pageSize)
  );
  pageInfo.textContent = `Page ${s.currentPage} of ${totalPagesText}`;
}


// ---------- Schedule 13D/13G rendering ----------

function applySched13Filters() {
  const s = state.sched13;
  const { allRows, searchTerm } = s;
  let rows = allRows;

  if (searchTerm) {
    const t = searchTerm.toLowerCase();
    rows = rows.filter((r) => {
      return (
        (r.company_name || "").toLowerCase().includes(t) ||
        (r.cik || "").toLowerCase().includes(t) ||
        (r.form_type || "").toLowerCase().includes(t)
      );
    });
  }

  s.filteredRows = rows;
  s.currentPage = 1;
  renderSched13Table();
}

function renderSched13Table() {
  const tbody = document.getElementById("sched13TableBody");
  const pageInfo = document.getElementById("sched13PageInfo");
  const s = state.sched13;
  const { filteredRows, currentPage, pageSize } = s;

  tbody.innerHTML = "";

  if (!filteredRows.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 8;
    td.textContent = "No results.";
    tr.appendChild(td);
    tbody.appendChild(tr);
    pageInfo.textContent = "Page 0 of 0";
    return;
  }

  const totalPages = Math.max(1, Math.ceil(filteredRows.length / pageSize));
  const page = Math.min(currentPage, totalPages);
  s.currentPage = page;

  const start = (page - 1) * pageSize;
  const end = start + pageSize;
  const rows = filteredRows.slice(start, end);

  rows.forEach((row) => {
    const tr = document.createElement("tr");

    const tdForm = document.createElement("td");
    tdForm.textContent = row.form_type || "";
    tr.appendChild(tdForm);

    const tdFiled = document.createElement("td");
    tdFiled.textContent = fmtDate(row.filed_date);
    tr.appendChild(tdFiled);

    const tdIssuer = document.createElement("td");
    tdIssuer.textContent = row.company_name || "";
    tr.appendChild(tdIssuer);

    const tdIssuerCik = document.createElement("td");
    tdIssuerCik.textContent = row.cik || "";
    tr.appendChild(tdIssuerCik);

    // We don't parse filer name/CIK from the actual 13D yet, so leave blanks / placeholders
    const tdFiler = document.createElement("td");
    tdFiler.textContent = "—";
    tr.appendChild(tdFiler);

    const tdFilerCik = document.createElement("td");
    tdFilerCik.textContent = "—";
    tr.appendChild(tdFilerCik);

    const tdPeriod = document.createElement("td");
    tdPeriod.textContent = "—";
    tr.appendChild(tdPeriod);

    const tdFiling = document.createElement("td");
    if (row.filing_url) {
      const a = document.createElement("a");
      a.href = row.filing_url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = "View";
      tdFiling.appendChild(a);
    }
    tr.appendChild(tdFiling);

    tbody.appendChild(tr);
  });

  const totalPagesText = Math.max(1, Math.ceil(filteredRows.length / pageSize));
  pageInfo.textContent = `Page ${s.currentPage} of ${totalPagesText}`;
}

// ---------- Tab + UI wiring ----------

function setupTabs() {
  const tabButtons = document.querySelectorAll(".tab-button");
  const tabPanels = document.querySelectorAll(".tab-panel");

  tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.getAttribute("data-tab");

      tabButtons.forEach((b) => b.classList.remove("active"));
      tabPanels.forEach((p) => p.classList.remove("active"));

      btn.classList.add("active");
      document.getElementById(`tab-${target}`).classList.add("active");
    });
  });
}

function setupForm4Controls() {
  // Subtabs: All / Buys / Sells
  const subtabButtons = document.querySelectorAll(
    "#tab-form4 .subtab-button"
  );
  subtabButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      subtabButtons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.form4.filterType = btn.getAttribute("data-filter");
      applyForm4Filters();
    });
  });

  // Search
  const searchInput = document.getElementById("form4Search");
  searchInput.addEventListener("input", (e) => {
    state.form4.searchTerm = e.target.value.trim();
    applyForm4Filters();
  });

  // Page size
  const pageSizeSelect = document.getElementById("form4PageSize");
  pageSizeSelect.addEventListener("change", (e) => {
    state.form4.pageSize = parseInt(e.target.value, 10) || 25;
    state.form4.currentPage = 1;
    renderForm4Table();
  });

  // Pagination
  document.getElementById("form4Prev").addEventListener("click", () => {
    if (state.form4.currentPage > 1) {
      state.form4.currentPage--;
      renderForm4Table();
    }
  });

  document.getElementById("form4Next").addEventListener("click", () => {
    const totalPages = Math.max(
      1,
      Math.ceil(state.form4.filteredRows.length / state.form4.pageSize)
    );
    if (state.form4.currentPage < totalPages) {
      state.form4.currentPage++;
      renderForm4Table();
    }
  });
}

function setupSched13Controls() {
  const searchInput = document.getElementById("sched13Search");
  searchInput.addEventListener("input", (e) => {
    state.sched13.searchTerm = e.target.value.trim();
    applySched13Filters();
  });

  const pageSizeSelect = document.getElementById("sched13PageSize");
  pageSizeSelect.addEventListener("change", (e) => {
    state.sched13.pageSize = parseInt(e.target.value, 10) || 25;
    state.sched13.currentPage = 1;
    renderSched13Table();
  });

  document.getElementById("sched13Prev").addEventListener("click", () => {
    if (state.sched13.currentPage > 1) {
      state.sched13.currentPage--;
      renderSched13Table();
    }
  });

  document.getElementById("sched13Next").addEventListener("click", () => {
    const totalPages = Math.max(
      1,
      Math.ceil(state.sched13.filteredRows.length / state.sched13.pageSize)
    );
    if (state.sched13.currentPage < totalPages) {
      state.sched13.currentPage++;
      renderSched13Table();
    }
  });
}

// ---------- Data loading ----------

async function loadForm4Data() {
  const res = await fetch("data/form4_transactions.json");
  if (!res.ok) throw new Error("Failed to load Form 4 JSON");
  const json = await res.json();

  const last = document.getElementById("lastUpdated");
  if (json.last_updated_utc) {
    last.textContent = `Last updated: ${json.last_updated_utc}`;
  } else {
    last.textContent = "Last updated: –";
  }

  state.form4.allRows = json.rows || [];
  applyForm4Filters();
}

async function loadSched13Data() {
  const res = await fetch("data/schedule_13d13g.json");
  if (!res.ok) {
    console.warn("Schedule 13D/13G JSON not found");
    return;
  }
  const json = await res.json();
  state.sched13.allRows = json.rows || [];
  applySched13Filters();
}

// ---------- init ----------

async function init() {
  setupTabs();
  setupForm4Controls();
  setupSched13Controls();

  try {
    await loadForm4Data();
    await loadSched13Data();
  } catch (err) {
    console.error("Error loading data", err);
    document.getElementById("lastUpdated").textContent =
      "Error loading data – check console.";
  }
}

document.addEventListener("DOMContentLoaded", init);
