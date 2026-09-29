/**
 * ResultsGrid Component
 *
 * Renders the responsive grid of search results, result counts, and metadata telemetry.
 */

import { ExperienceCard } from "./ExperienceCard.js";
import { escapeHtml } from "../utilities/formatting.js";

export class ResultsGrid {
  constructor({ container, onSelect, onBookmarkToggle }) {
    this.container = container;
    this.onSelect = onSelect;
    this.onBookmarkToggle = onBookmarkToggle;
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
                ? `<span class="personalization-badge" title="Results re-ranked based on your saved items and local preferences">
                    ✨ Personalized for you
                   </span>`
                : ""
            }
          </div>
          ${
            totalLatency
              ? `<div class="results-telemetry" title="Local CPU Retrieval Latency">
                  <span class="telemetry-badge">⚡ ${totalLatency}</span>
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
