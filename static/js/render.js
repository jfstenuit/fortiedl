/**
 * DOM rendering helpers.
 */

import { escHtml, fmtDate, expiryLabel } from "./util.js";

/**
 * Render the entries list into #entries-list.
 * @param {Array} entries - raw entries from the API
 * @param {string} sortKey - field name to sort by
 * @param {number} sortDir - 1 = asc, -1 = desc
 * @param {Function} onDelete - called with (ip, listName)
 * @param {Function} onHistory - called with (ip)
 */
export function renderEntries(entries, sortKey, sortDir, onDelete, onHistory) {
  const container = document.getElementById("entries-list");

  if (!entries.length) {
    container.innerHTML = '<p class="empty-state">No entries in this list.</p>';
    return;
  }

  const sorted = [...entries].sort((a, b) => {
    let av = a[sortKey] ?? "";
    let bv = b[sortKey] ?? "";
    if (av < bv) return -1 * sortDir;
    if (av > bv) return  1 * sortDir;
    return 0;
  });

  container.innerHTML = sorted.map(e => `
    <div class="entry-card" data-ip="${escHtml(e.ip)}" data-list="${escHtml(e.list_name)}">
      <div class="entry-ip">${escHtml(e.ip)}</div>
      <div class="entry-meta">
        <span class="entry-reason" title="${escHtml(e.reason)}">${escHtml(e.reason)}</span>
        <span class="entry-by">by ${escHtml(e.added_by)}</span>
        <span class="entry-added" title="${escHtml(fmtDate(e.added_at))}">added ${fmtDate(e.added_at)}</span>
        <span class="entry-expires tag tag--${expiryLabel(e.expires_at) === 'expired' ? 'red' : 'blue'}">
          expires ${fmtDate(e.expires_at)} (${expiryLabel(e.expires_at)})
        </span>
      </div>
      <div class="entry-actions">
        <button class="btn btn--ghost btn--sm js-history" data-ip="${escHtml(e.ip)}">History</button>
        <button class="btn btn--danger btn--sm js-delete"
          data-ip="${escHtml(e.ip)}" data-list="${escHtml(e.list_name)}">Delete</button>
      </div>
    </div>
  `).join("");

  container.querySelectorAll(".js-delete").forEach(btn => {
    btn.addEventListener("click", () => onDelete(btn.dataset.ip, btn.dataset.list));
  });
  container.querySelectorAll(".js-history").forEach(btn => {
    btn.addEventListener("click", () => onHistory(btn.dataset.ip));
  });
}

/**
 * Render audit rows into #audit-list.
 */
export function renderAudit(rows) {
  const container = document.getElementById("audit-list");

  if (!rows.length) {
    container.innerHTML = '<p class="empty-state">No audit records found.</p>';
    return;
  }

  const ACTION_CLASS = { add: "green", remove: "red", expire: "yellow" };

  container.innerHTML = rows.map(r => `
    <div class="audit-row">
      <span class="tag tag--${ACTION_CLASS[r.action] ?? 'blue'}">${escHtml(r.action)}</span>
      <span class="audit-ip">${escHtml(r.ip)}</span>
      <span class="audit-list">[${escHtml(r.list_name)}]</span>
      <span class="audit-user">${escHtml(r.user_email)}</span>
      <span class="audit-reason" title="${escHtml(r.reason ?? '')}">${escHtml(r.reason ?? "—")}</span>
      <span class="audit-ts">${fmtDate(r.timestamp)}</span>
    </div>
  `).join("");
}

/**
 * Render a modal with history rows for one IP.
 */
export function renderHistoryModal(ip, rows) {
  const existing = document.getElementById("history-modal");
  if (existing) existing.remove();

  const ACTION_CLASS = { add: "green", remove: "red", expire: "yellow" };

  const modal = document.createElement("div");
  modal.id = "history-modal";
  modal.className = "modal-backdrop";
  modal.innerHTML = `
    <div class="modal">
      <div class="modal-header">
        <h2>History — ${escHtml(ip)}</h2>
        <button class="btn btn--ghost modal-close" id="modal-close-btn">✕</button>
      </div>
      <div class="modal-body">
        ${rows.length ? rows.map(r => `
          <div class="audit-row">
            <span class="tag tag--${ACTION_CLASS[r.action] ?? 'blue'}">${escHtml(r.action)}</span>
            <span class="audit-list">[${escHtml(r.list_name)}]</span>
            <span class="audit-user">${escHtml(r.user_email)}</span>
            <span class="audit-reason">${escHtml(r.reason ?? "—")}</span>
            <span class="audit-ts">${fmtDate(r.timestamp)}</span>
          </div>
        `).join("") : '<p class="empty-state">No history for this IP.</p>'}
      </div>
    </div>
  `;

  document.body.appendChild(modal);
  document.getElementById("modal-close-btn").addEventListener("click", () => modal.remove());
  modal.addEventListener("click", e => { if (e.target === modal) modal.remove(); });
}

/**
 * Render a simple confirmation dialog.
 * Returns a Promise<boolean>.
 */
export function confirm(message) {
  return new Promise(resolve => {
    const existing = document.getElementById("confirm-modal");
    if (existing) existing.remove();

    const modal = document.createElement("div");
    modal.id = "confirm-modal";
    modal.className = "modal-backdrop";
    modal.innerHTML = `
      <div class="modal modal--sm">
        <div class="modal-header"><h2>Confirm</h2></div>
        <div class="modal-body">
          <p>${escHtml(message)}</p>
          <div class="modal-actions">
            <button class="btn btn--danger" id="confirm-yes">Delete</button>
            <button class="btn btn--ghost" id="confirm-no">Cancel</button>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    document.getElementById("confirm-yes").addEventListener("click", () => { modal.remove(); resolve(true); });
    document.getElementById("confirm-no").addEventListener("click", () => { modal.remove(); resolve(false); });
    modal.addEventListener("click", e => { if (e.target === modal) { modal.remove(); resolve(false); } });
  });
}
