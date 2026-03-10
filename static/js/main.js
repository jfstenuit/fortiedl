/**
 * Application entry point.
 */

import { api, loadCsrf } from "./api.js";
import { renderEntries, renderAudit, renderHistoryModal, confirm } from "./render.js";
import { showBanner } from "./util.js";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let currentList = "default";
let currentEntries = [];
let sortKey = "added_at";
let sortDir = -1;          // -1 = newest first
let auditPage = 1;
const AUDIT_PER_PAGE = 50;
let auditTotal = 0;

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
async function init() {
  try {
    await loadCsrf();
    const me = await api.getMe();
    document.getElementById("user-name").textContent = me.name || me.email;
  } catch (err) {
    showBanner("Session error — please reload.");
    return;
  }

  await loadLists();
  navigateTo(location.hash || "#entries");

  // Tab clicks
  document.querySelectorAll(".nav-tab").forEach(tab => {
    tab.addEventListener("click", () => navigateTo(tab.dataset.hash));
  });

  // List selector
  document.getElementById("list-selector").addEventListener("change", async e => {
    currentList = e.target.value;
    document.querySelectorAll(".list-selector-sync").forEach(s => (s.value = currentList));
    if (document.getElementById("section-entries").hidden === false) {
      await loadEntries();
    }
  });
  document.querySelectorAll(".list-selector-sync").forEach(s => {
    s.addEventListener("change", e => {
      currentList = e.target.value;
      document.getElementById("list-selector").value = currentList;
    });
  });

  // Sort headers
  document.querySelectorAll("[data-sort]").forEach(th => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (sortKey === key) { sortDir *= -1; }
      else { sortKey = key; sortDir = -1; }
      document.querySelectorAll("[data-sort]").forEach(el => el.classList.remove("sort-asc", "sort-desc"));
      th.classList.add(sortDir === 1 ? "sort-asc" : "sort-desc");
      renderEntries(currentEntries, sortKey, sortDir, handleDelete, handleHistory);
    });
  });

  // Refresh button
  document.getElementById("btn-refresh").addEventListener("click", loadEntries);

  // Add entry form
  document.getElementById("form-add").addEventListener("submit", handleAddSubmit);

  // Bulk add form
  document.getElementById("form-bulk").addEventListener("submit", handleBulkSubmit);

  // Audit filter
  document.getElementById("audit-filter").addEventListener("input", filterAudit);

  // Audit pagination
  document.getElementById("btn-audit-prev").addEventListener("click", () => { auditPage--; loadAudit(); });
  document.getElementById("btn-audit-next").addEventListener("click", () => { auditPage++; loadAudit(); });
}

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------
function navigateTo(hash) {
  const sections = ["entries", "add", "bulk", "audit"];
  const name = hash.replace("#", "") || "entries";

  sections.forEach(s => {
    document.getElementById(`section-${s}`).hidden = s !== name;
  });
  document.querySelectorAll(".nav-tab").forEach(t => {
    t.classList.toggle("nav-tab--active", t.dataset.hash === `#${name}`);
  });

  history.replaceState(null, "", `#${name}`);

  if (name === "entries") loadEntries();
  if (name === "audit")   { auditPage = 1; loadAudit(); }
}

// ---------------------------------------------------------------------------
// Lists
// ---------------------------------------------------------------------------
async function loadLists() {
  try {
    const lists = await api.getLists();
    const selectors = document.querySelectorAll(".list-selector-all");
    selectors.forEach(sel => {
      sel.innerHTML = lists.map(l =>
        `<option value="${l}"${l === currentList ? " selected" : ""}>${l}</option>`
      ).join("");
    });
  } catch (err) {
    showBanner(`Failed to load lists: ${err.message}`);
  }
}

// ---------------------------------------------------------------------------
// Entries
// ---------------------------------------------------------------------------
async function loadEntries() {
  const spinner = document.getElementById("entries-spinner");
  spinner.hidden = false;
  try {
    currentEntries = await api.getEntries(currentList);
    renderEntries(currentEntries, sortKey, sortDir, handleDelete, handleHistory);
    document.getElementById("entries-count").textContent = `${currentEntries.length} entr${currentEntries.length === 1 ? "y" : "ies"}`;
  } catch (err) {
    showBanner(`Failed to load entries: ${err.message}`);
  } finally {
    spinner.hidden = true;
  }
}

