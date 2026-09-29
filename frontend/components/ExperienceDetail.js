/**
 * ExperienceDetail Component
 *
 * Modal detail view displaying full information for a selected experience,
 * fetched via GET /api/experiences/{id}.
 */

import { apiClient } from "../api/client.js";
import {
  escapeHtml,
  formatDateTime,
  formatPrice,
  getCategoryBadgeClass,
} from "../utilities/formatting.js";

export class ExperienceDetail {
  constructor({ container, onClose }) {
    this.container = container;
    this.onClose = onClose;
    this.isOpen = false;
    this._handleKeyDown = this._handleKeyDown.bind(this);
  }

  async open(experienceSummary) {
    this.isOpen = true;
    document.body.classList.add("modal-open");
    window.addEventListener("keydown", this._handleKeyDown);

    // Initial render with summary data immediately
    this._renderModal(experienceSummary, true);

    // Fetch complete card details from API
    try {
      const fullExp = await apiClient.getExperienceById(experienceSummary.id);
      if (this.isOpen) {
        this._renderModal(fullExp, false);
      }
    } catch (err) {
      // If single item fetch fails, retain summary data without crashing
      console.warn("Could not fetch full details, showing summary:", err);
      if (this.isOpen) {
        this._renderModal(experienceSummary, false);
      }
    }
  }

  close() {
    this.isOpen = false;
    document.body.classList.remove("modal-open");
    window.removeEventListener("keydown", this._handleKeyDown);
    this.container.innerHTML = "";
    if (this.onClose) {
      this.onClose();
    }
  }

  _handleKeyDown(e) {
    if (e.key === "Escape") {
      this.close();
    }
  }

  _renderModal(exp, isLoadingFull = false) {
    if (!exp) return;

    const title = escapeHtml(exp.title || "Untitled Experience");
    const category = escapeHtml(exp.category || "Experience");
    const description = escapeHtml(exp.description || "");
    const venue = escapeHtml(exp.venue || "Venue TBA");
    const city = escapeHtml(exp.city || "");
    const neighborhood = escapeHtml(exp.neighborhood || "");
    const priceText = formatPrice(exp.price, exp.currency);
    const dateText = formatDateTime(exp.start_time);
    const endDateText = exp.end_time ? formatDateTime(exp.end_time) : null;
    const badgeClass = getCategoryBadgeClass(exp.category);
    const rating = exp.rating ? Number(exp.rating).toFixed(1) : null;
    const language = escapeHtml(exp.language || "");
    const imageUrl = exp.image_url || "";

    const subcats = Array.isArray(exp.subcategories) ? exp.subcategories : [];

    this.container.innerHTML = `
      <div class="modal-backdrop" id="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <div class="modal-container">
          <div class="modal-header">
            <button type="button" class="modal-back-btn" id="modal-back-btn" aria-label="Back to results">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="19" y1="12" x2="5" y2="12"></line>
                <polyline points="12 19 5 12 12 5"></polyline>
              </svg>
              <span>Back to Results</span>
            </button>
            <button type="button" class="modal-close-btn" id="modal-close-btn" aria-label="Close detail modal">✕</button>
          </div>

          <div class="modal-body">
            <div class="modal-media-wrapper">
              ${
                imageUrl
                  ? `<img
                      src="${escapeHtml(imageUrl)}"
                      alt="${title}"
                      class="modal-hero-image"
                      onerror="this.onerror=null; this.parentElement.classList.add('has-fallback-image'); this.style.display='none';"
                    />`
                  : ""
              }
              <div class="modal-fallback-badge" aria-hidden="true">
                <span>🎬</span>
              </div>
              <div class="modal-badges">
                <span class="category-badge ${badgeClass}">${category.toUpperCase()}</span>
                ${exp.is_indoor !== null && exp.is_indoor !== undefined
                  ? `<span class="setting-badge">${exp.is_indoor ? "Indoor" : "Outdoor"}</span>`
                  : ""}
              </div>
            </div>

            <div class="modal-content-details">
              <div class="modal-title-row">
                <h1 class="modal-title" id="modal-title">${title}</h1>
                ${rating ? `<div class="modal-rating">★ ${rating}</div>` : ""}
              </div>

              <div class="modal-pricing-bar">
                <div class="pricing-tag">
                  <span class="pricing-label">Admission</span>
                  <span class="pricing-value">${priceText}</span>
                </div>
                ${language ? `
                  <div class="pricing-tag">
                    <span class="pricing-label">Language</span>
                    <span class="pricing-value">${language}</span>
                  </div>
                ` : ""}
                ${exp.status ? `
                  <div class="pricing-tag">
                    <span class="pricing-label">Status</span>
                    <span class="pricing-value capitalize">${escapeHtml(exp.status)}</span>
                  </div>
                ` : ""}
              </div>

              <div class="modal-section">
                <h2 class="section-title">About this Experience</h2>
                <p class="modal-description">${description}</p>
              </div>

              <div class="modal-section">
                <h2 class="section-title">Schedule & Location</h2>
                <div class="detail-grid">
                  <div class="detail-item">
                    <span class="detail-icon">📅</span>
                    <div class="detail-info">
                      <span class="detail-heading">Date & Time</span>
                      <span class="detail-value">${dateText}</span>
                      ${endDateText ? `<span class="detail-subvalue">Until ${endDateText}</span>` : ""}
                    </div>
                  </div>

                  <div class="detail-item">
                    <span class="detail-icon">📍</span>
                    <div class="detail-info">
                      <span class="detail-heading">Venue</span>
                      <span class="detail-value">${venue}</span>
                      <span class="detail-subvalue">${[neighborhood, city].filter(Boolean).join(", ")}</span>
                    </div>
                  </div>
                </div>
              </div>

              ${
                subcats.length > 0
                  ? `
                <div class="modal-section">
                  <h2 class="section-title">Tags & Highlights</h2>
                  <div class="modal-tags">
                    ${subcats.map((tag) => `<span class="tag-pill">${escapeHtml(tag)}</span>`).join("")}
                  </div>
                </div>
              `
                  : ""
              }
            </div>
          </div>
        </div>
      </div>
    `;

    const closeBtn = this.container.querySelector("#modal-close-btn");
    const backBtn = this.container.querySelector("#modal-back-btn");
    const backdrop = this.container.querySelector("#modal-backdrop");

    closeBtn.addEventListener("click", () => this.close());
    backBtn.addEventListener("click", () => this.close());
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) {
        this.close();
      }
    });
  }
}
