/**
 * Thin fetch wrapper — adds CSRF token and handles errors uniformly.
 */

let _csrfToken = "";

export async function loadCsrf() {
  const res = await fetch("/api/csrf");
  if (!res.ok) throw new Error("Failed to load CSRF token");
  const data = await res.json();
  _csrfToken = data.csrf_token;
}

async function _fetch(method, url, body) {
  const opts = {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": _csrfToken,
    },
  };
  if (body !== undefined) opts.body = JSON.stringify(body);

  const res = await fetch(url, opts);

  if (res.status === 401) {
    window.location.href = "/auth/login";
    return;
  }

  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      if (j.error) msg = j.error;
    } catch (_) { /* ignore */ }
    throw new Error(msg);
  }

  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  getLists:        ()               => _fetch("GET",    "/api/lists"),
  getEntries:      (list)           => _fetch("GET",    `/api/entries?list=${encodeURIComponent(list)}`),
  addEntry:        (body)           => _fetch("POST",   "/api/entries", body),
  updateEntry:     (ip, body)       => _fetch("PUT",    `/api/entries/${encodeURIComponent(ip)}`, body),
  deleteEntry:     (ip, list)       => _fetch("DELETE", `/api/entries/${encodeURIComponent(ip)}?list=${encodeURIComponent(list)}`),
  getAudit:        (list, page, pp) => _fetch("GET",    `/api/audit?list=${encodeURIComponent(list)}&page=${page}&per_page=${pp}`),
  getHistory:      (ip)             => _fetch("GET",    `/api/history/${encodeURIComponent(ip)}`),
  getMe:           ()               => _fetch("GET",    "/api/me"),
};
