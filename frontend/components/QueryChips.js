/**
 * QueryChips Component
 *
 * Clickable quick-query chips below the search bar that populate and execute searches.
 * India-specific searches with clean BookMyShow tag aesthetic.
 */

export class QueryChips {
  constructor({
    container,
    onSelect,
    chips = [
      { label: "⚡ Adventurous & Thrilling", query: "adventurous and thrilling" },
      { label: "🌴 Goa Parties & Casinos", query: "Goa night parties casinos" },
      { label: "🍿 Delhi Movies", query: "movies in Delhi" },
      { label: "🧩 Mystery Rooms Delhi", query: "mystery rooms Delhi" },
      { label: "🎶 Nizamuddin Sufi Qawwali", query: "Nizamuddin Sufi Qawwali" },
      { label: "🎭 Late Night Comedy", query: "comedy in Delhi" },
    ],
  }) {
    this.container = container;
    this.onSelect = onSelect;
    this.chips = chips;
    this.render();
  }

  render() {
    this.container.innerHTML = `
      <div class="query-chips-wrapper" aria-label="Suggested searches">
        <span class="chips-label">Popular:</span>
        <div class="chips-list">
          ${this.chips
            .map(
              (chip, idx) => `
            <button
              type="button"
              class="query-chip"
              data-query="${chip.query}"
              data-idx="${idx}"
              aria-label="Search for ${chip.label}"
            >
              ${chip.label}
            </button>
          `
            )
            .join("")}
        </div>
      </div>
    `;

    this.container.querySelectorAll(".query-chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        const query = btn.getAttribute("data-query");
        if (query && this.onSelect) {
          this.onSelect(query);
        }
      });
    });
  }

  setDisabled(disabled) {
    this.container.querySelectorAll(".query-chip").forEach((btn) => {
      btn.disabled = disabled;
    });
  }
}
