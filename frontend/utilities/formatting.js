/**
 * Formatting and utility helpers for QdrantCinema Discovery UI.
 */

/**
 * Converts an ISO 8601 timestamp (e.g. 2026-10-15T22:00:00Z) to a human-friendly format:
 * "Thu, 15 Oct · 10:00 PM"
 */
export function formatDateTime(isoString) {
  if (!isoString) return "Date TBA";

  try {
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return "Date TBA";

    const dateOptions = {
      weekday: "short",
      day: "numeric",
      month: "short",
    };
    const timeOptions = {
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    };

    const datePart = date.toLocaleDateString("en-IN", dateOptions);
    const timePart = date.toLocaleTimeString("en-IN", timeOptions);

    return `${datePart} · ${timePart}`;
  } catch (err) {
    return "Date TBA";
  }
}

/**
 * Formats price and currency in Indian Rupees (₹):
 * - Free if 0
 * - ₹250, ₹1,200, etc.
 */
export function formatPrice(price, currency = "INR") {
  if (price === 0 || price === "0") return "Free";
  if (price === null || price === undefined) return "Price TBA";

  const num = Number(price);
  if (isNaN(num)) return "Price TBA";

  return `₹${Math.round(num).toLocaleString("en-IN")}`;
}

/**
 * Cleans long titles to be concise and specific (e.g. "Dune: Part Two Special Screening" -> "Dune: Part Two").
 */
export function cleanDisplayTitle(title) {
  if (!title) return "Untitled";
  return String(title).trim();
}

/**
 * Formats search relevance / RRF score for display.
 */
export function formatScore(score) {
  if (score === null || score === undefined) return "";
  const num = Number(score);
  if (isNaN(num)) return "";
  return num.toFixed(3);
}

/**
 * Returns a distinct badge style / color class per category.
 */
export function getCategoryBadgeClass(category) {
  const cat = String(category || "").toLowerCase().trim();
  switch (cat) {
    case "comedy":
      return "badge-comedy";
    case "movies":
      return "badge-movies";
    case "concerts":
      return "badge-concerts";
    case "theatre":
      return "badge-theatre";
    case "sports":
      return "badge-sports";
    case "festivals":
      return "badge-festivals";
    case "workshops":
      return "badge-workshops";
    case "exhibitions":
      return "badge-exhibitions";
    case "activities":
      return "badge-activities";
    default:
      return "badge-default";
  }
}

/**
 * Simple HTML escaping for safe DOM text insertion.
 */
export function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
