/**
 * RouteModal Component
 *
 * Displays local OpenStreetMap route visualization between user start location
 * and selected event/movie destination venue.
 * Features:
 * - Local Delhi OSM road graph routing with online OSRM fallback
 * - Prominent "LOCAL OSM ROUTE" / "ONLINE ROUTE" status badge
 * - Start location selector (GPS geolocation or Connaught Place / Delhi presets)
 * - Interactive Leaflet map with offline-safe vector polyline rendering
 * - Required "Map data © OpenStreetMap contributors" attribution
 */

import { apiClient } from "../services/client.js";
import { escapeHtml } from "../utilities/formatting.js";

export const START_PRESETS = [
  { name: "Connaught Place (Central Delhi)", lat: 28.6315, lon: 77.2167, isDefault: true },
  { name: "India Gate (New Delhi)", lat: 28.6129, lon: 77.2295 },
  { name: "Hauz Khas Village (South Delhi)", lat: 28.5535, lon: 77.1942 },
  { name: "Civil Lines (North Delhi)", lat: 28.6830, lon: 77.2150 },
];

const DELHI_MAP_BOUNDS = [[28.25, 76.85], [28.95, 77.55]];
const DELHI_MAP_CENTER = [28.6139, 77.2090];

function isInDelhi(lat, lon) {
  return lat >= DELHI_MAP_BOUNDS[0][0] && lat <= DELHI_MAP_BOUNDS[1][0]
    && lon >= DELHI_MAP_BOUNDS[0][1] && lon <= DELHI_MAP_BOUNDS[1][1];
}

export class RouteModal {
  constructor({ container, onClose }) {
    this.container = container;
    this.onClose = onClose;
    this.isOpen = false;
    this.activeExperience = null;
    this.startLocation = START_PRESETS[0];
    this.mapInstance = null;
    this._handleKeyDown = this._handleKeyDown.bind(this);

    this._initGeolocation();
  }

