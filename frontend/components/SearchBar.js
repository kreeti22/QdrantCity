/**
 * SearchBar Component
 *
 * Full-width BookMyShow-style search bar for movies, events, concerts and plays.
 */

export class SearchBar {
  constructor({
    container,
    onSearch,
    placeholder = "Search for Movies, Events, Plays, Sports and Activities...",
  }) {
    this.container = container;
    this.onSearch = onSearch;
    this.placeholder = placeholder;
    this.inputElement = null;
    this.buttonElement = null;
    this.render();
  }

  render() {
    this.container.innerHTML = `
      <form class="search-form" id="search-form" role="search" aria-label="Search movies and experiences">
        <div class="search-input-wrapper">
          <svg class="search-icon" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
          <input
            type="search"
            id="search-input"
            class="search-input"
            placeholder="${this.placeholder}"
            autocomplete="off"
            spellcheck="false"
            aria-label="Search query"
          />
          <button type="submit" id="search-submit-btn" class="search-submit-btn" aria-label="Search">
            <span>Search</span>
          </button>
        </div>
      </form>
    `;

    const form = this.container.querySelector("#search-form");
    this.inputElement = this.container.querySelector("#search-input");
    this.buttonElement = this.container.querySelector("#search-submit-btn");

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const val = this.getValue();
      if (val && this.onSearch) {
        this.onSearch(val);
      }
    });

    this.inputElement.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        const val = this.getValue();
        if (val && this.onSearch) {
          this.onSearch(val);
        }
      }
    });
  }

  getValue() {
    return this.inputElement ? this.inputElement.value.trim() : "";
  }

  setValue(val) {
    if (this.inputElement) {
      this.inputElement.value = val;
    }
  }

  setLoading(isLoading) {
    if (this.inputElement) {
      this.inputElement.disabled = isLoading;
    }
    if (this.buttonElement) {
      this.buttonElement.disabled = isLoading;
      this.buttonElement.innerHTML = isLoading
        ? `<span class="spinner-small" aria-hidden="true"></span> Searching...`
        : `<span>Search</span>`;
    }
  }
}
