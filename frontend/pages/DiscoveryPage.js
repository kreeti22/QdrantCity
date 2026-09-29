/**
 * DiscoveryPage Component
 *
 * Coordinates the single-page discovery experience:
 * - Search bar & query chips
 * - Filter controls
 * - Bookmarks management & local personalization (Phase 2C)
 * - Loading, results, empty, error, and saved experiences states
 * - Card selection and detail modal
 */

import { apiClient, ApiError } from "../api/client.js";
import { SearchBar } from "../components/SearchBar.js";
import { QueryChips } from "../components/QueryChips.js";
import { FilterBar } from "../components/FilterBar.js";
import { ResultsGrid } from "../components/ResultsGrid.js";
import { EmptyState } from "../components/EmptyState.js";
import { ErrorState } from "../components/ErrorState.js";
import { ExperienceDetail } from "../components/ExperienceDetail.js";

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

    // Phase 3F: System info for demo panel
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
    // Load system info for demo panel, then render it
    await this.loadSystemInfo();
    this.renderDemoStatusPanel();
    await this.refreshBookmarks();
    await this.refreshSyncStatus();
  }

  /** Phase 3F: Load system readiness info for demo status panel */
  async loadSystemInfo() {
    try {
      const info = await apiClient.getReadyStatus();
      this.systemInfo = info;
    } catch (e) {
      console.debug("Could not load system info:", e);
      this.systemInfo = null;
    }
  }

  /** Phase 3F: Render demo status panel showing system capabilities */
  renderDemoStatusPanel() {
    const panelMount = this.root.querySelector("#demo-status-panel-mount");
    if (!panelMount) return;

    const info = this.systemInfo;
    const pointsCount = info ? info.points_count : "—";
    const syncEnabled = info ? info.sync_enabled : false;
    const syncStatus = info ? (info.sync_status || "disabled") : "unknown";

    panelMount.innerHTML = `
      <div class="demo-status-panel" role="status" aria-label="System status">
        <span class="demo-status-title">⚡ System Status</span>
        <span class="demo-status-chip active" title="Qdrant Edge running locally in-process">🗄️ Qdrant Edge: Online</span>
        <span class="demo-status-chip active" title="BAAI/bge-small-en-v1.5 FastEmbed model">🧠 Local Embeddings</span>
        <span class="demo-status-chip active" title="BM25 sparse keyword retrieval">📋 BM25 Sparse</span>
        <span class="demo-status-chip active" title="${pointsCount} experiences in local shard">🎯 ${pointsCount} Experiences</span>
        <span class="demo-status-chip ${syncEnabled ? "active" : "inactive"}" title="Edge-to-server catalog sync">
          ${syncEnabled ? `🔄 Sync: ${syncStatus}` : "🔄 Sync: Disabled"}
        </span>
      </div>
    `;
  }

  renderLayout() {
    this.root.innerHTML = `
      <div class="discovery-app">
        <!-- Site Header -->
        <header class="app-header">
          <div class="header-container">
            <div class="brand-group">
              <div class="brand-logo" aria-hidden="true">🎬</div>
              <div class="brand-text">
                <span class="brand-name">QdrantCinema</span>
                <span class="brand-badge">Local Edge</span>
              </div>
            </div>
            
            <div class="header-actions">
              <span class="sync-badge local" id="sync-badge" title="Operating with local catalog data">
                Catalog: Local data
              </span>
              <span class="privacy-badge" title="All bookmarks, interactions, and preference profiles are stored locally in SQLite">
                🔒 Local Device Memory
              </span>
              <button type="button" class="header-bookmarks-btn" id="header-bookmarks-btn" aria-label="View saved experiences">
                <span class="bookmark-icon">🔖</span>
                <span class="bookmarks-label">Saved</span>
                <span class="bookmarks-count-pill" id="bookmarks-count-pill">0</span>
              </button>
              <button type="button" class="header-reset-btn" id="header-reset-btn" title="Clear local bookmarks and interaction history">
                Reset Memory
              </button>
            </div>
          </div>
        </header>

        <!-- Hero & Search Section -->
        <main class="main-content">
          <section class="search-hero-section">
            <div class="hero-container">
              <h1 class="hero-headline">Find movies, comedy, concerts & city adventures</h1>
              <p class="hero-subhead">Describe what you feel like doing naturally — our local intelligence takes care of the rest.</p>
              
              <div id="searchbar-mount"></div>
              <div id="querychips-mount"></div>
              <div id="filterbar-mount"></div>
            </div>
          </section>

          <!-- Phase 3F: Demo Status Panel (filled in by renderDemoStatusPanel) -->
          <div id="demo-status-panel-mount"></div>

          <!-- Dynamic Content Area (States) -->
          <section class="content-display-section" id="content-display-section">
            <!-- Loading Indicator -->
            <div id="loading-spinner-state" class="state-container loading-state" style="display:none;" aria-live="polite">
              <div class="quantum-spinner" aria-hidden="true"></div>
              <p class="loading-text">Discovering local experiences with Qdrant Edge...</p>
            </div>

            <!-- Initial Discovery State -->
            <div id="initial-state" class="state-container initial-state">
              <div class="initial-features-grid">
                <div class="feature-card">
                  <span class="feature-icon">🧠</span>
                  <h3>Local Query Understanding</h3>
                  <p>Understands "comedy tonight under $50" or "IMAX movies this weekend" deterministically without cloud LLMs.</p>
                </div>
                <div class="feature-card">
                  <span class="feature-icon">✨</span>
                  <h3>Durable Semantic Memory</h3>
                  <p>Remembers your bookmarks and past interactions to subtly boost ranking locally without telemetry or trackers.</p>
                </div>
                <div class="feature-card">
                  <span class="feature-icon">🔒</span>
                  <h3>100% Offline & Private</h3>
                  <p>All embeddings, search queries, SQLite preferences, and shard indexes execute directly on your local device.</p>
                </div>
              </div>
            </div>

            <!-- Mounts for Results, Empty, and Error States -->
            <div id="results-mount" class="state-container"></div>
            <div id="empty-mount" class="state-container"></div>
            <div id="error-mount" class="state-container"></div>
          </section>
        </main>

        <!-- Footer -->
        <footer class="app-footer">
          <div class="footer-container">
            <p>QdrantCinema · Offline-First Intelligence Substrate · Local FastEmbed & native Qdrant Edge shard · SQLite User Memory</p>
          </div>
        </footer>

        <!-- Modal Mount -->
        <div id="detail-modal-mount"></div>
      </div>
    `;

    // Bind header bookmarks and reset buttons
    const bookmarksBtn = this.root.querySelector("#header-bookmarks-btn");
    const resetBtn = this.root.querySelector("#header-reset-btn");

    bookmarksBtn.addEventListener("click", () => {
      this.toggleBookmarksView();
    });

    resetBtn.addEventListener("click", async () => {
      if (confirm("Reset all local bookmarks and interaction preferences for this device?")) {
        await this.handleResetMemory();
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
        if (this.state.query && !this.isShowingBookmarks) {
          this.executeSearch(this.state.query);
        }
      },
    });

    this.resultsGrid = new ResultsGrid({
      container: resultsMount,
      onSelect: (exp) => this.openDetail(exp),
      onBookmarkToggle: (exp, btn) => this.handleBookmarkToggle(exp, btn),
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
      onClose: () => {
        // detail closed
      },
    });
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
        badge.textContent = "Catalog: Local data";
        badge.title = "Operating with local catalog data (Sync disabled)";
        badge.className = "sync-badge local";
      } else if (syncInfo.status === "syncing") {
        badge.textContent = "Catalog: Syncing...";
        badge.title = "Synchronizing with central catalog...";
        badge.className = "sync-badge syncing";
      } else if (syncInfo.last_successful_sync) {
        badge.textContent = "Catalog: Up to date";
        badge.title = `Last synced: ${syncInfo.last_successful_sync} (v${syncInfo.catalog_version || "current"})`;
        badge.className = "sync-badge synced";
      } else {
        badge.textContent = "Catalog: Local data";
        badge.title = "Operating with local catalog data";
        badge.className = "sync-badge local";
      }
    } catch (e) {
      console.debug("Could not fetch sync status:", e);
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

      // If we are currently in bookmarks view, refresh it
      if (this.isShowingBookmarks) {
        await this.showBookmarksView();
      }
    } catch (err) {
      console.warn("Bookmark toggle failed:", err);
    }
  }

  async toggleBookmarksView() {
    if (this.isShowingBookmarks) {
      // Toggle back to search view
      this.isShowingBookmarks = false;
      const bBtn = this.root.querySelector("#header-bookmarks-btn");
      if (bBtn) bBtn.classList.remove("active");
      if (this.state.query) {
        this.updateStateView();
      } else {
        this.state.status = "initial";
        this.updateStateView();
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
    const query = queryString ? queryString.trim() : "";
    if (!query) return;

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
      // Synchronize is_saved with local set
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
    const resultsMount = this.root.querySelector("#results-mount");
    const emptyMount = this.root.querySelector("#empty-mount");
    const errorMount = this.root.querySelector("#error-mount");

    const isLoading = this.state.status === "loading";
    this.searchBar.setLoading(isLoading);
    this.queryChips.setDisabled(isLoading);

    // Hide all states first
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
          query: this.isShowingBookmarks ? "Your Saved Experiences" : this.state.query,
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
    // Record view interaction in local storage
    if (experience && experience.id) {
      apiClient.recordInteraction(this.userId, "view", experience.id);
    }
    if (this.detailModal) {
      this.detailModal.open(experience);
    }
  }
}
