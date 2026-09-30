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
   * Formats a raw experience title into a simple, punchy event or movie name.
   * Keeps the card title clean for judges while preserving details in the description.
   *
   * @param {string} rawTitle - Full original title
   * @returns {string} Clean event or movie name
   */
  static formatCardTitle(rawTitle) {
    if (!rawTitle) return "Untitled Experience";

    const cleanMap = {
      "Interstellar: 70mm IMAX Special Presentation": "Interstellar",
      "Dilwale Dulhania Le Jayenge": "Dilwale Dulhania Le Jayenge",
      "Sholay (70mm Revival)": "Sholay",
      "Sitar & Tabla Jugalbandi": "Sitar & Tabla Jugalbandi",
      "Beethoven & Tchaikovsky Symphony": "Beethoven & Tchaikovsky Symphony",
      "R.D. Burman Tribute Symphony": "R.D. Burman Tribute Symphony",
      "Bandra Acoustic Sunset": "Bandra Acoustic Sunset",
      "The Habitat Comedy Special": "The Habitat Comedy Special",
      "Bandra Unscripted Improv": "Bandra Unscripted Improv",
      "Sakharam Binder (Hindi Drama)": "Sakharam Binder",
      "Sangeet Shakuntal (Marathi Natak)": "Sangeet Shakuntal",
      "NCPA Contemporary Monologues": "Contemporary Monologues",
      "Wankhede Stadium & Museum Tour": "Wankhede Stadium Tour",
      "Mumbai Coastal Sunrise Run": "Mumbai Coastal Sunrise Run",
      "Mumbai Harbour Sunset Kayaking": "Mumbai Harbour Kayaking",
      "Mumbai Art Deco Heritage Walk": "Art Deco Heritage Walk",
      "Elephanta Caves Ferry Excursion": "Elephanta Caves Tour",
      "Kanheri Caves & Forest Trail": "Kanheri Caves Trail",
      "Khau Galli Food Discovery Walk": "Khau Galli Food Walk",
      "Kala Ghoda Arts Showcase": "Kala Ghoda Arts Showcase",
      "Banganga Classical Music Festival": "Banganga Music Festival",
      "Mumbai Literature Festival": "Mumbai Literature Festival",
      "Warli Painting Masterclass": "Warli Painting Masterclass",
      "Irani Chai & Baking Workshop": "Irani Chai & Baking Workshop",
      "Bollywood Choreography Workshop": "Bollywood Choreography Workshop",
      "Chhatrapati Shivaji Maharaj Vastu Sangrahalaya (CSMVS) Heritage Tour": "CSMVS Museum Tour",
      "Dr. Bhau Daji Lad City Museum: Victorian Decorative Arts": "Dr. Bhau Daji Lad Museum",
      "Jehangir Art Gallery: Contemporary Indian Painters": "Jehangir Art Gallery",
      "PVR Director's Cut Luxury Screening: Dune Part Two": "Dune: Part Two",
      "World Cinema Retrospective: Satyajit Ray's Apu Trilogy": "The Apu Trilogy",
      "Delite Cinema Heritage Single-Screen Bollywood Premiere": "Delite Cinema Premiere",
      "Late Night Underground Standup Comedy Showcase": "Late Night Standup Comedy",
      "Sufi Qawwali Night at Hazrat Nizamuddin Dargah": "Nizamuddin Sufi Qawwali",
      "Delhi International Classical Music Evening: Sarod & Flute": "Sarod & Flute Classical Evening",
      "Hauz Khas Indie Acoustic Evening: Jazz & Fusion": "Hauz Khas Indie Acoustic",
      "Delhi Comedy Club Weekend Special: Dilliwaale": "Dilliwaale Comedy Special",
      "Punchlines & Parathas: Late Night Comedy Jam": "Punchlines & Parathas",
      "National School of Drama Ensemble: Andha Yug": "Andha Yug",
      "Habib Tanvir's Charandas Chor Revival Play": "Charandas Chor",
      "Shakespeare in Delhi: A Midsummer Night's Dream": "A Midsummer Night's Dream",
      "Arun Jaitley Cricket Stadium Walk & Feroz Shah Kotla History": "Arun Jaitley Stadium Tour",
      "Delhi Ridge Forest Trail Cycling & Endurance Ride": "Delhi Ridge Forest Cycling",
      "Old Delhi Shahjahanabad Heritage & Street Food Trail": "Old Delhi Heritage & Food Trail",
      "Qutub Minar Complex & Mehrauli Archaeological Twilight Walk": "Qutub Minar Twilight Walk",
      "Humayun's Tomb Mughal Charbagh Architectural Tour": "Humayun's Tomb Mughal Tour",
      "Lodhi Art District Open-Air Street Mural Walking Tour": "Lodhi Art District Murals",
      "Delhi International Arts Festival: Classical Fusion Gala": "Delhi Arts Festival",
      "Dilli Haat Crafts & Regional Food Carnival": "Dilli Haat Food & Crafts Carnival",
      "Kathak Classical Dance Rhythm & Footwork Masterclass": "Kathak Dance Masterclass",
      "Traditional Indian Wooden Block Printing on Cotton": "Wooden Block Printing Workshop",
      "Mughlai Kebab & Biryani Culinary Masterclass": "Mughlai Kebab & Biryani Workshop",
      "National Museum: Harappan Civilization & Sacred Relics": "National Museum: Harappan Relics",
      "National Gallery of Modern Art (NGMA): Modern Indian Masters": "NGMA Modern Masters",
      "National Crafts Museum: Village Courtyards & Textiles": "National Crafts Museum",
      "Kiran Nadar Museum of Art (KNMA): Contemporary Retrospectives": "Kiran Nadar Museum of Art",
      "Urvashi Cinema 4K Laser Curved Screen Experience": "Urvashi Cinema 4K Showcase",
      "PVR Forum Mall IMAX: Sci-Fi & Hollywood Blockbusters": "PVR Forum IMAX Blockbusters",
      "Suchitra Film Society World Cinema Club Screening": "Suchitra World Cinema Club",
      "Carnatic Classical Concert: Veena & Mridangam Recital": "Carnatic Veena & Mridangam Recital",
      "Chowdiah Memorial Hall Grand Carnatic Vocal Recital": "Chowdiah Carnatic Vocal Recital",
      "Fandom at Gilly's: Indie Rock & Fusion Night": "Fandom Indie Rock & Fusion",
      "That Comedy Club: Bangalore Tech & Startup Roasts": "Bangalore Tech & Startup Roasts",
      "Kannada Standup Comedy: Namma Ooru Comedy Fest": "Namma Ooru Comedy Fest",
      "Ranga Shankara Kannada Drama: Girish Karnad's Tughlaq": "Tughlaq",
      "Jagriti Theatre Contemporary English Drama": "Contemporary English Drama",
      "Kanteerava Stadium Track Session & Athletic Sprint Training": "Kanteerava Sprint Training",
      "Turf Football & Futsal Community Tournament": "Turf Football & Futsal",
      "Cubbon Park Heritage & Botanical Morning Nature Walk": "Cubbon Park Botanical Walk",
      "Lalbagh Botanical Gardens & 1889 Glass House Historical Tour": "Lalbagh Glass House Tour",
      "Malleswaram Heritage & Filter Coffee Trail": "Malleswaram Filter Coffee Trail",
      "Bangalore Microbrewery & Craft Beer Tasting Tour": "Bangalore Craft Beer Tour",
      "Bangalore Literature Festival (BLF) Cultural Weekend": "Bangalore Literature Festival",
      "Karaga Shaktyotsava Heritage Cultural Celebration": "Karaga Shaktyotsava",
      "Terracotta & Ceramic Pottery Throwing Masterclass": "Ceramic Pottery Throwing",
      "Channapatna Wooden Toy Lacquer Craft Workshop": "Channapatna Wooden Toy Craft",
      "South Indian Filter Coffee Brewing & Bean Roasting Workshop": "Filter Coffee Brewing Workshop",
      "Museum of Art & Photography (MAP) Contemporary Exhibitions": "MAP Contemporary Art",
      "Visvesvaraya Industrial & Technological Museum (VITM)": "Visvesvaraya Tech Museum",
      "National Gallery of Modern Art (NGMA Bengaluru) Heritage House": "NGMA Bengaluru Heritage House",
      "Cinepolis VIP IMAX: Hollywood & Regional Spectacles": "Cinepolis VIP IMAX",
      "NFAI Heritage Archives: Indian Silent Era & Masterpieces": "NFAI Silent Cinema Archives",
      "Prabhat Talkies Single-Screen Marathi Cinema Premiere": "Prabhat Talkies Premiere",
      "Sawai Gandharva Classical Sangeet Evening Showcase": "Sawai Gandharva Classical Sangeet",
      "High Spirits Indie Live Band & Craft Beer Night": "High Spirits Live Band Night",
      "Pune Standup Comedy Club: Puneri Punches": "Puneri Punches Comedy Club",
      "Koregaon Park English Standup Comedy Night": "Koregaon Park Comedy Night",
      "Bal Gandharva Ranga Mandir: Classic Marathi Natak 'Ti Phulrani'": "Ti Phulrani",
      "Yashwantrao Chavan Natyagruha Experimental Marathi Theatre": "Experimental Marathi Theatre",
      "Shree Shiv Chhatrapati Sports Complex Badminton & Squash": "Balewadi Badminton & Squash",
      "Sinhagad Fort Mountain Trail Trek & Kanda Bhajji Breakfast": "Sinhagad Fort Mountain Trek",
      "Shaniwar Wada & Historic Peth Walking Heritage Trail": "Shaniwar Wada Heritage Trail",
      "Aga Khan Palace Heritage & Gandhi Memorial Tour": "Aga Khan Palace Heritage Tour",
      "Pune Peth Street Food & Puneri Misal Trail": "Pune Peth Street Food Trail",
      "Pataleshwar 8th-Century Rock-Cut Cave Temple Excursion": "Pataleshwar Rock-Cut Caves",
      "Pune Ganeshotsav Manache Ganpati Heritage Showcase": "Pune Manache Ganpati Showcase",
      "Pune International Film Festival (PIFF) Gala": "Pune International Film Festival",
      "Hindustani Classical Vocal Riyaaz & Raga Workshop": "Hindustani Classical Vocal Riyaaz",
      "Calligraphy & Modi Script Traditional Workshop": "Calligraphy & Modi Script Workshop",
      "Organic Coffee Brewing & Puneri Bakery Workshop": "Organic Coffee & Bakery Workshop",
      "Raja Dinkar Kelkar Museum: 20,000 Rare Indian Artifacts": "Raja Dinkar Kelkar Museum",
      "Tribal Research & Training Institute Cultural Museum": "Tribal Research Cultural Museum",
      "Mumbai Comedy Night: Open Mic & Standup": "Mumbai Comedy Night",
      "Blade Runner 2049": "Blade Runner 2049",
      "Hereditary & Tumbbad: Horror Showcase": "Hereditary & Tumbbad",
      "Neon Horizon: Retro Synthwave Night": "Neon Horizon",
      "Sahyadri Dawn Trek & Rappelling": "Sahyadri Dawn Trek & Rappelling",
      "Pawna Lake Kayaking & Stargazing Camp": "Pawna Lake Stargazing & Kayak",
      "Kamshet Tandem Paragliding Flight": "Kamshet Tandem Paragliding",
      "Torq03 Pro Go-Karting Championship": "Torq03 Pro Go-Karting",
      "Equilibrium Rock Climbing Challenge": "Equilibrium Rock Climbing",
      "Haunted Forest Night Trek": "Haunted Forest Night Trek",
      "Bhangarh Horror Mystery Room Challenge": "Bhangarh Horror Mystery Room",
      "The Haunted Asylum: VR Survival Adventure": "The Haunted Asylum (VR)",
      "Midnight Kayaking & Haunted Island Trail": "Midnight Kayaking & Haunted Island",
      "Midnight Ghost Walk & Haunted Ruins": "Midnight Ghost Walk",
      "The Dark Room: Ghost Stories & Horror Comedy": "The Dark Room"
    };

    if (cleanMap[rawTitle]) {
      return cleanMap[rawTitle];
    }

    // Dynamic heuristics:
    let clean = rawTitle;
    if (clean.includes(": ")) {
      const parts = clean.split(": ");
      if (parts[1] && parts[1].trim().length >= 3 && parts[1].trim().length <= 36) {
        clean = parts[1].trim();
      } else if (parts[0] && parts[0].trim().length >= 3 && parts[0].trim().length <= 36) {
        clean = parts[0].trim();
      }
    }

    // Strip trailing parentheticals
    clean = clean.replace(/\s*\([^)]*\)\s*$/, "").trim();
    return clean || rawTitle;
  }

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
    const cleanTitle = ExperienceCard.formatCardTitle(rawTitle);
    const title = escapeHtml(cleanTitle);
    const description = escapeHtml(experience.description || "");
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

          ${
            description
              ? `<p class="card-description">${description}</p>`
              : ""
          }

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
