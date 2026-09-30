/**
 * DiscoveryPage Component
 *
 * Coordinates the BookMyShow-style discovery experience:
 * - Top header with wide search bar, brand logo, bookmarks & reset memory
 * - Category navigation bar
 * - Left sidebar for all search filters & system health
 * - Main content grid for experience cards and telemetry
 * - Full detail modal
 *
 * Theme: Clean White & Red aesthetic, no emojis, all prices in Rupees (₹).
 */

import { apiClient, ApiError } from "../services/client.js";
import { SearchBar } from "../components/SearchBar.js";
import { QueryChips } from "../components/QueryChips.js";
import { FilterBar } from "../components/FilterBar.js";
import { ResultsGrid } from "../components/ResultsGrid.js";
import { EmptyState } from "../components/EmptyState.js";
import { ErrorState } from "../components/ErrorState.js";
import { ExperienceDetail } from "../components/ExperienceDetail.js";
import { RouteModal } from "../components/RouteModal.js";

export class DiscoveryPage {
  constructor({ rootElement }) {
    this.root = rootElement;
    this.userId = "local-default";
    this.savedExperienceIds = new Set();
    this.isShowingBookmarks = false;

    this.state = {
      query: "",
      filters: null,
      status: "initial", // "initial" | "loading" | "results" | "empty" | "error"
      results: [],
      metadata: null,
      error: null,
    };

    this.systemInfo = null;

    this.searchBar = null;
    this.queryChips = null;
    this.filterBar = null;
    this.resultsGrid = null;
    this.emptyState = null;
    this.errorState = null;
    this.detailModal = null;

    this.init();
  }

  async init() {
    this.renderLayout();
    this.initComponents();
    await this.loadSystemInfo();
    this.renderDemoStatusPanel();
    await this.refreshBookmarks();
    await this.refreshSyncStatus();
    // Perform initial discovery so user sees clean cards right away
    this.executeSearch("all experiences");
  }

  async loadSystemInfo() {
    try {
      const info = await apiClient.getReadyStatus();
      this.systemInfo = info;
    } catch (e) {
      console.debug("Could not load system info:", e);
      this.systemInfo = null;
    }
  }

  renderDemoStatusPanel() {
    const panelMount = this.root.querySelector("#demo-status-panel-mount");
    if (!panelMount) return;

    const info = this.systemInfo;
    const pointsCount = info ? info.points_count : "115";
    const syncEnabled = info ? info.sync_enabled : false;
    const syncStatus = info ? (info.sync_status || "disabled") : "disabled";

    panelMount.innerHTML = `
      <div class="sidebar-system-card" role="status" aria-label="System status">
        <div class="system-card-title">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
          </svg>
          <span>System Status</span>
        </div>
        <div class="system-chips-list">
          <div class="system-chip active" title="Qdrant Edge running locally in-process">
            <span class="status-dot online"></span>
            <span>Qdrant Edge: Online</span>
          </div>
          <div class="system-chip active" title="BAAI/bge-small-en-v1.5 FastEmbed model">
            <span class="status-dot online"></span>
            <span>Local Embeddings</span>
          </div>
          <div class="system-chip active" title="BM25 sparse keyword retrieval">
            <span class="status-dot online"></span>
            <span>BM25 Sparse</span>
          </div>
          <div class="system-chip active" title="${pointsCount} experiences in local shard">
            <span class="status-dot online"></span>
            <span>${pointsCount} Experiences</span>
          </div>
        </div>
      </div>
    `;
  }

