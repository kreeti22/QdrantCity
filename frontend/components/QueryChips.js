/**
 * QueryChips Component
 *
 * Clickable quick-query chips below the search bar that populate and execute searches.
 */

export class QueryChips {
  constructor({
    container,
    onSelect,
    chips = [
      { label: "Comedy tonight", query: "comedy tonight" },
      { label: "Movies this weekend", query: "movies this weekend" },
      { label: "Concerts under $30", query: "concerts under $30" },
      { label: "Outdoor activities", query: "outdoor activities" },
      { label: "Something fun tonight", query: "something fun tonight" },
      { label: "IMAX sci-fi", query: "IMAX sci-fi movies" },
    ],
  }) {
    this.container = container;
    this.onSelect = onSelect;
    this.chips = chips;
    this.render();
  }

  render() {
    this.container.innerHTML = `
      <div class="query-chips-wrapper" aria-label="Suggested natural-language queries">
        <span class="chips-label">Popular searches:</span>
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
