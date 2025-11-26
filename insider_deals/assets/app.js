const state = {
  form4: {
    rows: [],
    filter: "all",
    search: "",
    page: 1,
    pageSize: 25,
  },
  sched13: {
    rows: [],
    search: "",
    page: 1,
    pageSize: 25,
  },
};

function fmtNumber(x) {
  if (x === null || x === undefined) return "";
  return x.toLocaleString("en-US");
}

function fmtPrice(x) {
  if (x === null || x === undefined) return "";
  return "$" + x.toFixed(2);
}

function fmtDate(s) {
  if (!s) return "";
  if (s.length === 8 && /^\d+$/.test(s)) {
    const y = s.slice(0, 4);
    const m = s.slice(4, 6);
    const d = s.slice(6, 8);
    return `${m}/${d}/${y}`;
  }
  return s;
}

async function loadData() {
  const [form4Res, sched13Res] = await Promise.all([
    fetch("data/form4_transactions.json", { cache: "no-store" }),
    fetch("data/schedule_13d13g.json", { cache: "no-store" }),
  ]);

  const form4Json = await form4Res.json();
  const sched13Json = await sched13Res.json();

  state.form4.rows = form4Json.rows || [];
  state.sched13.rows = sched13Json.rows || [];

  const last = document.getElementById("lastUpdated");
  last.textContent = `Last updated: ${form4Json.last_updated_utc || "n/a"}`;

  renderForm4();
  renderSched13();
}

function getFilteredForm4Rows() {
  const { rows, filter, search } = state.form4;
  const query = (search || "").trim().toLowerCase();

  return rows.filter((r) => {
    if (filter === "buys" && !r.is_buy) return false;
    if (filter === "sells" && !r.is_sale) return false;

    if (!query) return true;

    const haystack = [
      r.insider_name,
      r.issuer_symbol,
      r.issuer_name,
      r.relation,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();

    return haystack.includes(query);
  });
}

function renderForm4() {
  const allRows = getFilteredForm4Rows();
  const { pageSize } = state.form4;
  const totalPages = Math.max(1, Math.ceil(allRows.length / pageSize));
  state.form4.page = Math.min(state.form4.page, totalPages);

  const start = (state.form4.page - 1) * pageSize;
  const pageRows = allRows.slice(start, start + pageSize);

  const tbody = document.getElementById("form4TableBody");
  tbody.innerHTML = pageRows
    .map((r) => {
      const ownerType =
        (r.owner_type || "").toUpperCase() === "I" ? "Indirect" : "Direct";
      const ownerClass =
        ownerType === "Direct" ? "badge-owner-type direct" : "badge-owner-type indirect";

      const txClass = r.is_buy
        ? "badge-buy"
        : r.is_sale
        ? "badge-sell"
        : "";

      return `<tr>
        <td>${r.insider_name || ""}</td>
        <td>${r.relation || ""}</td>
        <td>${fmtDate(r.transaction_date)}</td>
        <td>${r.issuer_symbol || ""}</td>
        <td>${r.issuer_name || ""}</td>
        <td><span class="${txClass}">${r.transaction_description || ""}</span></td>
        <td><span class="${ownerClass}">${ownerType}</span></td>
        <td class="num">${fmtNumber(r.shares_traded)}</td>
        <td class="num">${r.price != null ? fmtPrice(r.price) : ""}</td>
        <td class="num">${fmtNumber(r.shares_held_after)}</td>
        <td><a class="link-pill" href="${r.filing_url}" target="_blank" rel="noopener">View</a></td>
      </tr>`;
    })
    .join("");

  const info = document.getElementById("form4PageInfo");
  info.textContent = `Page ${state.form4.page} of ${totalPages}`;

  const prevBtn = document.getElementById("form4Prev");
  const nextBtn = document.getElementById("form4Next");
  prevBtn.disabled = state.form4.page <= 1;
  nextBtn.disabled = state.form4.page >= totalPages;
}

function getFilteredSched13Rows() {
  const { rows, search } = state.sched13;
  const query = (search || "").trim().toLowerCase();

  return rows.filter((r) => {
    if (!query) return true;

    const haystack = [
      r.form_type,
      r.issuer_name,
      r.issuer_cik,
      r.filer_name,
      r.filer_cik,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();

    return haystack.includes(query);
  });
}

function renderSched13() {
  const allRows = getFilteredSched13Rows();
  const { pageSize } = state.sched13;
  const totalPages = Math.max(1, Math.ceil(allRows.length / pageSize));
  state.sched13.page = Math.min(state.sched13.page, totalPages);

  const start = (state.sched13.page - 1) * pageSize;
  const pageRows = allRows.slice(start, start + pageSize);

  const tbody = document.getElementById("sched13TableBody");
  tbody.innerHTML = pageRows
    .map((r) => {
      return `<tr>
        <td>${r.form_type}</td>
        <td>${fmtDate(r.filed_date)}</td>
        <td>${r.issuer_name || ""}</td>
        <td>${r.issuer_cik || ""}</td>
        <td>${r.filer_name || ""}</td>
        <td>${r.filer_cik || ""}</td>
        <td>${fmtDate(r.period_of_report)}</td>
        <td><a class="link-pill" href="${r.filing_url}" target="_blank" rel="noopener">View</a></td>
      </tr>`;
    })
    .join("");

  const info = document.getElementById("sched13PageInfo");
  info.textContent = `Page ${state.sched13.page} of ${totalPages}`;

  const prevBtn = document.getElementById("sched13Prev");
  const nextBtn = document.getElementById("sched13Next");
  prevBtn.disabled = state.sched13.page <= 1;
  nextBtn.disabled = state.sched13.page >= totalPages;
}

function setupTabs() {
  const tabButtons = document.querySelectorAll(".tab-button");
  const tabPanels = document.querySelectorAll(".tab-panel");

  tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab;
      tabButtons.forEach((b) => b.classList.toggle("active", b === btn));
      tabPanels.forEach((p) =>
        p.classList.toggle("active", p.id === `tab-${tab}`)
      );
    });
  });
}

