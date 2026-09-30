/**
 * ProfileModal Component
 *
 * Dedicated User Profile & On-Device Memory Center:
 * - Real-time learned taste profile (category affinities, top subcategories, price preference)
 * - Saved Experiences collection with instant Route calculation
 * - Quick memory reset for judge live demo
 * - 100% on-device privacy telemetry
 */

import { apiClient } from "../services/client.js";
import { escapeHtml, formatPrice } from "../utilities/formatting.js";

export class ProfileModal {
  constructor({ container, userId = "local-default", onRoute, onBookmarkChange }) {
    this.container = container;
    this.userId = userId;
    this.onRoute = onRoute;
    this.onBookmarkChange = onBookmarkChange;
    this.isOpen = false;
    this.activeTab = "taste"; // 'taste' | 'saved'
    this.preferences = null;
    this.savedExperiences = [];
    this._handleKeyDown = this._handleKeyDown.bind(this);
  }

  async open(initialTab = "taste") {
    this.activeTab = initialTab;
    this.isOpen = true;
    document.body.classList.add("modal-open");
    window.addEventListener("keydown", this._handleKeyDown);

    await this.loadData();
    this.render();
  }

  close() {
    this.isOpen = false;
    document.body.classList.remove("modal-open");
    window.removeEventListener("keydown", this._handleKeyDown);
    this.container.innerHTML = "";
  }

  _handleKeyDown(e) {
    if (e.key === "Escape") {
      this.close();
    }
  }

  async loadData() {
    try {
      const [prefData, bookmarkData] = await Promise.all([
        apiClient.getUserPreferences(this.userId).catch(() => null),
        apiClient.listBookmarks(this.userId).catch(() => ({ experiences: [], bookmarks: [] })),
      ]);
      this.preferences = prefData;
      this.savedExperiences = bookmarkData.experiences || [];
    } catch (err) {
      console.warn("Failed loading profile data:", err);
    }
  }

  render() {
    const savedCount = this.savedExperiences.length;
    const pref = this.preferences || {};
    const categories = pref.preferred_categories || {};
    const subcats = pref.preferred_subcategories || {};
    const totalInteractions = pref.total_interactions || 0;
    const priceAvg = pref.preferred_price_avg ? Math.round(pref.preferred_price_avg) : null;
    const indoorPref = pref.preferred_indoor;

    const topCategories = Object.entries(categories)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 4);

