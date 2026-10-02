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

  async getExperienceById(id) {
    if (id === undefined || id === null) {
      throw new ApiError("Experience ID is required.", "INVALID_ID", null, 400);
    }
    return this._request(`/api/experiences/${encodeURIComponent(id)}`, { method: "GET" });
  }

  async addBookmark(userId = "local-default", experienceId) {
    return this._request(`/api/users/${encodeURIComponent(userId)}/bookmarks/${encodeURIComponent(experienceId)}`, { method: "POST" });
  }

  async removeBookmark(userId = "local-default", experienceId) {
    return this._request(`/api/users/${encodeURIComponent(userId)}/bookmarks/${encodeURIComponent(experienceId)}`, { method: "DELETE" });
  }

  async listBookmarks(userId = "local-default") {
    return this._request(`/api/users/${encodeURIComponent(userId)}/bookmarks`, { method: "GET" });
  }

  async getUserPreferences(userId = "local-default") {
    return this._request(`/api/users/${encodeURIComponent(userId)}/preferences`, { method: "GET" });
  }

  async resetUserMemory(userId = "local-default") {
    return this._request(`/api/users/${encodeURIComponent(userId)}/memory`, { method: "DELETE" });
  }

  async recordInteraction(userId = "local-default", eventType, experienceId = null, query = null) {
    try {
      return await this._request(`/api/users/${encodeURIComponent(userId)}/interactions`, {
        method: "POST",
        body: JSON.stringify({ event_type: eventType, experience_id: experienceId, query }),
      });
    } catch (e) {
      console.debug("Non-blocking interaction log failed:", e);
      return null;
    }
  }

  async checkReady() {
    return this._request("/ready", { method: "GET" });
  }

  async getSyncStatus() {
    try {
      return await this._request("/api/sync/status", { method: "GET" });
    } catch (e) {
      console.debug("Failed to fetch sync status:", e);
      return null;
    }
  }

  async runSync(force = false) {
    return this._request(`/api/sync/run?force=${Boolean(force)}`, { method: "POST" });
  }

  async getReadyStatus() {
    try {
      return await this._request("/ready", { method: "GET" });
    } catch (e) {
      console.debug("Could not fetch ready status:", e);
      return null;
    }
  }

  async getMetrics() {
    try {
      return await this._request("/metrics", { method: "GET" });
    } catch (e) {
      console.debug("Could not fetch metrics:", e);
      return null;
    }
  }

  async getRoute({ start, destination }) {
    return this._request("/route", {
      method: "POST",
      body: JSON.stringify({ start, destination }),
    });
  }

  async getRoutingStatus() {
    try {
      return await this._request("/api/routing/status", { method: "GET" });
    } catch (e) {
      console.debug("Could not fetch routing status:", e);
      return null;
    }
  }

  async chat(message, context = {}) {
    return this._request("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message, context }),
    });
  }

  async getTrekAIStatus() {
    try {
      return await this._request("/api/chat/status", { method: "GET" });
    } catch (e) {
      console.debug("Could not fetch TrekAI status:", e);
      return null;
    }
  }

  async getTrekAIIntents() {
    try {
      return await this._request("/api/chat/intents", { method: "GET" });
    } catch (e) {
      console.debug("Could not fetch TrekAI intents:", e);
      return null;
    }
  }
}

export const apiClient = new ApiClient();
export default apiClient;