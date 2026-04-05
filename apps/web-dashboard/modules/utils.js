export function formatNumber(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return String(value);
  }
  return numeric.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

export function formatTimestamp(value) {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value);
  }
  return parsed.toLocaleString();
}

export function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#39;");
}

export function titleizeLabel(value) {
  return String(value || "-")
    .split("-")
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}

export function readInteger(input, fallback = 0) {
  const numeric = Number.parseInt(String(input.value || "").trim(), 10);
  if (!Number.isFinite(numeric) || numeric < 0) {
    return fallback;
  }
  return numeric;
}

export function readNumber(input, fallback = 0) {
  const numeric = Number.parseFloat(String(input.value || "").trim());
  if (!Number.isFinite(numeric) || numeric < 0) {
    return fallback;
  }
  return numeric;
}

export function splitList(value) {
  return String(value || "")
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function toLocalDateTimeValue(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}