    const topSubcats = Object.entries(subcats)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8);

    this.container.innerHTML = `
      <div class="modal-backdrop" id="profile-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="profile-modal-title">
        <div class="modal-container profile-modal-container">
          <!-- Profile Header -->
          <div class="modal-header profile-modal-header">
            <div class="profile-header-user">
              <div class="profile-avatar-large">
                <svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor">
                  <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"></path>
                </svg>
              </div>
              <div class="profile-user-info">
                <div class="profile-title-row">
                  <h2 class="profile-modal-title" id="profile-modal-title">My Edge Profile</h2>
                  <span class="profile-privacy-badge">100% ON-DEVICE</span>
                </div>
                <p class="profile-user-meta">User ID: <code>${escapeHtml(this.userId)}</code> · Learned In-Process via SQLite & Qdrant Edge</p>
              </div>
            </div>
            <button type="button" class="modal-close-btn" id="profile-modal-close-btn" aria-label="Close profile">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
          </div>

          <!-- Profile Nav Tabs -->
          <div class="profile-tabs-bar">
            <button type="button" class="profile-tab-btn ${this.activeTab === "taste" ? "active" : ""}" id="tab-btn-taste">
              <span>Learned Taste Profile</span>
            </button>
            <button type="button" class="profile-tab-btn ${this.activeTab === "saved" ? "active" : ""}" id="tab-btn-saved">
              <span>Saved Collection (${savedCount})</span>
            </button>
          </div>

          <!-- Profile Body -->
          <div class="profile-modal-body">
            ${this.activeTab === "taste" ? this._renderTasteTab(topCategories, topSubcats, totalInteractions, priceAvg, indoorPref) : this._renderSavedTab()}
          </div>
        </div>
      </div>
    `;

    this._bindEvents();
  }

  _renderTasteTab(topCategories, topSubcats, totalInteractions, priceAvg, indoorPref) {
    const hasHistory = topCategories.length > 0 || topSubcats.length > 0;

    return `
      <div class="taste-tab-content">
        <!-- Privacy & Edge Intelligence Banner -->
        <div class="profile-info-banner">
          <div class="banner-text">
            <strong>Adaptive Edge Personalization</strong>
            <p>Every time you bookmark movies or venues, QdrantCity dynamically adapts your local vector recommendations in real time on your device. Zero user data leaves your machine.</p>
          </div>
        </div>

        ${
          !hasHistory
            ? `
          <div class="profile-empty-history">
            <h3>No learned preferences yet</h3>
            <p>Save experiences (like horror movies or mystery rooms) to see your local taste profile adapt live!</p>
          </div>
        `
            : `
          <!-- Categories & Affinities -->
          <div class="profile-metrics-grid">
            <div class="profile-section-card">
              <h4 class="card-section-title">Top Category Affinities</h4>
              <div class="affinity-bars-list">
                ${topCategories
                  .map(([cat, weight]) => {
                    const pct = Math.round(weight * 100);
                    return `
                      <div class="affinity-bar-item">
                        <div class="bar-label-row">
                          <span class="bar-cat-name">${escapeHtml(cat.toUpperCase())}</span>
                          <span class="bar-pct">${pct}%</span>
                        </div>
                        <div class="bar-track">
                          <div class="bar-fill" style="width: ${pct}%;"></div>
                        </div>
                      </div>
                    `;
                  })
                  .join("")}
              </div>
            </div>

            <div class="profile-section-card">
              <h4 class="card-section-title">Personalized Attributes</h4>
              <div class="profile-stats-list">
                <div class="profile-stat-item">
                  <span class="stat-name">Total On-Device Events</span>
                  <span class="stat-value highlight">${totalInteractions} interactions</span>
                </div>
                <div class="profile-stat-item">
                  <span class="stat-name">Price Sweet Spot</span>
                  <span class="stat-value">${priceAvg ? `~₹${priceAvg}` : "Any price"}</span>
                </div>
                <div class="profile-stat-item">
                  <span class="stat-name">Setting Preference</span>
                  <span class="stat-value">${indoorPref === true ? "Indoor Preferred" : indoorPref === false ? "Outdoor / Open-Air" : "Flexible"}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Top Subcategories / Interests Chips -->
          ${
            topSubcats.length > 0
              ? `
            <div class="profile-section-card full-width">
              <h4 class="card-section-title">Learned Affinity Tags (Guides Hybrid Re-ranking)</h4>
              <div class="profile-subcat-chips">
                ${topSubcats
                  .map(([sub, score]) => `
                    <span class="taste-chip">
                      <span class="chip-name">#${escapeHtml(sub)}</span>
                      <span class="chip-score">${(score * 100).toFixed(0)}%</span>
                    </span>
                  `)
                  .join("")}
              </div>
            </div>
          `
              : ""
          }
        `
        }

        <!-- Reset Button -->
        <div class="profile-footer-actions">
          <button type="button" class="btn-profile-reset" id="btn-profile-reset" title="Purge local memory and reset taste to default">
            <span>Reset Learned Memory</span>
          </button>
          <span class="reset-help-text">Instantly reset your learned taste back to baseline for live demo testing.</span>
        </div>
      </div>
    `;
  }

  _renderSavedTab() {
    if (this.savedExperiences.length === 0) {
      return `
        <div class="profile-empty-saved">
          <h3>Your saved collection is empty</h3>
          <p>Click the bookmark icon on any movie, party, or event card to save it locally.</p>
        </div>
      `;
    }

    return `
      <div class="saved-tab-content">
        <div class="saved-items-list">
          ${this.savedExperiences
            .map((exp) => {
              const title = escapeHtml(exp.title || "Experience");
              const venue = escapeHtml(exp.venue || "");
              const city = escapeHtml(exp.city || "Delhi");
              const priceText = formatPrice(exp.price, exp.currency);
              const hasCoords = exp.latitude !== undefined && exp.latitude !== null;

              return `
                <div class="saved-item-card" data-id="${exp.id}">
                  <div class="saved-item-info">
                    <span class="saved-item-category">${escapeHtml((exp.category || "Event").toUpperCase())}</span>
                    <h4 class="saved-item-title">${title}</h4>
                    <span class="saved-item-venue">${venue}, ${city} · <strong>${priceText}</strong></span>
                  </div>
                  <div class="saved-item-actions">
                    ${
                      hasCoords
                        ? `
                      <button type="button" class="saved-action-route-btn" data-action="route" data-id="${exp.id}" title="Show local route">
                        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                          <polygon points="3 11 22 2 13 21 11 13 3 11"></polygon>
                        </svg>
                        <span>Route</span>
                      </button>
                    `
                        : ""
                    }
                    <button type="button" class="saved-action-remove-btn" data-action="remove" data-id="${exp.id}" title="Remove from saved">
                      <span>Remove</span>
                    </button>
                  </div>
                </div>
              `;
            })
            .join("")}
        </div>
      </div>
    `;
  }

  _bindEvents() {
    const backdrop = this.container.querySelector("#profile-modal-backdrop");
    const closeBtn = this.container.querySelector("#profile-modal-close-btn");

    if (closeBtn) closeBtn.addEventListener("click", () => this.close());
    if (backdrop) {
      backdrop.addEventListener("click", (e) => {
        if (e.target === backdrop) this.close();
      });
    }

    // Tab buttons
    const tabTaste = this.container.querySelector("#tab-btn-taste");
    const tabSaved = this.container.querySelector("#tab-btn-saved");

    if (tabTaste) {
      tabTaste.addEventListener("click", () => {
        this.activeTab = "taste";
        this.render();
      });
    }
    if (tabSaved) {
      tabSaved.addEventListener("click", () => {
        this.activeTab = "saved";
        this.render();
      });
    }

    // Reset Memory Button
    const resetBtn = this.container.querySelector("#btn-profile-reset");
    if (resetBtn) {
      resetBtn.addEventListener("click", async () => {
        if (confirm("Reset local memory and learned taste back to baseline?")) {
          try {
            await apiClient.resetUserMemory(this.userId);
            this.savedExperiences = [];
            this.preferences = null;
            if (this.onBookmarkChange) {
              this.onBookmarkChange();
            }
            await this.loadData();
            this.render();
          } catch (e) {
            console.warn("Reset memory failed:", e);
          }
        }
      });
    }

    // Saved Items Actions (Route & Remove)
    this.container.querySelectorAll(".saved-action-route-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const id = parseInt(btn.getAttribute("data-id"), 10);
        const exp = this.savedExperiences.find((x) => x.id === id);
        if (exp && this.onRoute) {
          this.close();
          this.onRoute(exp);
        }
      });
    });

    this.container.querySelectorAll(".saved-action-remove-btn").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const id = parseInt(btn.getAttribute("data-id"), 10);
        try {
          await apiClient.removeBookmark(this.userId, id);
          this.savedExperiences = this.savedExperiences.filter((x) => x.id !== id);
          if (this.onBookmarkChange) {
            this.onBookmarkChange();
          }
          await this.loadData();
          this.render();
        } catch (err) {
          console.warn("Remove bookmark failed:", err);
        }
      });
    });
  }
}
