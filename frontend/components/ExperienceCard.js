/**
 * ExperienceCard Component
 *
 * Renders a clean, specific experience card with poster/badge, category tag,
 * pricing in Rupees, ratings, and location/schedule metadata.
 * Designed with a BookMyShow-style white & red card aesthetic.
 */

import {
  escapeHtml,
  formatDateTime,
  formatPrice,
  formatScore,
  getCategoryBadgeClass,
} from "../utilities/formatting.js";

export class ExperienceCard {
  /**
   * Generates HTML markup for an experience card.
   *
   * @param {Object} experience - The normalized experience object from backend
   * @returns {string} HTML string
   */
  static renderMarkup(experience) {
    if (!experience) return "";

    const id = experience.id ?? "";
    const rawTitle = experience.title || "Untitled Experience";
    const title = escapeHtml(rawTitle);
    const category = escapeHtml(experience.category || "Experience");
    const venue = escapeHtml(experience.venue || "Venue TBA");
    const neighborhood = escapeHtml(experience.neighborhood || "");
    const city = escapeHtml(experience.city || "");
    const priceText = formatPrice(experience.price, experience.currency);
    const dateText = formatDateTime(experience.start_time);
    const badgeClass = getCategoryBadgeClass(experience.category);
    const rating = experience.rating ? Number(experience.rating).toFixed(1) : null;
    const scoreText = formatScore(experience.score);

    const state = escapeHtml(experience.state || "");

    // Location line: "Venue · Neighborhood, City"
    const locationParts = [venue];
    if (neighborhood && city) {
      locationParts.push(`${neighborhood}, ${city}`);
    } else if (neighborhood) {
      locationParts.push(neighborhood);
    } else if (city) {
      locationParts.push(city);
    }
    const locationText = locationParts.join(" · ");

    // Subcategories tags (clean pills)
    const subcats = Array.isArray(experience.subcategories)
      ? experience.subcategories.slice(0, 3)
      : [];

    const imageUrl = experience.image_url || "";
    const isSaved = experience.is_saved === true;

    return `
      <article
        class="experience-card"
        data-id="${id}"
        tabindex="0"
        role="button"
        aria-label="View details for ${title}"
      >
        <div class="card-image-wrapper">
          ${
            imageUrl
              ? `<img
                  src="${escapeHtml(imageUrl)}"
                  alt="${title}"
                  class="card-image"
                  loading="lazy"
                  onerror="this.onerror=null; this.parentElement.classList.add('has-fallback-image'); this.style.display='none';"
                />`
              : ""
          }
          <div class="fallback-image-badge" aria-hidden="true">
            <svg class="fallback-card-icon" viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
              <rect x="2" y="2" width="20" height="20" rx="3" ry="3"></rect>
              <line x1="7" y1="2" x2="7" y2="22"></line>
              <line x1="17" y1="2" x2="17" y2="22"></line>
              <line x1="2" y1="12" x2="22" y2="12"></line>
              <line x1="2" y1="7" x2="7" y2="7"></line>
              <line x1="2" y1="17" x2="7" y2="17"></line>
              <line x1="17" y1="17" x2="22" y2="17"></line>
              <line x1="17" y1="7" x2="22" y2="7"></line>
            </svg>
          </div>
          
          <div class="card-badges-top">
            <span class="category-badge ${badgeClass}">${category.toUpperCase()}</span>
            ${
              experience.is_indoor !== null && experience.is_indoor !== undefined
                ? `<span class="setting-badge">${experience.is_indoor ? "Indoor" : "Outdoor"}</span>`
                : ""
            }
          </div>

          <button
            type="button"
            class="card-bookmark-btn ${isSaved ? "is-bookmarked" : ""}"
            data-action="bookmark"
            data-id="${id}"
            title="${isSaved ? "Remove from bookmarks" : "Save experience"}"
            aria-label="${isSaved ? "Remove from bookmarks" : "Save experience"}"
          >
            <svg viewBox="0 0 24 24" width="16" height="16" fill="${isSaved ? "currentColor" : "none"}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path>
            </svg>
          </button>
        </div>

        <div class="card-content">
          <div class="card-header">
            <h3 class="card-title">${title}</h3>
            ${
              rating
                ? `<div class="card-rating" aria-label="Rated ${rating} out of 5">
                    <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor" stroke="none">
                      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>
                    </svg>
                    <span>${rating}</span>
                  </div>`
                : ""
            }
          </div>

          <div class="card-meta">
            <div class="meta-row location-row">
              <svg class="meta-icon" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
                <circle cx="12" cy="10" r="3"></circle>
              </svg>
              <span class="meta-text">${locationText}</span>
            </div>

            <div class="meta-row date-row">
              <svg class="meta-icon" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                <line x1="16" y1="2" x2="16" y2="6"></line>
                <line x1="8" y1="2" x2="8" y2="6"></line>
                <line x1="3" y1="10" x2="21" y2="10"></line>
              </svg>
              <span class="meta-text">${dateText}</span>
            </div>
          </div>

          <div class="card-footer">
            <div class="card-price">${priceText}</div>
            ${
              subcats.length > 0
                ? `<div class="card-tags">
                    ${subcats.map((tag) => `<span class="tag-pill">${escapeHtml(tag)}</span>`).join("")}
                   </div>`
                : scoreText
                ? `<span class="relevance-score" title="Match Score">Score ${scoreText}</span>`
                : ""
            }
          </div>
        </div>
      </article>
    `;
  }
}
