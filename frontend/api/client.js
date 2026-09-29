/**
 * Centralized API Client for QdrantCinema Backend.
 *
 * Implements communication with:
 * - POST /api/experiences/search
 * - GET  /api/experiences/{id}
 * - GET  /ready
 */

import { CONFIG } from "../config.js";

export class ApiError extends Error {
  constructor(message, code = "UNKNOWN_ERROR", details = null, status = 500) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.details = details;
    this.status = status;
  }
}

class ApiClient {
  constructor(baseUrl = CONFIG.API_BASE_URL) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
  }

  /**
   * Helper to execute fetch with timeout and structured error extraction.
   */
  async _request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), CONFIG.SEARCH_TIMEOUT_MS);

    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal,
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          ...(options.headers || {}),
        },
      });

      clearTimeout(timeout);

      let data;
      const contentType = response.headers.get("content-type");
      if (contentType && contentType.includes("application/json")) {
        data = await response.json();
      } else {
        const text = await response.text();
        data = { detail: text };
      }

      if (!response.ok) {
        let code = "API_ERROR";
        let message = `Request failed with status ${response.status}`;
        let details = null;

        if (data && data.error) {
          code = data.error.code || code;
          message = data.error.message || message;
          details = data.error.details || null;
        } else if (data && data.detail) {
          message = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
        }

        throw new ApiError(message, code, details, response.status);
      }

      return data;
    } catch (err) {
      clearTimeout(timeout);
      if (err instanceof ApiError) {
        throw err;
      }
      if (err.name === "AbortError") {
        throw new ApiError("Request timed out. Please check your network or backend server.", "TIMEOUT", null, 408);
      }
      throw new ApiError(
        err.message || "Failed to communicate with QdrantCinema backend.",
        "NETWORK_ERROR",
        null,
        0
      );
    }
  }

  /**
   * Natural language discovery search.
   *
   * @param {Object} params
   * @param {string} params.query - Natural-language query string
   * @param {number} [params.limit=10] - Number of results to return
   * @param {string} [params.mode='hybrid'] - Search mode: 'hybrid', 'dense', or 'bm25'
   * @param {boolean} [params.enable_intent=true] - Whether to apply deterministic query intent
   * @param {Object|null} [params.filters=null] - Optional structured filter overrides
   */
  async searchExperiences({
    query,
    limit = CONFIG.DEFAULT_SEARCH_LIMIT,
    mode = "hybrid",
    enable_intent = true,
    filters = null,
    userId = "local-default",
    personalize = true,
  }) {
    if (!query || typeof query !== "string" || !query.trim()) {
      throw new ApiError("Please enter a search query.", "INVALID_QUERY", null, 400);
    }

    const payload = {
      query: query.trim(),
      limit,
      mode,
      enable_intent,
      user_id: userId,
      personalize,
    };

    if (filters && Object.keys(filters).length > 0) {
      payload.filters = filters;
    }

    return this._request("/api/experiences/search", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  /**
   * Retrieves single experience card details by ID.
   *
   * @param {number|string} id - The experience identifier
   */
  async getExperienceById(id) {
    if (id === undefined || id === null) {
      throw new ApiError("Experience ID is required.", "INVALID_ID", null, 400);
    }
    return this._request(`/api/experiences/${encodeURIComponent(id)}`, {
      method: "GET",
    });
  }

  /**
   * Saves experience to user bookmarks.
   */
  async addBookmark(userId = "local-default", experienceId) {
    return this._request(`/api/users/${encodeURIComponent(userId)}/bookmarks/${encodeURIComponent(experienceId)}`, {
      method: "POST",
    });
  }

  /**
   * Removes experience from user bookmarks.
   */
  async removeBookmark(userId = "local-default", experienceId) {
    return this._request(`/api/users/${encodeURIComponent(userId)}/bookmarks/${encodeURIComponent(experienceId)}`, {
      method: "DELETE",
    });
  }

  /**
   * Lists all bookmarked experiences for user.
   */
  async listBookmarks(userId = "local-default") {
    return this._request(`/api/users/${encodeURIComponent(userId)}/bookmarks`, {
      method: "GET",
    });
  }

  /**
   * Retrieves current inferred user preference profile.
   */
  async getUserPreferences(userId = "local-default") {
    return this._request(`/api/users/${encodeURIComponent(userId)}/preferences`, {
      method: "GET",
    });
  }

  /**
   * Resets local user memory, bookmarks, and preferences.
   */
  async resetUserMemory(userId = "local-default") {
    return this._request(`/api/users/${encodeURIComponent(userId)}/memory`, {
      method: "DELETE",
    });
  }

  /**
   * Logs a lightweight user interaction (e.g. view or search).
   */
  async recordInteraction(userId = "local-default", eventType, experienceId = null, query = null) {
    try {
      return await this._request(`/api/users/${encodeURIComponent(userId)}/interactions`, {
        method: "POST",
        body: JSON.stringify({
          event_type: eventType,
          experience_id: experienceId,
          query,
        }),
      });
    } catch (e) {
      // Non-blocking telemetry
      console.debug("Non-blocking interaction log failed:", e);
      return null;
    }
  }

  /**
   * Probes backend readiness.
   */
  async checkReady() {
    return this._request("/ready", {
      method: "GET",
    });
  }

  /**
   * Retrieves synchronization status and checkpoint metrics.
   */
  async getSyncStatus() {
    try {
      return await this._request("/api/sync/status", {
        method: "GET",
      });
    } catch (e) {
      console.debug("Failed to fetch sync status:", e);
      return null;
    }
  }

  /**
   * Triggers a manual synchronization cycle.
   */
  async runSync(force = false) {
    return this._request(`/api/sync/run?force=${Boolean(force)}`, {
      method: "POST",
    });
  }

  /**
   * Phase 3F: Gets system readiness info for demo status panel.
   */
  async getReadyStatus() {
    try {
      return await this._request("/ready", { method: "GET" });
    } catch (e) {
      console.debug("Could not fetch ready status:", e);
      return null;
    }
  }

  /**
   * Phase 3D: Gets operational metrics (privacy-safe aggregate data).
   */
  async getMetrics() {
    try {
      return await this._request("/metrics", { method: "GET" });
    } catch (e) {
      console.debug("Could not fetch metrics:", e);
      return null;
    }
  }
}

export const apiClient = new ApiClient();
export default apiClient;

