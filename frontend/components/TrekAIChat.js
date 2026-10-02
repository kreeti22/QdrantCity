/**
 * TrekAI Chat Panel Component
 *
 * Full chat interface with message history, input, and voice input.
 * Offline-first implementation using local intent detection and templates.
 */

import { apiClient } from "../services/client.js";

export class TrekAIChat {
  constructor({ container, onClose }) {
    this.container = container;
    this.onClose = onClose;
    this.userId = "local-default";
    this.conversationId = "";
    this.messages = [];
    this.context = {};
    this.isListening = false;
    this.init();
  }

  async init() {
    this.renderLayout();
    this.loadConversation();
    this.registerEventListeners();
  }

  renderLayout() {
    this.container.innerHTML = `
      <div class="trekai-chat-panel" id="trekai-chat-panel">
        <div class="trekai-chat-header" id="trekai-chat-header">
          <div class="trekai-chat-header-title">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
            </svg>
            <span>TrekAI</span>
          </div>
          <button type="button" class="trekai-chat-close" id="trekai-chat-close" aria-label="Close chat">&times;</button>
        </div>

        <div class="trekai-chat-messages" id="trekai-chat-messages" role="log" aria-live="polite">
          <!-- Messages will be inserted here -->
        </div>

        <div class="trekai-chat-input-container">
          <div class="trekai-chat-input-wrapper">
            <button
              type="button"
              class="trekai-mic-btn"
              id="trekai-mic-btn"
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
            <input
              type="text"
              id="trekai-input"
              class="trekai-input"
              placeholder="Ask me anything..."
              autocomplete="off"
              spellcheck="false"
              aria-label="Ask TrekAI a question"
            />
            <button
              type="button"
              class="trekai-send-btn"
              id="trekai-send-btn"
              aria-label="Send message"
            >
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
              </svg>
            </button>
          </div>
          <div class="trekai-input-actions">
            <button
              type="button"
              class="trekai-clear-btn"
              id="trekai-clear-btn"
              aria-label="Clear conversation"
              title="Clear conversation"
            >
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="3 6 5 6 21 6"></polyline>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
              </svg>
            </button>
          </div>
        </div>

        <div class="trekai-status-bar" id="trekai-status-bar">
          <span class="trekai-status-dot"></span>
          <span class="trekai-status-text">Offline • Local Processing</span>
        </div>
      </div>
    `;

    this.setupInputHandlers();
    this.setupVoiceInput();
  }