function setupForm4Controls() {
  document.querySelectorAll(".subtab-button").forEach((btn) => {
    btn.addEventListener("click", () => {
      const filter = btn.dataset.filter;
      state.form4.filter = filter;
      state.form4.page = 1;
      document
        .querySelectorAll(".subtab-button")
        .forEach((b) => b.classList.toggle("active", b === btn));
      renderForm4();
    });
  });

  const searchInput = document.getElementById("form4Search");
  searchInput.addEventListener("input", (e) => {
    state.form4.search = e.target.value;
    state.form4.page = 1;
    renderForm4();
  });

  const pageSizeSelect = document.getElementById("form4PageSize");
  pageSizeSelect.addEventListener("change", (e) => {
    state.form4.pageSize = parseInt(e.target.value, 10) || 25;
    state.form4.page = 1;
    renderForm4();
  });

  document.getElementById("form4Prev").addEventListener("click", () => {
    if (state.form4.page > 1) {
      state.form4.page -= 1;
      renderForm4();
    }
  });
  document.getElementById("form4Next").addEventListener("click", () => {
    state.form4.page += 1;
    renderForm4();
  });
}

function setupSched13Controls() {
  const searchInput = document.getElementById("sched13Search");
  searchInput.addEventListener("input", (e) => {
    state.sched13.search = e.target.value;
    state.sched13.page = 1;
    renderSched13();
  });

  const pageSizeSelect = document.getElementById("sched13PageSize");
  pageSizeSelect.addEventListener("change", (e) => {
    state.sched13.pageSize = parseInt(e.target.value, 10) || 25;
    state.sched13.page = 1;
    renderSched13();
  });

  document.getElementById("sched13Prev").addEventListener("click", () => {
    if (state.sched13.page > 1) {
      state.sched13.page -= 1;
      renderSched13();
    }
  });
  document.getElementById("sched13Next").addEventListener("click", () => {
    state.sched13.page += 1;
    renderSched13();
  });
}

document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  setupForm4Controls();
  setupSched13Controls();
  loadData().catch((err) => {
    console.error("Error loading data", err);
    document.getElementById("lastUpdated").textContent =
      "Error loading data – check console.";
  });
});
