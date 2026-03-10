/**
 * Utility helpers.
 */

export function escHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Format an ISO timestamp to a human-readable local string. */
export function fmtDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    year: "numeric", month: "short", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

/** Return "expired" / "today" / "N days" label for expires_at. */
export function expiryLabel(iso) {
  if (!iso) return "—";
  const ms = new Date(iso) - Date.now();
  if (ms < 0) return "expired";
  const days = Math.ceil(ms / 86_400_000);
  if (days === 0) return "today";
  return `${days}d`;
}

export function showBanner(msg, type = "error") {
  const banner = document.getElementById("banner");
  banner.textContent = msg;
  banner.className = `banner banner--${type}`;
  banner.hidden = false;
  clearTimeout(banner._timer);
  banner._timer = setTimeout(() => (banner.hidden = true), 6000);
}

export function hideBanner() {
  const banner = document.getElementById("banner");
  banner.hidden = true;
}
