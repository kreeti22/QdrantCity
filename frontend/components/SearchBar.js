/**
 * SearchBar Component
 *
 * Full-width BookMyShow-style search bar for movies, events, concerts and plays.
 */

export class SearchBar {
  constructor({
    container,
    onSearch,
    onVoiceInput,
    placeholder = "Search for Movies, Events, Plays, Sports and Activities...",
  }) {
    this.container = container;
    this.onSearch = onSearch;
    this.onVoiceInput = onVoiceInput;
    this.placeholder = placeholder;
    this.inputElement = null;
    this.buttonElement = null;
    this.micButton = null;
    this.isListening = false;
    this.speechRecognition = null;
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
          <button
            type="button"
            class="search-mic-btn"
            id="search-mic-btn"
            aria-label="Use voice input"
            title="Voice Input (Offline)"
          >
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
              <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
              <line x1="12" y1="19" x2="12" y2="23"></line>
              <line x1="8" y1="23" x2="16" y2="23"></line>
            </svg>
          </button>
          <button type="submit" id="search-submit-btn" class="search-submit-btn" aria-label="Search">
            <span>Search</span>
          </button>
        </div>
      </form>
    `;

    this.setupVoiceInput();

    const form = this.container.querySelector("#search-form");
    this.inputElement = this.container.querySelector("#search-input");
    this.buttonElement = this.container.querySelector("#search-submit-btn");
    this.micButton = this.container.querySelector("#search-mic-btn");

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

    if (this.micButton) {
      this.micButton.addEventListener("click", () => this.toggleVoiceInput());
    }
  }

  setupVoiceInput() {
    // Try to initialize offline speech recognition
    // This uses Web Speech API if available, or falls back to manual entry
    this.speechRecognition = null;
    
    // Check for browser speech recognition support
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    
    if (SpeechRecognition) {
      try {
        this.speechRecognition = new SpeechRecognition();
        this.speechRecognition.continuous = false;
        this.speechRecognition.lang = "en-US";
        this.speechRecognition.interimResults = false;
        
        this.speechRecognition.onstart = () => {
          this.isListening = true;
          this.updateMicState(true);
        };
        
        this.speechRecognition.onend = () => {
          this.isListening = false;
          this.updateMicState(false);
        };
        
        this.speechRecognition.onerror = (event) => {
          console.debug("Speech recognition error:", event.error);
          this.isListening = false;
          this.updateMicState(false);
        };
        
        this.speechRecognition.onresult = (event) => {
          if (event.results.length > 0) {
            const transcript = event.results[0][0].transcript;
            this.insertTextToInput(transcript);
            if (this.onVoiceInput) {
              this.onVoiceInput(transcript);
            }
          }
        };
        
        console.log("Speech recognition initialized (browser-based)");
      } catch (e) {
        console.debug("Speech recognition initialization failed:", e);
        this.speechRecognition = null;
      }
    } else {
      console.log("Browser speech recognition not available - using offline mode");
    }
  }

  toggleVoiceInput() {
    if (this.speechRecognition) {
      if (this.isListening) {
        this.speechRecognition.stop();
      } else {
        this.speechRecognition.start();
      }
    } else {
      // Speech recognition not available, show informative message
      console.log("Voice input requires browser support. Please use a browser with Web Speech API support for offline voice input, or type your query manually.");
    }
  }

  updateMicState(isListening) {
    if (this.micButton) {
      if (isListening) {
        this.micButton.classList.add("listening");
        this.micButton.setAttribute("aria-label", "Listening... click to stop");
      } else {
        this.micButton.classList.remove("listening");
        this.micButton.setAttribute("aria-label", "Use voice input");
      }
    }
  }

  insertTextToInput(text) {
    if (this.inputElement) {
      this.inputElement.value = text;
      this.inputElement.focus();
    }
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
