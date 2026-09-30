/**
 * Centralized Frontend Configuration for QdrantCinema Discovery UI.
 *
 * Configurable API Base URL:
 * - Checks window.__ENV__ (injected via deployment/environment)
 * - Checks localStorage override ('QDRANT_API_BASE_URL')
 * - Uses the current origin by default so frontend and API share one backend
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
    return "";
  }
  return "https://qdrantcity-2btt.onrender.com";
};

export const CONFIG = {
  API_BASE_URL: getApiBaseUrl(),
  APP_NAME: "QdrantCinema",
  APP_TAGLINE: "Offline-First City Experiences Discovery",
  DEFAULT_SEARCH_LIMIT: 10,
  SEARCH_TIMEOUT_MS: 10000,
};
