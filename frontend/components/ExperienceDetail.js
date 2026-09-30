/**
 * ExperienceDetail Component
 *
 * Modal detail view displaying full comprehensive information for a selected experience.
 * Fully styled in clean white & red BookMyShow aesthetic without emojis.
 */

import { apiClient } from "../api/client.js";
import { ExperienceCard } from "./ExperienceCard.js";
import {
  escapeHtml,
  formatDateTime,
  formatPrice,
  getCategoryBadgeClass,
} from "../utilities/formatting.js";

export class ExperienceDetail {
  constructor({ container, onClose, onShowRoute }) {
    this.container = container;
    this.onClose = onClose;
    this.onShowRoute = onShowRoute;
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

    const rawTitle = exp.title || "Untitled Experience";
    const cleanTitle = ExperienceCard.formatCardTitle(rawTitle);
    const title = escapeHtml(cleanTitle);
    const subtitle = cleanTitle !== rawTitle ? escapeHtml(rawTitle) : "";
    const category = escapeHtml(exp.category || "Experience");
    const description = escapeHtml(exp.description || "No description provided.");
    const venue = escapeHtml(exp.venue || "Venue TBA");
    const city = escapeHtml(exp.city || "");
    const neighborhood = escapeHtml(exp.neighborhood || "");
    const state = escapeHtml(exp.state || "");
    const priceText = formatPrice(exp.price, exp.currency);
    const dateText = formatDateTime(exp.start_time);
    const endDateText = exp.end_time ? formatDateTime(exp.end_time) : null;
    const badgeClass = getCategoryBadgeClass(exp.category);
    const rating = exp.rating ? Number(exp.rating).toFixed(1) : null;
    const language = escapeHtml(exp.language || "English / Hindi");
    const imageUrl = exp.image_url || "";
    const sourceUrl = exp.source_url ? escapeHtml(exp.source_url) : "";
    const imageCredit = exp.image_credit ? escapeHtml(exp.image_credit) : "";
    const lastVerified = exp.last_verified ? escapeHtml(exp.last_verified) : "2026-09";
    const isDemo = exp.demo_data === true;

    const subcats = Array.isArray(exp.subcategories) ? exp.subcategories : [];
    const locationParts = [venue];
    if (neighborhood) locationParts.push(neighborhood);
    if (city) locationParts.push(city);
    if (state) locationParts.push(state);
    const locationFull = locationParts.filter(Boolean).join(", ");

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
            <button type="button" class="modal-close-btn" id="modal-close-btn" aria-label="Close detail modal">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
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
                <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="2" y="2" width="20" height="20" rx="3" ry="3"></rect>
                  <line x1="7" y1="2" x2="7" y2="22"></line>
                  <line x1="17" y1="2" x2="17" y2="22"></line>
                  <line x1="2" y1="12" x2="22" y2="12"></line>
                  <line x1="2" y1="7" x2="7" y2="7"></line>
                  <line x1="2" y1="17" x2="7" y2="17"></line>
                  <line x1="17" y1="17" x2="22" y2="17"></line>
                  <line x1="17" y1="7" x2="22" y2="7"></line>
                </svg>
              </div>
              <div class="modal-badges">
                <span class="category-badge ${badgeClass}">${category.toUpperCase()}</span>
                ${
                  exp.is_indoor !== null && exp.is_indoor !== undefined
                    ? `<span class="setting-badge">${exp.is_indoor ? "Indoor" : "Outdoor"}</span>`
                    : ""
                }
                ${isDemo ? `<span class="setting-badge" title="Illustrative event example">DEMO DATA</span>` : ""}
              </div>
            </div>

            <div class="modal-content-details">
              <div class="modal-title-row">
                <div class="modal-title-group">
                  <h1 class="modal-title" id="modal-title">${title}</h1>
                  ${subtitle ? `<div class="modal-subtitle">${subtitle}</div>` : ""}
                </div>
                ${
                  rating
                    ? `<div class="modal-rating">
                        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" stroke="none">
                          <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>
                        </svg>
                        <span>${rating} / 5</span>
                       </div>`
                    : ""
                }
              </div>

              <div class="modal-pricing-bar">
                <div class="pricing-tag">
                  <span class="pricing-label">Price</span>
                  <span class="pricing-value highlight-red">${priceText}</span>
                </div>
                <div class="pricing-tag">
                  <span class="pricing-label">City / State</span>
                  <span class="pricing-value">${city}${state ? `, ${state}` : ""}</span>
                </div>
                <div class="pricing-tag">
                  <span class="pricing-label">Language</span>
                  <span class="pricing-value">${language}</span>
                </div>
                <div class="pricing-action">
                  <button type="button" class="btn-detail-route" id="btn-detail-route" title="Calculate local route to this venue">
                    <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                      <polygon points="3 11 22 2 13 21 11 13 3 11"></polygon>
                    </svg>
                    <span>Show Route</span>
                  </button>
                  <button type="button" class="btn-book-now" id="btn-book-now" onclick="alert('Booking initiated for ${escapeHtml(title)}!')">
                    Book Experience
                  </button>
                </div>
              </div>

              <div class="modal-section">
                <h2 class="section-title">About this Experience</h2>
                <p class="modal-description">${description}</p>
              </div>

              <div class="modal-section">
                <h2 class="section-title">Schedule & Location</h2>
                <div class="detail-grid">
                  <div class="detail-item">
                    <div class="detail-icon-circle">
                      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                        <line x1="16" y1="2" x2="16" y2="6"></line>
                        <line x1="8" y1="2" x2="8" y2="6"></line>
                        <line x1="3" y1="10" x2="21" y2="10"></line>
                      </svg>
                    </div>
                    <div class="detail-info">
                      <span class="detail-heading">Date & Time</span>
                      <span class="detail-value">${dateText}</span>
                      ${endDateText ? `<span class="detail-subvalue">Ends: ${endDateText}</span>` : ""}
                    </div>
                  </div>

                  <div class="detail-item">
                    <div class="detail-icon-circle">
                      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
                        <circle cx="12" cy="10" r="3"></circle>
                      </svg>
                    </div>
                    <div class="detail-info">
                      <span class="detail-heading">Venue & Address</span>
                      <span class="detail-value">${venue}</span>
                      <span class="detail-subvalue">${locationFull}</span>
                    </div>
                  </div>

                  ${
                    exp.latitude !== undefined && exp.latitude !== null && exp.longitude !== undefined && exp.longitude !== null
                      ? `<div class="detail-item">
                          <div class="detail-icon-circle">
                            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                              <circle cx="12" cy="12" r="10"></circle>
                              <line x1="2" y1="12" x2="22" y2="12"></line>
                              <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
                            </svg>
                          </div>
                          <div class="detail-info">
                            <span class="detail-heading">Coordinates & Type</span>
                            <span class="detail-value">${Number(exp.latitude).toFixed(4)}, ${Number(exp.longitude).toFixed(4)}</span>
                            <span class="detail-subvalue">${(exp.type || (exp.category === "movies" ? "movie" : "event")).toUpperCase()} · Local OSM Mapped</span>
                          </div>
                        </div>`
                      : ""
                  }
                </div>
              </div>

              ${
                subcats.length > 0
                  ? `
                <div class="modal-section">
                  <h2 class="section-title">Categories & Tags</h2>
                  <div class="modal-tags">
                    ${subcats.map((tag) => `<span class="tag-pill">${escapeHtml(tag)}</span>`).join("")}
                  </div>
                </div>
              `
                  : ""
              }

              <!-- Verification & Attribution -->
              <div class="modal-section modal-attribution-section">
                <div class="attribution-row">
                  ${sourceUrl ? `<span><strong>Source:</strong> <a href="${sourceUrl}" target="_blank" rel="noopener noreferrer" class="attribution-link">${sourceUrl}</a></span> · ` : ""}
                  ${imageCredit ? `<span><strong>Image Credit:</strong> ${imageCredit}</span> · ` : ""}
                  <span><strong>Verified:</strong> ${lastVerified}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;

    const closeBtn = this.container.querySelector("#modal-close-btn");
    const backBtn = this.container.querySelector("#modal-back-btn");
    const backdrop = this.container.querySelector("#modal-backdrop");
    const routeBtn = this.container.querySelector("#btn-detail-route");

    if (closeBtn) closeBtn.addEventListener("click", () => this.close());
    if (backBtn) backBtn.addEventListener("click", () => this.close());
    if (routeBtn) {
      routeBtn.addEventListener("click", () => {
        if (this.onShowRoute) {
          this.onShowRoute(exp);
        }
      });
    }
    if (backdrop) {
      backdrop.addEventListener("click", (e) => {
        if (e.target === backdrop) {
          this.close();
        }
      });
    }
  }
}