async function handleDelete(ip, list) {
  const ok = await confirm(`Delete ${ip} from list "${list}"?`);
  if (!ok) return;
  try {
    await api.deleteEntry(ip, list);
    showBanner(`${ip} removed.`, "success");
    await loadEntries();
  } catch (err) {
    showBanner(`Delete failed: ${err.message}`);
  }
}

async function handleHistory(ip) {
  try {
    const rows = await api.getHistory(ip);
    renderHistoryModal(ip, rows);
  } catch (err) {
    showBanner(`Failed to load history: ${err.message}`);
  }
}

// ---------------------------------------------------------------------------
// Add entry
// ---------------------------------------------------------------------------
async function handleAddSubmit(e) {
  e.preventDefault();
  const form = e.target;
  const list_name = form.querySelector('[name="list_name"]').value;
  const ip        = form.querySelector('[name="ip"]').value.trim();
  const reason    = form.querySelector('[name="reason"]').value.trim();
  const expires_in = form.querySelector('[name="expires_in"]').value;

  if (!ip || !reason) {
    showBanner("IP and reason are required.");
    return;
  }

  try {
    await api.addEntry({ list_name, ip, reason, expires_in });
    showBanner(`${ip} added to list "${list_name}".`, "success");
    form.reset();
    form.querySelector('[name="list_name"]').value = currentList;
  } catch (err) {
    showBanner(`Failed to add entry: ${err.message}`);
  }
}

// ---------------------------------------------------------------------------
// Bulk add
// ---------------------------------------------------------------------------
async function handleBulkSubmit(e) {
  e.preventDefault();
  const form = e.target;
  const list_name  = form.querySelector('[name="list_name"]').value;
  const rawIPs     = form.querySelector('[name="ips"]').value;
  const reason     = form.querySelector('[name="reason"]').value.trim();
  const expires_in = form.querySelector('[name="expires_in"]').value;

  const ips = rawIPs.split("\n").map(l => l.trim()).filter(Boolean);
  if (!ips.length) { showBanner("No IPs provided."); return; }
  if (!reason)     { showBanner("Reason is required."); return; }

  const statusEl = document.getElementById("bulk-status");
  statusEl.textContent = "";

  let ok = 0, fail = 0;
  for (const ip of ips) {
    try {
      await api.addEntry({ list_name, ip, reason, expires_in });
      ok++;
    } catch (err) {
      fail++;
      const line = document.createElement("div");
      line.className = "bulk-error";
      line.textContent = `${ip}: ${err.message}`;
      statusEl.appendChild(line);
    }
  }

  showBanner(
    `Bulk add: ${ok} added${fail ? `, ${fail} failed` : ""}.`,
    fail ? "error" : "success",
  );
  if (ok) {
    form.querySelector('[name="ips"]').value = "";
    form.querySelector('[name="reason"]').value = "";
  }
}

// ---------------------------------------------------------------------------
// Audit
// ---------------------------------------------------------------------------
async function loadAudit() {
  const spinner = document.getElementById("audit-spinner");
  spinner.hidden = false;
  try {
    const data = await api.getAudit(currentList, auditPage, AUDIT_PER_PAGE);
    auditTotal = data.total;
    renderAudit(data.rows);
    filterAudit();
    updateAuditPager();
  } catch (err) {
    showBanner(`Failed to load audit: ${err.message}`);
  } finally {
    spinner.hidden = true;
  }
}

function filterAudit() {
  const q = document.getElementById("audit-filter").value.toLowerCase();
  document.querySelectorAll(".audit-row").forEach(row => {
    row.hidden = q && !row.textContent.toLowerCase().includes(q);
  });
}

function updateAuditPager() {
  const total = Math.ceil(auditTotal / AUDIT_PER_PAGE) || 1;
  document.getElementById("audit-page-info").textContent = `Page ${auditPage} / ${total}`;
  document.getElementById("btn-audit-prev").disabled = auditPage <= 1;
  document.getElementById("btn-audit-next").disabled = auditPage >= total;
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", init);
