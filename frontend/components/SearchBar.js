/**
 * SearchBar Component
 *
 * Prominent natural-language search bar with keyboard and submit button handling.
 */

export class SearchBar {
  constructor({ container, onSearch, placeholder = 'Try "comedy tonight under $50" or "indie film in Mission"' }) {
    this.container = container;
    this.onSearch = onSearch;
    this.placeholder = placeholder;
    this.inputElement = null;
    this.buttonElement = null;
    this.render();
  }

  render() {
    this.container.innerHTML = `
      <form class="search-form" id="search-form" role="search" aria-label="City experiences discovery search">
        <div class="search-input-wrapper">
          <svg class="search-icon" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
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
            aria-label="Natural language search query"
          />
          <button type="submit" id="search-submit-btn" class="search-submit-btn" aria-label="Submit Search">
            <span>Discover</span>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="5" y1="12" x2="19" y2="12"></line>
              <polyline points="12 5 19 12 12 19"></polyline>
            </svg>
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
        : `<span>Discover</span>
           <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
             <line x1="5" y1="12" x2="19" y2="12"></line>
             <polyline points="12 5 19 12 12 19"></polyline>
           </svg>`;
    }
  }
}
