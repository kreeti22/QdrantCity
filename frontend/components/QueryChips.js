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
      { label: "Movies near me", query: "movies near me" },
      { label: "Movie at PVR", query: "movie at PVR" },
      { label: "Events near Connaught Place", query: "events near Connaught Place" },
      { label: "Concert in Delhi", query: "concert in Delhi" },
      { label: "Comedy in Delhi", query: "comedy in Delhi" },
      { label: "IMAX Sci-Fi", query: "IMAX sci-fi movies" },
      { label: "Delhi Sufi Qawwali", query: "Delhi sufi qawwali" },
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
