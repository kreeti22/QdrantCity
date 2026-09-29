/**
 * Centralized Frontend Configuration for QdrantCinema Discovery UI.
 *
 * Configurable API Base URL:
 * - Checks window.__ENV__ (injected via deployment/environment)
 * - Checks localStorage override ('QDRANT_API_BASE_URL')
 * - If running on same origin as backend (e.g. /ui), uses relative path ""
 * - Falls back to default http://localhost:8000
 */

const getApiBaseUrl = () => {
  if (typeof window !== "undefined") {
    if (window.__ENV__ && window.__ENV__.API_BASE_URL) {
      return window.__ENV__.API_BASE_URL;
    }
    const localOverride = localStorage.getItem("QDRANT_API_BASE_URL");
    if (localOverride) {
      return localOverride;
    }
    // If frontend is hosted directly on port 8000
    if (window.location.port === "8000" || window.location.pathname.startsWith("/ui")) {
      return "";
    }
  }
  return "http://localhost:8000";
};

export const CONFIG = {
  API_BASE_URL: getApiBaseUrl(),
  APP_NAME: "QdrantCinema",
  APP_TAGLINE: "Offline-First City Experiences Discovery",
  DEFAULT_SEARCH_LIMIT: 10,
  SEARCH_TIMEOUT_MS: 10000,
};
