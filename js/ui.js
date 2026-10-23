const UI = {
  toastContainer: null,
  terminalDrawer: null,
  terminalBody: null,

  init() {
    this.toastContainer = document.getElementById('toastContainer');
    this.terminalDrawer = document.getElementById('terminalDrawer');
    this.terminalBody = document.getElementById('terminalBody');

    document.querySelectorAll('.modal-overlay').forEach(overlay => {
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
          overlay.classList.remove('active');
        }
      });
    });

    document.querySelectorAll('.modal-close').forEach(btn => {
      btn.addEventListener('click', () => {
        const modal = btn.closest('.modal-overlay');
        if (modal) modal.classList.remove('active');
      });
    });
  },

  showToast(message, type = 'info', duration = 3500) {
    if (!this.toastContainer) return;
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    let icon = 'ℹ️';
    if (type === 'success') icon = '✅';
    if (type === 'error') icon = '❌';

    toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
    this.toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(-10px) scale(0.95)';
      setTimeout(() => toast.remove(), 250);
    }, duration);
  },

  openModal(modalId) {
    const el = document.getElementById(modalId);
    if (el) el.classList.add('active');
  },

  closeModal(modalId) {
    const el = document.getElementById(modalId);
    if (el) el.classList.remove('active');
  },

  toggleTerminal(force = null) {
    if (!this.terminalDrawer) return;
    if (force !== null) {
      this.terminalDrawer.classList.toggle('open', force);
    } else {
      this.terminalDrawer.classList.toggle('open');
    }
  },

  appendTerminalLog(line, type = '') {
    if (!this.terminalBody) return;
    const div = document.createElement('div');
    div.className = `log-line ${type}`;
    div.textContent = `[${new Date().toLocaleTimeString()}] ${line}`;
    this.terminalBody.appendChild(div);
    this.terminalBody.scrollTop = this.terminalBody.scrollHeight;
  },

  show2FAModal(email, callback) {
    const input = document.getElementById('twoFaCodeInput');
    if (input) input.value = '';
    const emailSpan = document.getElementById('twoFaEmailDisplay');
    if (emailSpan) emailSpan.textContent = email;

    const confirmBtn = document.getElementById('twoFaConfirmBtn');
    const newConfirmBtn = confirmBtn.cloneNode(true);
    confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);

    newConfirmBtn.addEventListener('click', () => {
      const code = input.value.trim();
      if (!code) {
        UI.showToast('Введите 6-значный код 2FA', 'error');
        return;
      }
      UI.closeModal('twoFaModal');
      callback(code);
    });

    this.openModal('twoFaModal');
    if (input) setTimeout(() => input.focus(), 150);
  },

  renderAppCard(app, options = {}) {
    const card = document.createElement('div');
    card.className = 'app-card';
    card.dataset.id = app.id;

    const iconPlaceholder = app.name ? app.name.charAt(0).toUpperCase() : '📦';
    const iconHtml = app.icon 
      ? `<img src="${app.icon}" class="app-icon" alt="${app.name}" onerror="this.outerHTML='<div class=\\'app-icon\\'>${iconPlaceholder}</div>'">`
      : `<div class="app-icon">${iconPlaceholder}</div>`;

    const catBadge = app.category 
      ? `<span class="app-badge cat">${app.category}</span>`
      : '';

    const minIosBadge = app.min_ios
      ? `<span class="app-badge ios">iOS ${app.min_ios}+</span>`
      : '';

    card.innerHTML = `
      <div class="app-card-top">
        ${iconHtml}
        <div class="app-meta">
          <div class="app-name" title="${app.name}">${app.name}</div>
          <div class="app-id-tag">ID: ${app.id}</div>
          <div class="app-badge-row">
            ${catBadge}
            ${minIosBadge}
          </div>
        </div>
      </div>
      <div class="app-card-actions">
        <button class="btn btn-secondary btn-sm" onclick="App.openVersionSelector('${app.id}', '${escape(app.name)}')">
          ⏳ Версии
        </button>
        <button class="btn btn-secondary btn-sm" onclick="App.purchaseApp('${app.id}', '${escape(app.name)}')">
          🔑 Привязать
        </button>
        <button class="btn btn-primary btn-sm" style="flex: 1;" onclick="App.downloadApp('${app.id}', '${escape(app.name)}')">
          ⬇️ Скачать IPA
        </button>
      </div>
    `;

    return card;
  }
};
