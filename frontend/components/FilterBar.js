/**
 * FilterBar Component
 *
 * Lightweight, optional discovery controls:
 * - Category
 * - Maximum Price
 * - Indoor / Outdoor
 *
 * Keeps natural-language search as primary interaction while allowing explicit overrides.
 */

export class FilterBar {
  constructor({ container, onChange }) {
    this.container = container;
    this.onChange = onChange;
    this.filters = {
      category: "",
      max_price: null,
      is_indoor: null,
    };
    this.categories = [
      { id: "", label: "All Categories" },
      { id: "comedy", label: "Comedy" },
      { id: "movies", label: "Movies" },
      { id: "concerts", label: "Concerts" },
      { id: "theatre", label: "Theatre" },
      { id: "sports", label: "Sports" },
      { id: "festivals", label: "Festivals" },
      { id: "workshops", label: "Workshops" },
      { id: "exhibitions", label: "Exhibitions" },
      { id: "activities", label: "Activities" },
    ];
    this.render();
  }

  render() {
    this.container.innerHTML = `
      <div class="filter-bar" aria-label="Optional search filters">
        <div class="filter-controls">
          <!-- Category Filter -->
          <div class="filter-item">
            <label for="filter-category" class="filter-label">Category</label>
            <select id="filter-category" class="filter-select">
              ${this.categories
                .map(
                  (c) => `<option value="${c.id}" ${this.filters.category === c.id ? "selected" : ""}>${c.label}</option>`
                )
                .join("")}
            </select>
          </div>

          <!-- Max Price Filter -->
          <div class="filter-item">
            <label for="filter-price" class="filter-label">Max Price</label>
            <select id="filter-price" class="filter-select">
              <option value="" ${this.filters.max_price === null ? "selected" : ""}>Any Price</option>
              <option value="20" ${this.filters.max_price === 20 ? "selected" : ""}>Under $20</option>
              <option value="30" ${this.filters.max_price === 30 ? "selected" : ""}>Under $30</option>
              <option value="50" ${this.filters.max_price === 50 ? "selected" : ""}>Under $50</option>
              <option value="100" ${this.filters.max_price === 100 ? "selected" : ""}>Under $100</option>
            </select>
          </div>

          <!-- Indoor / Outdoor Filter -->
          <div class="filter-item">
            <label for="filter-indoor" class="filter-label">Setting</label>
            <select id="filter-indoor" class="filter-select">
              <option value="" ${this.filters.is_indoor === null ? "selected" : ""}>Any Setting</option>
              <option value="true" ${this.filters.is_indoor === true ? "selected" : ""}>Indoor Only</option>
              <option value="false" ${this.filters.is_indoor === false ? "selected" : ""}>Outdoor Only</option>
            </select>
          </div>

          <!-- Reset Button -->
          <button type="button" id="filter-reset-btn" class="filter-reset-btn" ${!this.hasActiveFilters() ? 'style="display:none;"' : ""}>
            Reset Filters
          </button>
        </div>
      </div>
    `;

    const catSelect = this.container.querySelector("#filter-category");
    const priceSelect = this.container.querySelector("#filter-price");
    const indoorSelect = this.container.querySelector("#filter-indoor");
    const resetBtn = this.container.querySelector("#filter-reset-btn");

    catSelect.addEventListener("change", (e) => {
      this.filters.category = e.target.value.trim();
      this._handleFilterChange();
    });

    priceSelect.addEventListener("change", (e) => {
      const val = e.target.value;
      this.filters.max_price = val ? parseFloat(val) : null;
      this._handleFilterChange();
    });

    indoorSelect.addEventListener("change", (e) => {
      const val = e.target.value;
      this.filters.is_indoor = val === "true" ? true : val === "false" ? false : null;
      this._handleFilterChange();
    });

    resetBtn.addEventListener("click", () => {
      this.reset();
      this._handleFilterChange();
    });
  }

  _handleFilterChange() {
    const resetBtn = this.container.querySelector("#filter-reset-btn");
    if (resetBtn) {
      resetBtn.style.display = this.hasActiveFilters() ? "inline-block" : "none";
    }

    if (this.onChange) {
      this.onChange(this.getActiveFilters());
    }
  }

  hasActiveFilters() {
    return Boolean(this.filters.category || this.filters.max_price !== null || this.filters.is_indoor !== null);
  }

  getActiveFilters() {
    const out = {};
    if (this.filters.category) out.category = this.filters.category;
    if (this.filters.max_price !== null) out.max_price = this.filters.max_price;
    if (this.filters.is_indoor !== null) out.is_indoor = this.filters.is_indoor;
    return Object.keys(out).length > 0 ? out : null;
  }

  reset() {
    this.filters = { category: "", max_price: null, is_indoor: null };
    const cat = this.container.querySelector("#filter-category");
    const prc = this.container.querySelector("#filter-price");
    const ind = this.container.querySelector("#filter-indoor");
    const rst = this.container.querySelector("#filter-reset-btn");
    if (cat) cat.value = "";
    if (prc) prc.value = "";
    if (ind) ind.value = "";
    if (rst) rst.style.display = "none";
  }
}
