/**
 * ErrorState Component — Phase 3F: UX Polish
 *
 * Friendly error presentation with safe error message display,
 * retry action, and example query shortcuts so users can recover easily.
 */

import { escapeHtml } from "../utilities/formatting.js";

const RECOVERY_QUERIES = [
  { label: "Comedy Tonight", query: "comedy tonight" },
  { label: "Movies This Weekend", query: "movies this weekend" },
  { label: "Live Music", query: "live music events" },
];

export class ErrorState {
  constructor({ container, onRetry }) {
    this.container = container;
    this.onRetry = onRetry;
  }

  render({ error, query, onSuggestionClick }) {
    // Display user-friendly message — never expose stack traces or internal details
    const rawMessage =
      error && error.message ? error.message : "An unexpected error occurred while searching.";

    // Truncate overly long messages for safety
    const message =
      rawMessage.length > 200 ? rawMessage.slice(0, 200) + "…" : rawMessage;

    const isRateLimit =
      (error && error.code === "RATE_LIMITED") ||
      message.toLowerCase().includes("rate") ||
      message.toLowerCase().includes("too many");

    const isOffline =
      message.toLowerCase().includes("fetch") ||
      message.toLowerCase().includes("network") ||
      message.toLowerCase().includes("failed to fetch");

    let hint = "";
    if (isRateLimit) {
      hint = `<p class="error-hint">⏳ You've made many requests recently. Please wait a moment before searching again.</p>`;
    } else if (isOffline) {
      hint = `<p class="error-hint">📡 Cannot reach the local server. Make sure the backend is running on <code>http://localhost:8000</code>.</p>`;
    }

    this.container.innerHTML = `
      <div class="error-state" role="alert">
        <div class="error-icon" aria-hidden="true">⚠️</div>
        <div class="error-content">
          <h3 class="error-title">Unable to Complete Search</h3>
          <p class="error-message">${escapeHtml(message)}</p>
          ${hint}
          ${
            query
              ? `<p class="error-query-preserved">Query was: <code>${escapeHtml(query)}</code></p>`
              : ""
          }
          <div class="error-actions">
            <button type="button" class="error-retry-btn" id="error-retry-btn">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="23 4 23 10 17 10"></polyline>
                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
              </svg>
              <span>Try Again</span>
            </button>
          </div>
          <div class="error-recovery">
            <p class="suggestions-label">Or try one of these searches:</p>
            <div class="empty-query-chips">
              ${RECOVERY_QUERIES.map(
                (e) =>
                  `<button type="button" class="empty-action-btn" data-query="${escapeHtml(e.query)}">${escapeHtml(e.label)}</button>`
              ).join("")}
            </div>
          </div>
        </div>
      </div>
    `;

    const retryBtn = this.container.querySelector("#error-retry-btn");
    if (retryBtn) {
      retryBtn.addEventListener("click", () => {
        if (this.onRetry) {
          this.onRetry();
        }
      });
    }

    if (onSuggestionClick) {
      this.container.querySelectorAll(".empty-action-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const q = btn.getAttribute("data-query");
          if (q) onSuggestionClick(q);
        });
      });
    }
  }

  clear() {
    this.container.innerHTML = "";
  }
}
