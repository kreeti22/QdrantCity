/**
 * EmptyState Component
 *
 * Clean empty result state with curated example queries.
 * No emojis, BookMyShow styling.
 */

import { escapeHtml } from "../utilities/formatting.js";

const EXAMPLE_QUERIES = [
  { label: "Movies this Weekend", query: "movies this weekend" },
  { label: "Concerts Under ₹2,500", query: "concerts under $30" },
  { label: "Comedy Shows", query: "comedy tonight" },
  { label: "Outdoor Activities", query: "outdoor activities" },
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
      ? `<p class="empty-state-subtitle">You haven't saved any experiences yet. Browse experiences and click the save button to bookmark your favorites.</p>`
      : `<p class="empty-state-subtitle">
           We couldn't find any experiences matching ${
             query
               ? `"<span class="query-highlight">${escapeHtml(query)}</span>"`
               : "your current criteria"
           }.
         </p>
         <div class="empty-state-suggestions">
           <p class="suggestions-label">Suggestions:</p>
           <ul class="suggestions-list">
             <li>Try broader keywords like <em>Movies, Concerts, Comedy</em></li>
             <li>Adjust or clear selected sidebar filters</li>
             <li>Search by specific titles or genres</li>
           </ul>
         </div>`;

    this.container.innerHTML = `
      <div class="empty-state" role="status" aria-live="polite">
        <div class="empty-state-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="36" height="36" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
        </div>
        <h3 class="empty-state-title">${
          isBookmarks ? "No Saved Experiences" : "No Experiences Found"
        }</h3>
        ${bookmarkHint}
        ${
          !isBookmarks
            ? `<div class="empty-state-actions">
                 <p class="suggestions-label" style="margin-bottom:0.5rem;">Explore popular searches:</p>
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
