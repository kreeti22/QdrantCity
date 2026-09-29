/**
 * EmptyState Component — Phase 3F: UX Polish
 *
 * Friendly empty result state with curated example queries so users
 * can immediately try something meaningful after a zero-result search.
 */

import { escapeHtml } from "../utilities/formatting.js";

const EXAMPLE_QUERIES = [
  { label: "Comedy Tonight", query: "comedy tonight" },
  { label: "IMAX This Weekend", query: "IMAX movies this weekend" },
  { label: "Live Music Under \$50", query: "live music under $50" },
  { label: "Free Outdoor Events", query: "free outdoor events this week" },
  { label: "Art Exhibitions", query: "art exhibitions downtown" },
  { label: "Family Workshops", query: "family workshops Saturday" },
];

export class EmptyState {
  constructor({ container, onSuggestionClick }) {
    this.container = container;
    this.onSuggestionClick = onSuggestionClick;
  }

  render(query = "") {
    const isBookmarks = query === "Saved Bookmarks";

    const bookmarkHint = isBookmarks
      ? `<p class="empty-state-subtitle">You haven't saved any experiences yet. Search and tap the bookmark icon to save your favourites.</p>`
      : `<p class="empty-state-subtitle">
           We couldn't find any city experiences matching ${
             query
               ? `"<span class="query-highlight">${escapeHtml(query)}</span>"`
               : "your current criteria"
           }.
         </p>
         <div class="empty-state-suggestions">
           <p class="suggestions-label">Tips to broaden your search:</p>
           <ul class="suggestions-list">
             <li>Use broader category terms: <em>comedy, movies, live music, festivals</em></li>
             <li>Relax price, date, or time constraints</li>
             <li>Explore city-wide instead of a single neighborhood</li>
             <li>Try removing indoor/outdoor filters</li>
           </ul>
         </div>`;

    this.container.innerHTML = `
      <div class="empty-state" role="status" aria-live="polite">
        <div class="empty-state-icon" aria-hidden="true">${isBookmarks ? "🔖" : "🔍"}</div>
        <h3 class="empty-state-title">${
          isBookmarks ? "No saved experiences yet" : "No experiences matched that search"
        }</h3>
        ${bookmarkHint}
        ${
          !isBookmarks
            ? `<div class="empty-state-actions">
                 <p class="suggestions-label" style="margin-bottom:0.5rem;">Try one of these:</p>
                 <div class="empty-query-chips">
                   ${EXAMPLE_QUERIES.map(
                     (e) =>
                       `<button type="button" class="empty-action-btn" data-query="${escapeHtml(e.query)}">${escapeHtml(e.label)}</button>`
                   ).join("")}
                 </div>
               </div>`
            : ""
        }
      </div>
    `;

    this.container.querySelectorAll(".empty-action-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const q = btn.getAttribute("data-query");
        if (q && this.onSuggestionClick) {
          this.onSuggestionClick(q);
        }
      });
    });
  }

  clear() {
    this.container.innerHTML = "";
  }
}