  setupInputHandlers() {
    const input = this.container.querySelector("#trekai-input");
    const sendBtn = this.container.querySelector("#trekai-send-btn");
    const closeBtn = this.container.querySelector("#trekai-chat-close");
    const clearBtn = this.container.querySelector("#trekai-clear-btn");
    const micBtn = this.container.querySelector("#trekai-mic-btn");

    // Send message on Enter key
    if (input) {
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          this.handleSend();
        }
      });
    }

    // Send button
    if (sendBtn) {
      sendBtn.addEventListener("click", () => this.handleSend());
    }

    // Close button
    if (closeBtn) {
      closeBtn.addEventListener("click", () => {
        if (this.onClose) {
          this.onClose();
        }
      });
    }

    // Clear button
    if (clearBtn) {
      clearBtn.addEventListener("click", () => this.clearConversation());
    }

    // Voice input button
    if (micBtn) {
      micBtn.addEventListener("click", () => this.toggleVoiceInput());
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
      this.showSystemMessage(
        "Voice input requires browser support. Please use a browser with Web Speech API support for offline voice input, or type your query manually."
      );
    }
  }

  updateMicState(isListening) {
    const micBtn = this.container.querySelector("#trekai-mic-btn");
    if (micBtn) {
      if (isListening) {
        micBtn.classList.add("listening");
        micBtn.setAttribute("aria-label", "Listening... click to stop");
      } else {
        micBtn.classList.remove("listening");
        micBtn.setAttribute("aria-label", "Use voice input");
      }
    }
  }

  insertTextToInput(text) {
    const input = this.container.querySelector("#trekai-input");
    if (input) {
      input.value = text;
      input.focus();
    }
  }

  async handleSend() {
    const input = this.container.querySelector("#trekai-input");
    if (!input) return;

    const message = input.value.trim();
    if (!message) return;

    // Add user message
    this.addMessage("user", message);

    // Clear input
    input.value = "";
    input.focus();

    // Show loading
    this.showLoading(true);

    try {
      // Call TrekAI API
      const response = await apiClient.chat(message, this.context);

      // Add assistant response
      this.addMessage("assistant", response.response);

      // Update context for follow-up questions
      this.context = response.context || {};
      
      // Register interaction for personalization
      await this.registerInteraction(response.intent, response.related_events);

      // Show follow-up suggestions
      this.showFollowUpSuggestions(response.response);

    } catch (error) {
      console.error("Chat failed:", error);
      this.addMessage("assistant", "I encountered an error processing your request. Please try again.");
    } finally {
      this.showLoading(false);
    }
  }

  async registerInteraction(intent, relatedEvents) {
    try {
      // Record interaction for personalization
      if (intent && relatedEvents && relatedEvents.length > 0) {
        const eventId = relatedEvents[0]?.id || null;
        await apiClient.recordInteraction(this.userId, "chat", eventId, intent, {
          message: this.messages[this.messages.length - 1]?.content || "",
        });
      }
    } catch (e) {
      console.debug("Could not register chat interaction:", e);
    }
  }

  addMessage(role, content) {
    const message = {
      role,
      content,
      timestamp: new Date().toISOString(),
    };
    this.messages.push(message);

    const messagesContainer = this.container.querySelector("#trekai-chat-messages");
    if (!messagesContainer) return;

    const messageEl = document.createElement("div");
    messageEl.className = `trekai-message ${role}`;
    messageEl.innerHTML = `
      <div class="trekai-message-content">${this.formatMessage(content)}</div>
      <span class="trekai-message-time">${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
    `;

    messagesContainer.appendChild(messageEl);
    this.scrollToBottom();
  }

  showSystemMessage(content) {
    const messagesContainer = this.container.querySelector("#trekai-chat-messages");
    if (!messagesContainer) return;

    const messageEl = document.createElement("div");
    messageEl.className = "trekai-message system";
    messageEl.innerHTML = `<div class="trekai-message-content">${content}</div>`;

    messagesContainer.appendChild(messageEl);
    this.scrollToBottom();
  }

  showLoading(isLoading) {
    const messagesContainer = this.container.querySelector("#trekai-chat-messages");
    if (!messagesContainer) return;

    const loadingEl = messagesContainer.querySelector(".trekai-loading");
    if (isLoading) {
      if (!loadingEl) {
        const el = document.createElement("div");
        el.className = "trekai-loading";
        el.innerHTML = `
          <span class="trekai-message-content">
            <span class="trekai-spinner"></span> Thinking...
          </span>
        `;
        messagesContainer.appendChild(el);
        this.scrollToBottom();
      }
    } else if (loadingEl) {
      loadingEl.remove();
    }
  }

  showFollowUpSuggestions(response) {
    const messagesContainer = this.container.querySelector("#trekai-chat-messages");
    if (!messagesContainer) return;

    // Only show suggestions for certain intents
    const followUp = this.getFollowUpSuggestions(response);
    if (!followUp || followUp.length === 0) return;

    const suggestionsContainer = document.createElement("div");
    suggestionsContainer.className = "trekai-follow-up";
    suggestionsContainer.innerHTML = `<div class="trekai-suggestions-title">Try asking:</div>`;

    followUp.forEach((suggestion) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "trekai-suggestion-chip";
      chip.textContent = suggestion;
      chip.addEventListener("click", () => {
        const input = this.container.querySelector("#trekai-input");
        if (input) {
          input.value = suggestion;
          this.handleSend();
        }
      });
      suggestionsContainer.appendChild(chip);
    });

    messagesContainer.appendChild(suggestionsContainer);
    this.scrollToBottom();
  }

  getFollowUpSuggestions(response) {
    // Simple heuristic to suggest follow-ups based on response content
    const suggestions = [];
    const responseLower = response.toLowerCase();

    if (responseLower.includes("event") || responseLower.includes("events")) {
      suggestions.push("Tell me more about movies");
      suggestions.push("Show sports events in Delhi");
      suggestions.push("What's playing tonight?");
    }

    if (responseLower.includes("route") || responseLower.includes("direction")) {
      suggestions.push("Plan a route to the theatre");
      suggestions.push("How do I get to the cinema?");
    }

    if (responseLower.includes("bookmark") || responseLower.includes("saved")) {
      suggestions.push("What events have I saved?");
      suggestions.push("Show me all my bookmarks");
    }

    if (responseLower.includes("hello") || responseLower.includes("hi")) {
      suggestions.push("What can you do?");
      suggestions.push("Tell me about events today");
    }

    return suggestions;
  }

  formatMessage(text) {
    // Convert markdown-like formatting to HTML
    let formatted = text
      .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
      .replace(/\n/g, "<br/>");

    return formatted;
  }

  scrollToBottom() {
    const messagesContainer = this.container.querySelector("#trekai-chat-messages");
    if (messagesContainer) {
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
  }

  clearConversation() {
    this.messages = [];
    this.context = {};
    this.conversationId = "";

    const messagesContainer = this.container.querySelector("#trekai-chat-messages");
    if (messagesContainer) {
      messagesContainer.innerHTML = "";
    }

    const input = this.container.querySelector("#trekai-input");
    if (input) {
      input.value = "";
    }

    this.showSystemMessage("Conversation cleared. How can I help you?");
  }

  loadConversation() {
    // Load from localStorage if available
    const saved = localStorage.getItem("trekai_conversation");
    if (saved) {
      try {
        const data = JSON.parse(saved);
        this.messages = data.messages || [];
        this.context = data.context || {};
        this.conversationId = data.conversationId || "";

        const messagesContainer = this.container.querySelector("#trekai-chat-messages");
        if (messagesContainer && this.messages.length > 0) {
          this.messages.forEach((msg) => {
            this.addMessage(msg.role, msg.content);
          });
        }
      } catch (e) {
        console.debug("Could not load conversation:", e);
      }
    } else {
      // Show welcome message
      this.showSystemMessage(
        "Hello! I'm TrekAI, your offline assistant. Ask me about events, plan routes, check your saved items, or learn about QdrantCity!"
      );
    }
  }

  saveConversation() {
    const data = {
      messages: this.messages,
      context: this.context,
      conversationId: this.conversationId,
    };
    try {
      localStorage.setItem("trekai_conversation", JSON.stringify(data));
    } catch (e) {
      console.debug("Could not save conversation:", e);
    }
  }

  registerEventListeners() {
    // Save conversation on close
    const closeBtn = this.container.querySelector("#trekai-chat-close");
    if (closeBtn) {
      closeBtn.addEventListener("click", () => {
        this.saveConversation();
      });
    }

    // Save conversation periodically
    this.saveInterval = setInterval(() => {
      this.saveConversation();
    }, 30000);
  }

  destroy() {
    if (this.saveInterval) {
      clearInterval(this.saveInterval);
    }
    this.saveConversation();
  }
}