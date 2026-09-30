/**
 * ResultsGrid Component
 *
 * Renders the responsive grid of search results, result counts, and metadata telemetry.
 * Styled in clean BookMyShow white and red aesthetic without emojis.
 */

import { ExperienceCard } from "./ExperienceCard.js";
import { escapeHtml } from "../utilities/formatting.js";

export class ResultsGrid {
  constructor({ container, onSelect, onBookmarkToggle, onShowRoute }) {
    this.container = container;
    this.onSelect = onSelect;
    this.onBookmarkToggle = onBookmarkToggle;
    this.onShowRoute = onShowRoute;
    this.results = [];
  }

  render({ query, results, total_returned, latency_ms, intent, filters_applied, personalization }) {
    this.results = results || [];

    const total = total_returned !== undefined ? total_returned : this.results.length;
    const totalLatency = latency_ms && latency_ms.total_ms ? `${latency_ms.total_ms.toFixed(1)}ms` : "";
    const isPersonalized = personalization && personalization.applied === true;

    this.container.innerHTML = `
      <section class="results-section" aria-label="Search Results">
        <div class="results-header">
          <div class="results-title-group">
            <h2 class="results-heading">
              Found <span class="highlight-count">${total}</span> ${total === 1 ? "experience" : "experiences"}
              ${query ? `for "<span class="highlight-query">${escapeHtml(query)}</span>"` : ""}
            </h2>
            ${
              isPersonalized
                ? `<span class="personalization-badge" title="Results tailored to your saved preferences">
                    Personalized for you
                   </span>`
                : ""
            }
          </div>
          ${
            totalLatency
              ? `<div class="results-telemetry" title="Local CPU Retrieval Latency">
                  <span class="telemetry-badge">
                    <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
                    </svg>
                    <span>${totalLatency}</span>
                  </span>
                 </div>`
              : ""
          }
        </div>

        <div class="results-grid" id="results-grid-items">
          ${this.results.map((exp) => ExperienceCard.renderMarkup(exp)).join("")}
        </div>
      </section>
    `;

    // Attach click and enter key handlers to card elements
    const gridEl = this.container.querySelector("#results-grid-items");
    if (gridEl) {
      gridEl.querySelectorAll(".experience-card").forEach((card) => {
        const id = card.getAttribute("data-id");
        const exp = this.results.find((r) => String(r.id) === String(id));

        // Bookmark button click
        const bookmarkBtn = card.querySelector(".card-bookmark-btn");
        if (bookmarkBtn) {
          bookmarkBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            if (exp && this.onBookmarkToggle) {
              this.onBookmarkToggle(exp, bookmarkBtn);
            }
          });
        }

        // Route button click
        const routeBtn = card.querySelector(".card-route-btn");
        if (routeBtn) {
          routeBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            if (exp && this.onShowRoute) {
              this.onShowRoute(exp);
            }
          });
        }

        const triggerSelect = () => {
          if (exp && this.onSelect) {
            this.onSelect(exp);
          }
        };

        card.addEventListener("click", triggerSelect);
        card.addEventListener("keydown", (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            triggerSelect();
          }
        });
      });
    }
  }

  clear() {
    this.results = [];
    this.container.innerHTML = "";
  }
}