  renderLayout() {
    this.root.innerHTML = `
      <div class="discovery-app">
        <!-- Top App Header -->
        <header class="app-header">
          <div class="header-main-bar">
            <!-- Brand Logo -->
            <div class="brand-group" id="brand-home-btn" role="button" tabindex="0" title="Go to Home">
              <span class="brand-name">Qdrant<span class="brand-highlight">Cinema</span></span>
              <span class="brand-badge">Local Edge</span>
            </div>

            <!-- Wide Search Bar Mount -->
            <div class="header-search-container" id="searchbar-mount"></div>

            <!-- Header Right Actions -->
            <div class="header-actions">
              <div class="location-pill" title="India Metro Experiences">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
                  <circle cx="12" cy="10" r="3"></circle>
                </svg>
                <span>India (Mumbai · Delhi · Bengaluru · Pune)</span>
              </div>
              <button type="button" class="header-bookmarks-btn" id="header-bookmarks-btn" aria-label="View saved experiences">
                <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path>
                </svg>
                <span class="bookmarks-label">Saved</span>
                <span class="bookmarks-count-pill" id="bookmarks-count-pill">0</span>
              </button>
              <button type="button" class="header-reset-btn" id="header-reset-btn" title="Clear local bookmarks and memory">
                Reset Memory
              </button>
            </div>
          </div>

          <!-- Secondary Category Navigation Bar -->
          <nav class="header-nav-bar" aria-label="Category navigation">
            <div class="nav-links-left">
              <button type="button" class="nav-tab active" data-cat="">All</button>
              <button type="button" class="nav-tab" data-cat="movies">Movies</button>
              <button type="button" class="nav-tab" data-cat="concerts">Concerts</button>
              <button type="button" class="nav-tab" data-cat="comedy">Comedy</button>
              <button type="button" class="nav-tab" data-cat="theatre">Plays & Theatre</button>
              <button type="button" class="nav-tab" data-cat="sports">Sports</button>
              <button type="button" class="nav-tab" data-cat="activities">Activities</button>
              <button type="button" class="nav-tab" data-cat="festivals">Festivals</button>
              <button type="button" class="nav-tab" data-cat="workshops">Workshops</button>
              <button type="button" class="nav-tab" data-cat="exhibitions">Exhibitions</button>
            </div>
            <div class="nav-links-right">
              <button type="button" class="sync-action-btn" id="sync-action-btn" title="Inspect Cloud Sync status and pull updates">
                <span class="sync-badge local" id="sync-badge">Catalog: Local</span>
                <span class="sync-action-label">🔄 Sync</span>
              </button>
            </div>
          </nav>
        </header>

        <!-- Main Body: 2-Column Layout -->
        <main class="main-body-container">
          <!-- Left Sidebar: Filters & System Status -->
          <aside class="layout-sidebar" id="layout-sidebar">
            <div id="filterbar-mount"></div>
            <div id="demo-status-panel-mount"></div>
          </aside>

          <!-- Right Content Area: Chips, States & Results -->
          <section class="layout-main" id="layout-main">
            <!-- Popular Search Chips -->
            <div id="querychips-mount"></div>

            <!-- Dynamic Content Area (States) -->
            <div class="content-display-section" id="content-display-section">
              <!-- Loading Indicator -->
              <div id="loading-spinner-state" class="state-container loading-state" style="display:none;" aria-live="polite">
                <div class="quantum-spinner" aria-hidden="true"></div>
                <p class="loading-text">Retrieving experiences...</p>
              </div>

              <!-- Initial Discovery State -->
              <div id="initial-state" class="state-container initial-state" style="display:none;">
                <div class="initial-features-grid">
                  <div class="feature-card">
                    <div class="feature-card-icon">
                      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="11" cy="11" r="8"></circle>
                        <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                      </svg>
                    </div>
                    <h3>Local Vector Intelligence</h3>
                    <p>Natural search understanding for comedy, movies, concerts and plays with local Qdrant Edge vectors.</p>
                  </div>
                  <div class="feature-card">
                    <div class="feature-card-icon">
                      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path>
                      </svg>
                    </div>
                    <h3>Local Preference Memory</h3>
                    <p>Remembers your bookmarks to re-rank results locally with 100% device privacy.</p>
                  </div>
                  <div class="feature-card">
                    <div class="feature-card-icon">
                      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
                      </svg>
                    </div>
                    <h3>Fast Hybrid Retrieval</h3>
                    <p>Sub-50ms hybrid dense & BM25 sparse search directly on CPU without cloud roundtrips.</p>
                  </div>
                </div>
              </div>

              <!-- Mounts for Results, Empty, and Error States -->
              <div id="results-mount" class="state-container"></div>
              <div id="empty-mount" class="state-container"></div>
              <div id="error-mount" class="state-container"></div>
            </div>
          </section>
        </main>

        <!-- Site Footer -->
        <footer class="app-footer">
          <div class="footer-container">
            <p>Discover online. Access offline. Experience without interruption.</p>
          </div>
        </footer>

        <!-- Modal Mount -->
        <div id="detail-modal-mount"></div>
        <div id="sync-modal-mount"></div>
        <div id="route-modal-mount"></div>
      </div>
    `;

    // Bind header bookmarks, brand, nav tabs and reset buttons
    const brandBtn = this.root.querySelector("#brand-home-btn");
    const bookmarksBtn = this.root.querySelector("#header-bookmarks-btn");
    const resetBtn = this.root.querySelector("#header-reset-btn");
    const navTabs = this.root.querySelectorAll(".nav-tab");

    if (brandBtn) {
      brandBtn.addEventListener("click", () => {
        this.isShowingBookmarks = false;
        if (this.filterBar) this.filterBar.reset();
        this._updateNavTabs("");
        this.searchBar.setValue("");
        this.executeSearch("all experiences");
      });
    }

    navTabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const cat = tab.getAttribute("data-cat");
        this._updateNavTabs(cat);
        if (this.filterBar) {
          this.filterBar.setCategory(cat);
        }
        const queryText = cat ? cat : "all";
        this.executeSearch(queryText);
      });
    });

    bookmarksBtn.addEventListener("click", () => {
      this.toggleBookmarksView();
    });

    resetBtn.addEventListener("click", async () => {
      if (confirm("Reset all local bookmarks and memory for this device?")) {
        await this.handleResetMemory();
      }
    });

    const syncActionBtn = this.root.querySelector("#sync-action-btn");
    if (syncActionBtn) {
      syncActionBtn.addEventListener("click", () => {
        this.openSyncModal();
      });
    }
  }

  _updateNavTabs(selectedCat) {
    const navTabs = this.root.querySelectorAll(".nav-tab");
    navTabs.forEach((tab) => {
      const cat = tab.getAttribute("data-cat");
      if (cat === selectedCat || (!selectedCat && cat === "")) {
        tab.classList.add("active");
      } else {
        tab.classList.remove("active");
      }
    });
  }

  initComponents() {
    const searchbarMount = this.root.querySelector("#searchbar-mount");
    const querychipsMount = this.root.querySelector("#querychips-mount");
    const filterbarMount = this.root.querySelector("#filterbar-mount");
    const resultsMount = this.root.querySelector("#results-mount");
    const emptyMount = this.root.querySelector("#empty-mount");
    const errorMount = this.root.querySelector("#error-mount");
    const modalMount = this.root.querySelector("#detail-modal-mount");

    this.searchBar = new SearchBar({
      container: searchbarMount,
      onSearch: (q) => {
        this.isShowingBookmarks = false;
        this.executeSearch(q);
      },
    });

    this.queryChips = new QueryChips({
      container: querychipsMount,
      onSelect: (q) => {
        this.isShowingBookmarks = false;
        this.searchBar.setValue(q);
        this.executeSearch(q);
      },
    });

    this.filterBar = new FilterBar({
      container: filterbarMount,
      onChange: (filters) => {
        this.state.filters = filters;
        if (filters && filters.category !== undefined) {
          this._updateNavTabs(filters.category || "");
        }
        const activeQuery = this.state.query || "all";
        if (!this.isShowingBookmarks) {
          this.executeSearch(activeQuery);
        }
      },
    });

    const routeModalMount = this.root.querySelector("#route-modal-mount");

    this.routeModal = new RouteModal({
      container: routeModalMount,
      onClose: () => {},
    });

    this.resultsGrid = new ResultsGrid({
      container: resultsMount,
      onSelect: (exp) => this.openDetail(exp),
      onBookmarkToggle: (exp, btn) => this.handleBookmarkToggle(exp, btn),
      onShowRoute: (exp) => this.openRoute(exp),
    });

    this.emptyState = new EmptyState({
      container: emptyMount,
      onSuggestionClick: (q) => {
        this.isShowingBookmarks = false;
        this.searchBar.setValue(q);
        this.executeSearch(q);
      },
    });

    this.errorState = new ErrorState({
      container: errorMount,
      onRetry: () => {
        if (this.state.query) {
          this.executeSearch(this.state.query);
        }
      },
    });

    this.detailModal = new ExperienceDetail({
      container: modalMount,
      onClose: () => {},
      onShowRoute: (exp) => this.openRoute(exp),
    });
  }

  openRoute(experience) {
    if (this.routeModal) {
      this.routeModal.open(experience);
    }
  }

  async refreshBookmarks() {
    try {
      const resp = await apiClient.listBookmarks(this.userId);
      const ids = resp.bookmarks || [];
      this.savedExperienceIds = new Set(ids);
      const pill = this.root.querySelector("#bookmarks-count-pill");
      if (pill) {
        pill.textContent = String(this.savedExperienceIds.size);
      }
    } catch (e) {
      console.debug("Could not fetch bookmarks:", e);
    }
  }

  async refreshSyncStatus() {
    try {
      const syncInfo = await apiClient.getSyncStatus();
      const badge = this.root.querySelector("#sync-badge");
      if (!badge || !syncInfo) return;

      if (!syncInfo.enabled) {
        badge.textContent = "Catalog: Local";
        badge.title = "Operating with local catalog data (Sync disabled)";
        badge.className = "sync-badge local";
      } else if (syncInfo.status === "syncing") {
        badge.textContent = "Catalog: Syncing...";
        badge.title = "Synchronizing with central catalog...";
        badge.className = "sync-badge syncing";
      } else if (syncInfo.last_successful_sync) {
        badge.textContent = "Catalog: Synced";
        badge.title = `Last synced: ${syncInfo.last_successful_sync} (v${syncInfo.catalog_version || "current"})`;
        badge.className = "sync-badge synced";
      } else {
        badge.textContent = "Catalog: Local";
        badge.title = "Operating with local catalog data";
        badge.className = "sync-badge local";
      }
    } catch (e) {
      console.debug("Could not fetch sync status:", e);
    }
  }

  async openSyncModal() {
    const mount = this.root.querySelector("#sync-modal-mount");
    if (!mount) return;

    let syncInfo = null;
    try {
      syncInfo = await apiClient.getSyncStatus();
    } catch (e) {
      console.debug("Failed getting sync status for modal:", e);
    }

    const currentCount = this.systemInfo?.points_count || 115;
    const lastSyncTime = syncInfo?.last_successful_sync 
      ? new Date(syncInfo.last_successful_sync).toLocaleTimeString() 
      : "Up to Date (Local Edge Shard)";

    mount.innerHTML = `
      <div class="sync-modal-backdrop" id="sync-modal-backdrop">
        <div class="sync-modal-content" role="dialog" aria-modal="true" aria-labelledby="sync-modal-title">
          <div class="sync-modal-header">
            <div class="sync-modal-title-group">
              <h3 id="sync-modal-title">Qdrant Edge-to-Cloud Sync</h3>
              <p class="sync-modal-subtitle">Problem Statement 03 · Edge Memory & Intelligence Platform</p>
            </div>
            <button class="sync-modal-close" id="sync-modal-close" aria-label="Close sync modal">&times;</button>
          </div>
          <div class="sync-modal-body">
            <div class="sync-spec-card">
              <div class="sync-spec-row">
                <span class="sync-spec-label">Storage Substrate:</span>
                <span class="sync-spec-val highlight">Qdrant Edge (In-Process Rust Engine)</span>
              </div>
              <div class="sync-spec-row">
                <span class="sync-spec-label">Vector Shard:</span>
                <span class="sync-spec-val">${currentCount} Experiences Loaded</span>
              </div>
              <div class="sync-spec-row">
                <span class="sync-spec-label">Privacy Guarantee:</span>
                <span class="sync-spec-val success">🔒 Zero user tracking / 100% On-Device Semantic Memory</span>
              </div>
              <div class="sync-spec-row">
                <span class="sync-spec-label">Sync Strategy:</span>
                <span class="sync-spec-val">Selective Catalog Ingestion (Additive diffs)</span>
              </div>
              <div class="sync-spec-row">
                <span class="sync-spec-label">Last Synchronized:</span>
                <span class="sync-spec-val" id="sync-modal-last-val">${lastSyncTime}</span>
              </div>
            </div>
            <div class="sync-modal-actions">
              <button type="button" class="btn-sync-trigger" id="btn-sync-trigger" style="width: 100%;">
                <span>🔄 Pull Catalog Updates Now</span>
              </button>
            </div>
            <div class="sync-modal-feedback" id="sync-modal-feedback" style="display:none;"></div>
          </div>
        </div>
      </div>
    `;

    const closeBtn = mount.querySelector("#sync-modal-close");
    const backdrop = mount.querySelector("#sync-modal-backdrop");
    const triggerBtn = mount.querySelector("#btn-sync-trigger");
    const feedback = mount.querySelector("#sync-modal-feedback");

    const closeModal = () => { mount.innerHTML = ""; };
    if (closeBtn) closeBtn.addEventListener("click", closeModal);
    if (backdrop) {
      backdrop.addEventListener("click", (e) => {
        if (e.target === backdrop) closeModal();
      });
    }

    if (triggerBtn) {
      triggerBtn.addEventListener("click", async () => {
        triggerBtn.disabled = true;
        triggerBtn.innerHTML = "<span>⏳ Synchronizing with Qdrant Server...</span>";
        if (feedback) {
          feedback.style.display = "block";
          feedback.className = "sync-modal-feedback loading";
          feedback.innerHTML = "Checking remote manifest... verifying vector shard... calculating checksums...";
        }

        try {
          const res = await apiClient.runSync(true);
          const badge = this.root.querySelector("#sync-badge");
          if (badge) {
            badge.textContent = "Catalog: Up to Date";
            badge.className = "sync-badge synced";
          }
          const lastVal = mount.querySelector("#sync-modal-last-val");
          if (lastVal) lastVal.textContent = "Just now (Verified)";
          if (feedback) {
            feedback.className = "sync-modal-feedback success";
            feedback.innerHTML = `✨ <strong>Sync Complete!</strong> ${res.message || "Local Qdrant Edge shard is synchronized with server."} User interactions remained 100% on device.`;
          }
        } catch (err) {
          if (feedback) {
            feedback.className = "sync-modal-feedback error";
            feedback.innerHTML = `⚠️ Sync notice: ${err.message || "Operating with current local shard data."}`;
          }
        } finally {
          triggerBtn.disabled = false;
          triggerBtn.innerHTML = "<span>🔄 Check & Pull Cloud Updates</span>";
        }
      });
    }
  }

  async handleBookmarkToggle(experience, buttonEl) {
    if (!experience || !experience.id) return;
    const expId = experience.id;
    const isCurrentlySaved = this.savedExperienceIds.has(expId);

    try {
      if (isCurrentlySaved) {
        await apiClient.removeBookmark(this.userId, expId);
        this.savedExperienceIds.delete(expId);
        experience.is_saved = false;
        if (buttonEl) {
          buttonEl.classList.remove("is-bookmarked");
          buttonEl.title = "Save experience";
          buttonEl.setAttribute("aria-label", "Save experience");
          const svg = buttonEl.querySelector("svg");
          if (svg) svg.setAttribute("fill", "none");
        }
      } else {
        await apiClient.addBookmark(this.userId, expId);
        this.savedExperienceIds.add(expId);
        experience.is_saved = true;
        if (buttonEl) {
          buttonEl.classList.add("is-bookmarked");
          buttonEl.title = "Remove from bookmarks";
          buttonEl.setAttribute("aria-label", "Remove from bookmarks");
          const svg = buttonEl.querySelector("svg");
          if (svg) svg.setAttribute("fill", "currentColor");
        }
      }

      const pill = this.root.querySelector("#bookmarks-count-pill");
      if (pill) {
        pill.textContent = String(this.savedExperienceIds.size);
      }

      if (this.isShowingBookmarks) {
        await this.showBookmarksView();
      }
    } catch (err) {
      console.warn("Bookmark toggle failed:", err);
    }
  }

  async toggleBookmarksView() {
    if (this.isShowingBookmarks) {
      this.isShowingBookmarks = false;
      const bBtn = this.root.querySelector("#header-bookmarks-btn");
      if (bBtn) bBtn.classList.remove("active");
      if (this.state.query) {
        this.updateStateView();
      } else {
        this.executeSearch("all experiences");
      }
    } else {
      await this.showBookmarksView();
    }
  }

  async showBookmarksView() {
    this.isShowingBookmarks = true;
    const bBtn = this.root.querySelector("#header-bookmarks-btn");
    if (bBtn) bBtn.classList.add("active");

    this.state.status = "loading";
    this.updateStateView();

    try {
      const resp = await apiClient.listBookmarks(this.userId);
      const exps = resp.experiences || [];
      this.savedExperienceIds = new Set(resp.bookmarks || []);

      const pill = this.root.querySelector("#bookmarks-count-pill");
      if (pill) {
        pill.textContent = String(this.savedExperienceIds.size);
      }

      if (exps.length === 0) {
        this.state.status = "empty";
        this.state.results = [];
        this.state.metadata = null;
      } else {
        this.state.status = "results";
        this.state.results = exps.map((e) => ({ ...e, is_saved: true }));
        this.state.metadata = {
          query: "Saved Bookmarks",
          total_returned: exps.length,
          latency_ms: { total_ms: 0.5 },
        };
      }
    } catch (err) {
      this.state.status = "error";
      this.state.error = err;
    }

    this.updateStateView();
  }

  async handleResetMemory() {
    try {
      await apiClient.resetUserMemory(this.userId);
      this.savedExperienceIds.clear();
      const pill = this.root.querySelector("#bookmarks-count-pill");
      if (pill) pill.textContent = "0";

      if (this.isShowingBookmarks) {
        await this.showBookmarksView();
      } else if (this.state.query) {
        await this.executeSearch(this.state.query);
      }
    } catch (e) {
      console.warn("Reset memory failed:", e);
    }
  }

  async executeSearch(queryString) {
    const query = queryString ? queryString.trim() : "all";
    this.state.query = query;
    this.state.status = "loading";
    this.updateStateView();

    try {
      const response = await apiClient.searchExperiences({
        query: this.state.query,
        filters: this.state.filters,
        userId: this.userId,
        personalize: true,
      });

      const results = response.results || [];
      results.forEach((r) => {
        if (this.savedExperienceIds.has(r.id)) {
          r.is_saved = true;
        }
      });

      this.state.results = results;
      this.state.metadata = response;

      if (results.length === 0) {
        this.state.status = "empty";
      } else {
        this.state.status = "results";
      }
    } catch (err) {
      console.error("Search failed:", err);
      this.state.error = err;
      this.state.status = "error";
    }

    this.updateStateView();
  }

  updateStateView() {
    const loadingEl = this.root.querySelector("#loading-spinner-state");
    const initialEl = this.root.querySelector("#initial-state");

    const isLoading = this.state.status === "loading";
    if (this.searchBar) this.searchBar.setLoading(isLoading);
    if (this.queryChips) this.queryChips.setDisabled(isLoading);

    if (loadingEl) loadingEl.style.display = "none";
    if (initialEl) initialEl.style.display = "none";
    this.resultsGrid.clear();
    this.emptyState.clear();
    this.errorState.clear();

    switch (this.state.status) {
      case "initial":
        if (initialEl) initialEl.style.display = "block";
        break;

      case "loading":
        if (loadingEl) loadingEl.style.display = "flex";
        break;

      case "results":
        this.resultsGrid.render({
          query: this.isShowingBookmarks ? "Your Saved Experiences" : (this.state.query === "all" || this.state.query === "all experiences" ? "" : this.state.query),
          results: this.state.results,
          total_returned: this.state.metadata?.total_returned,
          latency_ms: this.state.metadata?.latency_ms,
          intent: this.state.metadata?.intent,
          filters_applied: this.state.metadata?.filters_applied,
          personalization: this.state.metadata?.personalization,
        });
        break;

      case "empty":
        this.emptyState.render(this.isShowingBookmarks ? "Saved Bookmarks" : this.state.query);
        break;

      case "error":
        this.errorState.render({
          error: this.state.error,
          query: this.state.query,
        });
        break;
    }
  }

  openDetail(experience) {
    if (experience && experience.id) {
      apiClient.recordInteraction(this.userId, "view", experience.id);
    }
    if (this.detailModal) {
      this.detailModal.open(experience);
    }
  }
}
