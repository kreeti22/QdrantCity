/**
 * FilterBar Component
 *
 * Left Sidebar Filter Panel:
 * - City (Mumbai, Delhi, Bengaluru, Pune)
 * - Category
 * - Price in Indian Rupees (₹)
 * - Setting (Indoor / Outdoor)
 */

export class FilterBar {
  constructor({ container, onChange }) {
    this.container = container;
    this.onChange = onChange;
    this.filters = {
      city: "",
      category: "",
      max_price: null,
      is_indoor: null,
    };
    this.cities = [
      { id: "", label: "All Cities" },
      { id: "Delhi", label: "Delhi" },
      { id: "Goa", label: "Goa" },
      { id: "Mumbai", label: "Mumbai" },
      { id: "Bengaluru", label: "Bengaluru" },
    ];
    this.categories = [
      { id: "", label: "All Categories" },
      { id: "movies", label: "Movies" },
      { id: "concerts", label: "Concerts" },
      { id: "comedy", label: "Comedy" },
      { id: "theatre", label: "Plays & Theatre" },
      { id: "sports", label: "Sports" },
      { id: "activities", label: "Activities" },
      { id: "festivals", label: "Festivals" },
      { id: "workshops", label: "Workshops" },
      { id: "exhibitions", label: "Exhibitions" },
    ];
    this.priceOptions = [
      { value: "", label: "Any Price", maxPrice: null },
      { value: "300", label: "Under ₹300", maxPrice: 300.0 },
      { value: "600", label: "Under ₹600", maxPrice: 600.0 },
      { value: "1200", label: "Under ₹1,200", maxPrice: 1200.0 },
      { value: "2500", label: "Under ₹2,500", maxPrice: 2500.0 },
      { value: "5000", label: "Under ₹5,000", maxPrice: 5000.0 },
    ];
    this.render();
  }

  render() {
    this.container.innerHTML = `
      <div class="sidebar-filters-panel" aria-label="Search filters">
        <div class="sidebar-filters-header">
          <h3 class="sidebar-filters-title">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"></polygon>
            </svg>
            <span>Filters</span>
          </h3>
          <button type="button" id="filter-reset-btn" class="filter-reset-btn" ${!this.hasActiveFilters() ? 'style="display:none;"' : ""}>
            Clear All
          </button>
        </div>

        <!-- City Filter Group -->
        <div class="filter-group">
          <label class="filter-group-title">City</label>
          <div class="city-radio-list">
            ${this.cities
              .map(
                (c) => `
              <label class="filter-radio-item ${this.filters.city === c.id ? "is-selected" : ""}">
                <input
                  type="radio"
                  name="sidebar-city"
                  value="${c.id}"
                  ${this.filters.city === c.id ? "checked" : ""}
                />
                <span class="radio-custom"></span>
                <span class="radio-label-text">${c.label}</span>
              </label>
            `
              )
              .join("")}
          </div>
        </div>

        <!-- Category Filter Group -->
        <div class="filter-group">
          <label class="filter-group-title">Category</label>
          <div class="category-radio-list">
            ${this.categories
              .map(
                (c) => `
              <label class="filter-radio-item ${this.filters.category === c.id ? "is-selected" : ""}">
                <input
                  type="radio"
                  name="sidebar-category"
                  value="${c.id}"
                  ${this.filters.category === c.id ? "checked" : ""}
                />
                <span class="radio-custom"></span>
                <span class="radio-label-text">${c.label}</span>
              </label>
            `
              )
              .join("")}
          </div>
        </div>

        <!-- Max Price Filter Group in Rupees -->
        <div class="filter-group">
          <label class="filter-group-title">Price Range</label>
          <div class="price-radio-list">
            ${this.priceOptions
              .map(
                (p) => `
              <label class="filter-radio-item ${String(this.filters.max_price) === String(p.maxPrice) || (this.filters.max_price === null && p.value === "") ? "is-selected" : ""}">
                <input
                  type="radio"
                  name="sidebar-price"
                  value="${p.value}"
                  data-price="${p.maxPrice !== null ? p.maxPrice : ""}"
                  ${String(this.filters.max_price) === String(p.maxPrice) || (this.filters.max_price === null && p.value === "") ? "checked" : ""}
                />
                <span class="radio-custom"></span>
                <span class="radio-label-text">${p.label}</span>
              </label>
            `
              )
              .join("")}
          </div>
        </div>

        <!-- Indoor / Outdoor Setting -->
        <div class="filter-group">
          <label class="filter-group-title">Setting</label>
          <div class="setting-buttons">
            <button
              type="button"
              class="setting-btn ${this.filters.is_indoor === null ? "is-active" : ""}"
              data-setting=""
            >
              Any
            </button>
            <button
              type="button"
              class="setting-btn ${this.filters.is_indoor === true ? "is-active" : ""}"
              data-setting="true"
            >
              Indoor
            </button>
            <button
              type="button"
              class="setting-btn ${this.filters.is_indoor === false ? "is-active" : ""}"
              data-setting="false"
            >
              Outdoor
            </button>
          </div>
        </div>
      </div>
    `;

    this._bindEvents();
  }

