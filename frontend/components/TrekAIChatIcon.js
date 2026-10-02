/**
 * TrekAI Chat Icon Component
 *
 * Floating chatbot icon in bottom-right corner.
 * Matches QdrantCity warm beige, brown-accented theme.
 */

export class TrekAIChatIcon {
  constructor({ onClick, onOpenChat }) {
    this.onClick = onClick;
    this.onOpenChat = onOpenChat;
    this.container = null;
    this.isChatOpen = false;
    this.render();
  }

  render() {
    this.container = document.createElement("div");
    this.container.className = "trekai-chat-icon-container";
    this.container.innerHTML = `
      <button
        type="button"
        class="trekai-chat-icon"
        id="trekai-chat-icon"
        aria-label="Open TrekAI chatbot"
        title="TrekAI - Your Offline Assistant"
      >
        <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
          <circle cx="12" cy="12" r="1"></circle>
          <circle cx="12" cy="5" r="1"></circle>
          <circle cx="12" cy="19" r="1"></circle>
        </svg>
        <span class="trekai-badge" id="trekai-badge"></span>
      </button>
    `;

    const iconBtn = this.container.querySelector("#trekai-chat-icon");
    if (iconBtn) {
      iconBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.toggleChat();
      });
    }
  }

  toggleChat() {
    this.isChatOpen = !this.isChatOpen;
    if (this.onOpenChat) {
      this.onOpenChat(this.isChatOpen);
    }
    if (this.container) {
      const icon = this.container.querySelector("#trekai-chat-icon");
      if (icon) {
        if (this.isChatOpen) {
          icon.classList.add("open");
        } else {
          icon.classList.remove("open");
        }
      }
    }
  }

  isOpen() {
    return this.isChatOpen;
  }

  updateBadge(text) {
    const badge = this.container.querySelector("#trekai-badge");
    if (badge) {
      badge.textContent = text;
    }
  }

  getContainer() {
    return this.container;
  }

  remove() {
    if (this.container && this.container.parentNode) {
      this.container.parentNode.removeChild(this.container);
    }
  }
}