  _initGeolocation() {
    if (typeof navigator !== "undefined" && navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          const { latitude, longitude } = pos.coords;
          if (isInDelhi(latitude, longitude)) {
            this.gpsLocation = {
              name: "My Current Location (GPS)",
              lat: latitude,
              lon: longitude,
              isGps: true,
            };
            this.startLocation = this.gpsLocation;
            console.log("Acquired Delhi device geolocation:", this.gpsLocation);
          } else {
            console.warn("Device location is outside the Delhi map area; using Delhi fallback.");
          }
        },
        (err) => {
          console.warn("Geolocation unavailable or denied, using Delhi Connaught Place fallback:", err.message);
        },
        { timeout: 4000, maximumAge: 60000 }
      );
    }
  }

  async open(experience) {
    if (!experience) return;
    this.activeExperience = experience;
    this.isOpen = true;
    document.body.classList.add("modal-open");
    window.addEventListener("keydown", this._handleKeyDown);

    this._renderModal();
    await this.calculateAndRenderRoute();
  }

  close() {
    this.isOpen = false;
    document.body.classList.remove("modal-open");
    window.removeEventListener("keydown", this._handleKeyDown);
    if (this.mapInstance) {
      try {
        this.mapInstance.remove();
      } catch (e) {
        // ignore
      }
      this.mapInstance = null;
    }
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

  _renderModal() {
    const exp = this.activeExperience;
    const title = escapeHtml(exp.title || "Selected Destination");
    const venue = escapeHtml(exp.venue || "Venue Location");
    const city = escapeHtml(exp.city || "Delhi");
    const destLat = exp.latitude ?? 28.6139;
    const destLon = exp.longitude ?? 77.2090;

    this.container.innerHTML = `
      <div class="modal-backdrop" id="route-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="route-modal-title">
        <div class="modal-container route-modal-container">
          <div class="modal-header route-modal-header">
            <div class="route-header-titles">
              <span class="route-modal-eyebrow">OFFLINE-FIRST EVENT LOCATION LOCATOR</span>
              <h2 class="route-modal-title" id="route-modal-title">Route to ${title}</h2>
            </div>
            <button type="button" class="modal-close-btn" id="route-modal-close-btn" aria-label="Close route modal">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
          </div>

          <div class="route-modal-body">
            <!-- Route Control Bar -->
            <div class="route-control-panel">
              <div class="route-point-row">
                <div class="point-indicator start-indicator" aria-hidden="true"></div>
                <div class="point-details">
                  <span class="point-label">START / ORIGIN</span>
                  <div class="point-selector-wrapper">
                    <select id="route-start-select" class="route-start-dropdown">
                      ${this.gpsLocation ? `<option value="gps" selected>📍 My Current Location (${this.gpsLocation.lat.toFixed(4)}, ${this.gpsLocation.lon.toFixed(4)})</option>` : ""}
                      ${START_PRESETS.map((p, idx) => `
                        <option value="${idx}" ${(!this.gpsLocation && p.isDefault) ? "selected" : ""}>
                          📍 ${p.name}
                        </option>
                      `).join("")}
                    </select>
                  </div>
                </div>
              </div>

              <div class="route-connector-line" aria-hidden="true"></div>

              <div class="route-point-row">
                <div class="point-indicator dest-indicator" aria-hidden="true"></div>
                <div class="point-details">
                  <span class="point-label">DESTINATION VENUE</span>
                  <span class="point-value">${venue}, ${city} (${destLat.toFixed(4)}, ${destLon.toFixed(4)})</span>
                </div>
              </div>
            </div>

            <!-- Route Telemetry Banner -->
            <div id="route-telemetry-banner" class="route-telemetry-banner loading">
              <div class="spinner-small" aria-hidden="true"></div>
              <span>Computing route using local Delhi OpenStreetMap road graph...</span>
            </div>

            <!-- Map View Container -->
            <div class="route-map-wrapper">
              <div id="route-map-canvas" class="route-map-canvas"></div>
              <div class="map-attribution-badge">
                Map data © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors
              </div>
            </div>
          </div>
        </div>
      </div>
    `;

    // Event Listeners
    const closeBtn = this.container.querySelector("#route-modal-close-btn");
    if (closeBtn) closeBtn.addEventListener("click", () => this.close());

    const backdrop = this.container.querySelector("#route-modal-backdrop");
    if (backdrop) {
      backdrop.addEventListener("click", (e) => {
        if (e.target === backdrop) this.close();
      });
    }

    const startSelect = this.container.querySelector("#route-start-select");
    if (startSelect) {
      startSelect.addEventListener("change", (e) => {
        const val = e.target.value;
        if (val === "gps" && this.gpsLocation) {
          this.startLocation = this.gpsLocation;
        } else {
          const idx = parseInt(val, 10);
          if (START_PRESETS[idx]) {
            this.startLocation = START_PRESETS[idx];
          }
        }
        this.calculateAndRenderRoute();
      });
    }
  }

  async calculateAndRenderRoute() {
    const banner = this.container.querySelector("#route-telemetry-banner");
    const mapCanvas = this.container.querySelector("#route-map-canvas");
    if (!banner || !this.activeExperience) return;

    banner.className = "route-telemetry-banner loading";
    banner.innerHTML = `
      <div class="spinner-small" aria-hidden="true"></div>
      <span>Querying local Delhi OSM road network...</span>
    `;

    const exp = this.activeExperience;
    const destLat = exp.latitude ?? 28.6139;
    const destLon = exp.longitude ?? 77.2090;
    const startLat = this.startLocation.lat;
    const startLon = this.startLocation.lon;

    if (!isInDelhi(destLat, destLon)) {
      banner.className = "route-telemetry-banner error";
      banner.innerHTML = "<span>Routing is currently available only for destinations in Delhi.</span>";
      this._renderDelhiMap(mapCanvas);
      return;
    }

    try {
      const res = await apiClient.getRoute({
        start: { latitude: startLat, longitude: startLon },
        destination: { latitude: destLat, longitude: destLon },
      });

      const distKm = (res.distance_m / 1000.0).toFixed(1);
      const durMin = Math.max(1, Math.round((res.duration_s || res.distance_m / 8.33) / 60.0));
      const isLocal = res.source === "local_osm";
      const sourceBadgeClass = isLocal ? "badge-local" : (res.source === "online_osrm" ? "badge-online" : "badge-fallback");
      const sourceLabel = isLocal ? "LOCAL OSM ROUTE" : (res.source === "online_osrm" ? "ONLINE ROUTE FALLBACK" : "DIRECT LOCAL ROUTE");

      banner.className = `route-telemetry-banner ${sourceBadgeClass}`;
      banner.innerHTML = `
        <div class="telemetry-source-group">
          <span class="telemetry-chip ${sourceBadgeClass}">
            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              ${isLocal
                ? `<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>`
                : `<circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 14 14"></polyline>`
              }
            </svg>
            ${sourceLabel}
          </span>
          <span class="telemetry-offline-indicator">${res.is_offline !== false ? "100% OFFLINE" : "CONNECTED"}</span>
        </div>
        <div class="telemetry-stats-group">
          <span class="telemetry-stat"><strong>${distKm} km</strong> distance</span>
          <span class="stat-separator">·</span>
          <span class="telemetry-stat"><strong>~${durMin} min</strong> estimated drive</span>
        </div>
      `;

      this._renderMapPolyline(startLat, startLon, destLat, destLon, res.geometry?.coordinates || []);
    } catch (err) {
      console.error("Route calculation failed:", err);
      banner.className = "route-telemetry-banner error";
      banner.innerHTML = `
        <span>Route calculation failed: ${escapeHtml(err.message || "Unknown error")}</span>
      `;
    }
  }

  _renderMapPolyline(startLat, startLon, destLat, destLon, geoCoords) {
    const mapCanvas = this.container.querySelector("#route-map-canvas");
    if (!mapCanvas) return;

    // Destroy existing Leaflet map if present
    if (this.mapInstance) {
      try {
        this.mapInstance.remove();
      } catch (e) {
        // ignore
      }
      this.mapInstance = null;
    }

    // Convert GeoJSON [lon, lat] pairs to Leaflet [lat, lon]
    const latLngs = geoCoords.map((c) => [c[1], c[0]]);
    if (latLngs.length === 0) {
      latLngs.push([startLat, startLon], [destLat, destLon]);
    }

    // Check if Leaflet (L) is available globally
    if (typeof L !== "undefined") {
      try {
        const map = L.map(mapCanvas, {
          zoomControl: true,
          attributionControl: false,
          maxBounds: DELHI_MAP_BOUNDS,
          maxBoundsViscosity: 1.0,
          minZoom: 9,
          maxZoom: 18,
        });
        this.mapInstance = map;
        map.setView(DELHI_MAP_CENTER, 11);

        // Add OSM tiles (will load if online, neutral background if offline)
        L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19,
          subdomains: ["a", "b", "c"],
          errorTileUrl: "", // Graceful silence when offline
        }).addTo(map);

        // Start Marker (Emerald green circle)
        const startIcon = L.divIcon({
          className: "leaflet-custom-marker start-pin",
          html: `<div class="marker-pin marker-start" title="Start Location"><span class="pin-dot"></span></div>`,
          iconSize: [22, 22],
          iconAnchor: [11, 11],
        });
        L.marker([startLat, startLon], { icon: startIcon })
          .addTo(map)
          .bindPopup(`<strong>Origin</strong><br/>${escapeHtml(this.startLocation.name)}`);

        // Destination Marker (Crimson red pin)
        const destIcon = L.divIcon({
          className: "leaflet-custom-marker dest-pin",
          html: `<div class="marker-pin marker-dest" title="${escapeHtml(this.activeExperience.venue)}"><span class="pin-core"></span></div>`,
          iconSize: [26, 26],
          iconAnchor: [13, 26],
        });
        L.marker([destLat, destLon], { icon: destIcon })
          .addTo(map)
          .bindPopup(`<strong>${escapeHtml(this.activeExperience.title)}</strong><br/>${escapeHtml(this.activeExperience.venue)}`)
          .openPopup();

        // Draw Route Polyline
        const polyline = L.polyline(latLngs, {
          color: "#e11d48",
          weight: 5,
          opacity: 0.9,
          lineJoin: "round",
          lineCap: "round",
        }).addTo(map);

        // Fit map bounds to show complete route
        map.fitBounds(polyline.getBounds(), { padding: [40, 40] });

        // Trigger resize after DOM render
        setTimeout(() => map.invalidateSize(), 150);
        return;
      } catch (err) {
        console.warn("Leaflet map initialization failed, falling back to SVG vector renderer:", err);
      }
    }

    // Fallback vector SVG renderer if Leaflet cannot mount
    this._renderVectorFallback(mapCanvas, startLat, startLon, destLat, destLon, latLngs);
  }

  _renderDelhiMap(mapCanvas) {
    if (!mapCanvas || typeof L === "undefined") return;

    if (this.mapInstance) {
      try {
        this.mapInstance.remove();
      } catch (e) {
        // ignore
      }
    }

    const map = L.map(mapCanvas, {
      zoomControl: true,
      attributionControl: false,
      maxBounds: DELHI_MAP_BOUNDS,
      maxBoundsViscosity: 1.0,
      minZoom: 9,
      maxZoom: 18,
    }).setView(DELHI_MAP_CENTER, 11);
    this.mapInstance = map;
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      errorTileUrl: "",
    }).addTo(map);
    setTimeout(() => map.invalidateSize(), 150);
  }

  _renderVectorFallback(container, startLat, startLon, destLat, destLon, latLngs) {
    // Find coordinate bounds
    let minLat = Infinity, maxLat = -Infinity, minLon = Infinity, maxLon = -Infinity;
    for (const [lat, lon] of latLngs) {
      if (lat < minLat) minLat = lat;
      if (lat > maxLat) maxLat = lat;
      if (lon < minLon) minLon = lon;
      if (lon > maxLon) maxLon = lon;
    }

    const padLat = Math.max(0.01, (maxLat - minLat) * 0.15);
    const padLon = Math.max(0.01, (maxLon - minLon) * 0.15);
    minLat -= padLat;
    maxLat += padLat;
    minLon -= padLon;
    maxLon += padLon;

    const width = 800;
    const height = 450;

    const scaleX = (lon) => ((lon - minLon) / (maxLon - minLon)) * width;
    const scaleY = (lat) => (1 - (lat - minLat) / (maxLat - minLat)) * height;

    const pointsStr = latLngs.map(([lat, lon]) => `${scaleX(lon).toFixed(1)},${scaleY(lat).toFixed(1)}`).join(" ");
    const startX = scaleX(startLon).toFixed(1);
    const startY = scaleY(startLat).toFixed(1);
    const destX = scaleX(destLon).toFixed(1);
    const destY = scaleY(destLat).toFixed(1);

    container.innerHTML = `
      <div class="vector-route-svg-wrapper">
        <svg viewBox="0 0 ${width} ${height}" class="vector-route-svg" preserveAspectRatio="xMidYMid meet">
          <defs>
            <linearGradient id="routeGradient" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stop-color="#059669" />
              <stop offset="100%" stop-color="#e11d48" />
            </linearGradient>
            <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#e11d48" flood-opacity="0.3" />
            </filter>
          </defs>

          <!-- Background Grid for road orientation -->
          <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(226,232,240,0.6)" stroke-width="1"/>
          </pattern>
          <rect width="100%" height="100%" fill="#f8fafc" />
          <rect width="100%" height="100%" fill="url(#grid)" />

          <!-- Route Polyline -->
          <polyline points="${pointsStr}" fill="none" stroke="url(#routeGradient)" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" filter="url(#glow)" />

          <!-- Start Marker -->
          <circle cx="${startX}" cy="${startY}" r="9" fill="#059669" stroke="#ffffff" stroke-width="2.5" />
          <text x="${startX}" y="${parseFloat(startY) - 14}" fill="#065f46" font-size="12" font-weight="700" text-anchor="middle">Start: ${escapeHtml(this.startLocation.name.split(" ")[0])}</text>

          <!-- Destination Marker -->
          <circle cx="${destX}" cy="${destY}" r="10" fill="#e11d48" stroke="#ffffff" stroke-width="3" />
          <text x="${destX}" y="${parseFloat(destY) - 15}" fill="#9f1239" font-size="13" font-weight="800" text-anchor="middle">${escapeHtml(this.activeExperience.venue || "Venue")}</text>
        </svg>
      </div>
    `;
  }
}