  _bindEvents() {
    const cityRadios = this.container.querySelectorAll('input[name="sidebar-city"]');
    const catRadios = this.container.querySelectorAll('input[name="sidebar-category"]');
    const priceRadios = this.container.querySelectorAll('input[name="sidebar-price"]');
    const settingBtns = this.container.querySelectorAll(".setting-btn");
    const resetBtn = this.container.querySelector("#filter-reset-btn");

    cityRadios.forEach((r) => {
      r.addEventListener("change", (e) => {
        this.filters.city = e.target.value.trim();
        this._updateUiSelection();
        this._handleFilterChange();
      });
    });

    catRadios.forEach((r) => {
      r.addEventListener("change", (e) => {
        this.filters.category = e.target.value.trim();
        this._updateUiSelection();
        this._handleFilterChange();
      });
    });

    priceRadios.forEach((r) => {
      r.addEventListener("change", (e) => {
        const val = e.target.getAttribute("data-price");
        this.filters.max_price = val ? parseFloat(val) : null;
        this._updateUiSelection();
        this._handleFilterChange();
      });
    });

    settingBtns.forEach((btn) => {
      btn.addEventListener("click", () => {
        const val = btn.getAttribute("data-setting");
        this.filters.is_indoor = val === "true" ? true : val === "false" ? false : null;
        this._updateUiSelection();
        this._handleFilterChange();
      });
    });

    if (resetBtn) {
      resetBtn.addEventListener("click", () => {
        this.reset();
        this._handleFilterChange();
      });
    }
  }

  _updateUiSelection() {
    this.render();
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

  setCity(city) {
    this.filters.city = city || "";
    this.render();
    if (this.onChange) {
      this.onChange(this.getActiveFilters());
    }
  }

  setCategory(category) {
    this.filters.category = category || "";
    this.render();
    if (this.onChange) {
      this.onChange(this.getActiveFilters());
    }
  }

  hasActiveFilters() {
    return Boolean(
      this.filters.city ||
      this.filters.category ||
      this.filters.max_price !== null ||
      this.filters.is_indoor !== null
    );
  }

  getActiveFilters() {
    const out = {};
    if (this.filters.city) out.city = this.filters.city;
    if (this.filters.category) out.category = this.filters.category;
    if (this.filters.max_price !== null) out.max_price = this.filters.max_price;
    if (this.filters.is_indoor !== null) out.is_indoor = this.filters.is_indoor;
    return Object.keys(out).length > 0 ? out : null;
  }

  reset() {
    this.filters = { city: "", category: "", max_price: null, is_indoor: null };
    this.render();
  }
}
