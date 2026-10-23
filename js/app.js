const App = {
  currentTab: 'catalog',
  currentCategory: 'all',
  searchQuery: '',
  catalogApps: [],
  catalogAccountFilter: 'all',
  catalogSort: 'name-asc',
  activeAccount: null,
  connectedDevices: [],
  popularApps: [],
  purchasedApps: [],
  libraryIpas: [],

  async init() {
    UI.init();
    this.bindEvents();
    this.initSSE();

    // Load initial system status
    await this.refreshStatus();
    await this.loadTab(this.currentTab);
  },

  initSSE() {
    API.initSSE((type, data) => {
      if (type === 'task_start') {
        UI.appendTerminalLog(`🚀 [${data.type.toUpperCase()}] ${data.title}`, 'info');
        UI.toggleTerminal(true);
      } else if (type === 'task_log') {
        UI.appendTerminalLog(data.line);
      } else if (type === 'task_complete') {
        const cls = data.success ? 'success' : 'error';
        UI.appendTerminalLog(`🏁 ${data.message}`, cls);
        UI.showToast(data.message, data.success ? 'success' : 'error');
        if (data.success) {
          this.loadLibrary();
        }
      } else if (type === 'auth_change') {
        this.refreshStatus();
      }
    });
  },

  bindEvents() {
    // Tab switching
    document.querySelectorAll('.nav-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        const target = tab.dataset.tab;
        this.switchTab(target);
      });
    });

    // Category chips
    document.querySelectorAll('.chip').forEach(chip => {
      chip.addEventListener('click', () => {
        document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        this.currentCategory = chip.dataset.category;
        this.loadPopularApps();
      });
    });

    // Catalog Sort dropdown
    const sortSelect = document.getElementById('catalogSortSelect');
    if (sortSelect) {
      sortSelect.addEventListener('change', (e) => {
        this.catalogSort = e.target.value;
        this.renderCatalogGrid();
      });
    }

    // Search input debounced
    const searchInput = document.getElementById('mainSearchInput');
    let debounceTimer;
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
          this.searchQuery = e.target.value.trim();
          if (this.currentTab === 'catalog') {
            this.renderCatalogGrid();
          } else if (this.currentTab === 'search') {
            this.executeAppStoreSearch();
          } else {
            this.loadPopularApps();
          }
        }, 300);
      });
    }

    // Login Form Submit
    const loginForm = document.getElementById('loginForm');
    if (loginForm) {
      loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        await this.handleLoginSubmit();
      });
    }

    // Add Custom App Form
    const customAppForm = document.getElementById('addCustomAppForm');
    if (customAppForm) {
      customAppForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const name = document.getElementById('customAppName').value.trim();
        const id = document.getElementById('customAppId').value.trim();
        if (!name || !id) return;
        const res = await API.addCustomApp(name, id);
        if (res.success) {
          UI.showToast('Приложение добавлено в список!', 'success');
          UI.closeModal('addCustomAppModal');
          document.getElementById('customAppName').value = '';
          document.getElementById('customAppId').value = '';
          this.loadCustomApps();
        } else {
          UI.showToast(res.error || 'Ошибка добавления', 'error');
        }
      });
    }
  },

  async switchTab(tabId) {
    this.currentTab = tabId;
    document.querySelectorAll('.nav-tab').forEach(t => {
      t.classList.toggle('active', t.dataset.tab === tabId);
    });

    document.querySelectorAll('.tab-view').forEach(v => {
      v.style.display = v.id === `${tabId}TabView` ? 'block' : 'none';
    });

    const searchBox = document.getElementById('mainSearchBox');
    const categoryChips = document.getElementById('categoryChips');
    if (searchBox) searchBox.style.display = (tabId === 'catalog' || tabId === 'popular' || tabId === 'search') ? 'block' : 'none';
    if (categoryChips) categoryChips.style.display = (tabId === 'popular') ? 'flex' : 'none';

    await this.loadTab(tabId);
  },

  async loadTab(tabId) {
    if (tabId === 'catalog') {
      await this.loadCatalogApps();
    } else if (tabId === 'popular') {
      await this.loadPopularApps();
    } else if (tabId === 'purchases') {
      await this.loadPurchases();
    } else if (tabId === 'library') {
      await this.loadLibrary();
    } else if (tabId === 'devices') {
      await this.loadDevices();
    } else if (tabId === 'custom') {
      await this.loadCustomApps();
    } else if (tabId === 'accounts') {
      await this.loadAccountsList();
    }
  },

  async refreshStatus() {
    const status = await API.getStatus();
    this.activeAccount = status.account;

    // Header Account Pill
    const pill = document.getElementById('headerAccountPill');
    const nameEl = document.getElementById('headerAccountName');
    const emailEl = document.getElementById('headerAccountEmail');
    const avatarEl = document.getElementById('headerAccountAvatar');

    if (status && status.success !== false) {
      if (this.activeAccount && this.activeAccount.is_logged_in) {
        nameEl.textContent = this.activeAccount.name;
        emailEl.textContent = this.activeAccount.email;
        avatarEl.textContent = this.activeAccount.name.charAt(0).toUpperCase();
      } else {
        nameEl.textContent = 'Вход в Apple ID';
        emailEl.textContent = 'Нажмите для авторизации';
        avatarEl.textContent = '';
      }

      // Devices status badge
      const devPill = document.getElementById('headerDevicePill');
      const devDot = document.getElementById('headerDeviceDot');
      const devText = document.getElementById('headerDeviceText');
      if (status.devices_count > 0) {
        devDot.className = 'status-dot online';
        devText.textContent = `Подключено: ${status.devices_count} устр.`;
      } else {
        devDot.className = 'status-dot';
        devText.textContent = 'Устройства не найдены';
      }

      // Badges on tabs
      const libBadge = document.getElementById('libraryTabBadge');
      if (libBadge) libBadge.textContent = status.ipas_count;
    } else {
      // Offline / GitHub Pages mode
      const devDot = document.getElementById('headerDeviceDot');
      const devText = document.getElementById('headerDeviceText');
      if (devDot) devDot.className = 'status-dot';
      if (devText) devText.textContent = 'Офлайн (OTA режим)';
    }
  },

  async loadCatalogApps() {
    const container = document.getElementById('catalogAppsGrid');
    if (!container) return;
    if (!this.catalogApps || this.catalogApps.length === 0) {
      container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-muted);">Загрузка каталога приложений...</div>';
      const apps = await API.getCatalogApps();
      this.catalogApps = apps || [];
      this.populateCatalogAccountTabs();
    }
    this.renderCatalogGrid();
  },

  populateCatalogAccountTabs() {
    const tabsWrapper = document.getElementById('catalogAccountTabs');
    if (!tabsWrapper) return;
    tabsWrapper.innerHTML = '';

    const accCounts = {};
    this.catalogApps.forEach(a => {
      const acc = a.account || 'unknown';
      accCounts[acc] = (accCounts[acc] || 0) + 1;
    });

    const allTab = document.createElement('div');
    allTab.className = `account-tab ${this.catalogAccountFilter === 'all' ? 'active' : ''}`;
    allTab.dataset.acc = 'all';
    allTab.innerHTML = `Все аккаунты <span class="count">${this.catalogApps.length}</span>`;
    allTab.addEventListener('click', () => {
      this.catalogAccountFilter = 'all';
      tabsWrapper.querySelectorAll('.account-tab').forEach(t => t.classList.remove('active'));
      allTab.classList.add('active');
      this.renderCatalogGrid();
    });
    tabsWrapper.appendChild(allTab);

    Object.keys(accCounts).sort().forEach(acc => {
      const tab = document.createElement('div');
      tab.className = `account-tab ${this.catalogAccountFilter === acc ? 'active' : ''}`;
      tab.dataset.acc = acc;
      tab.innerHTML = `${acc} <span class="count">${accCounts[acc]}</span>`;
      tab.addEventListener('click', () => {
        this.catalogAccountFilter = acc;
        tabsWrapper.querySelectorAll('.account-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        this.renderCatalogGrid();
      });
      tabsWrapper.appendChild(tab);
    });
  },

  parseSizeInMb(sizeStr) {
    if (!sizeStr) return 0;
    const num = parseFloat(sizeStr.replace(',', '.'));
    if (sizeStr.includes('ГБ') || sizeStr.includes('GB')) return num * 1024;
    if (sizeStr.includes('КБ') || sizeStr.includes('KB')) return num / 1024;
    return num || 0;
  },

  renderCatalogGrid() {
    const container = document.getElementById('catalogAppsGrid');
    if (!container) return;
    container.innerHTML = '';

    let list = [...this.catalogApps];

    // Filter by account
    if (this.catalogAccountFilter !== 'all') {
      list = list.filter(a => a.account === this.catalogAccountFilter);
    }

    // Filter by search query
    if (this.searchQuery) {
      const q = this.searchQuery.toLowerCase();
      list = list.filter(a => 
        (a.name && a.name.toLowerCase().includes(q)) ||
        (a.bundleId && a.bundleId.toLowerCase().includes(q)) ||
        (a.account && a.account.toLowerCase().includes(q))
      );
    }

    // Sort
    const sort = this.catalogSort;
    list.sort((a, b) => {
      if (sort === 'name-asc') return (a.name || '').localeCompare(b.name || '', 'ru');
      if (sort === 'name-desc') return (b.name || '').localeCompare(a.name || '', 'ru');
      if (sort === 'size-desc') return this.parseSizeInMb(b.size) - this.parseSizeInMb(a.size);
      if (sort === 'size-asc') return this.parseSizeInMb(a.size) - this.parseSizeInMb(b.size);
      if (sort === 'version-desc') return (b.version || '').localeCompare(a.version || '', undefined, { numeric: true });
      if (sort === 'account') return (a.account || '').localeCompare(b.account || '');
      return 0;
    });

    if (list.length === 0) {
      container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-muted);">Приложения не найдены</div>';
      return;
    }

    list.forEach(app => {
      const card = document.createElement('div');
      card.className = 'app-card';

      const iconPlaceholder = app.name ? app.name.charAt(0).toUpperCase() : '📱';
      const iconHtml = app.icon 
        ? `<img src="${app.icon}" class="app-icon" alt="${app.name}" onerror="this.outerHTML='<div class=\\'app-icon\\'>${iconPlaceholder}</div>'">`
        : `<div class="app-icon">${iconPlaceholder}</div>`;

      const otaUrl = `itms-services://?action=download-manifest&url=${encodeURIComponent(app.manifestUrl)}`;

      card.innerHTML = `
        <div class="app-card-top">
          ${iconHtml}
          <div class="app-meta">
            <div class="app-name" title="${app.name}">${app.name}</div>
            <div class="app-id-tag">${app.bundleId}</div>
            <div class="app-badge-row">
              <span class="app-badge ios">v${app.version || '1.0'}</span>
              <span class="app-badge">${app.size || 'IPA'}</span>
              <span class="app-badge cat" style="max-width: 130px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${app.account}">${app.account || 'Signed'}</span>
            </div>
          </div>
        </div>
        <div class="app-card-actions">
          <a href="${otaUrl}" class="btn btn-primary btn-sm" style="flex: 1; text-decoration: none; text-align: center; justify-content: center;">
            📲 Установить (OTA)
          </a>
          <button class="btn btn-secondary btn-sm" onclick="App.installCatalogToDevice('${app.bundleId}', '${escape(app.name)}')">
            ⚡ По USB
          </button>
          <a href="https://github.com/FS13Fid/ipa-studio/releases/download/v1.0/${encodeURIComponent(app.account ? `${app.account}_${app.bundleId}_${app.version}.ipa` : `${app.name}.${app.version}.ipa`)}" 
             class="btn btn-secondary btn-sm btn-icon" title="Скачать .IPA файл" download>💾</a>
        </div>
      `;
      container.appendChild(card);
    });
  },

  async installCatalogToDevice(bundleId, appName) {
    const unescapedName = unescape(appName);
    const devices = await API.getDevices();
    if (!devices || devices.length === 0) {
      UI.openModal('deviceHelperModal');
      return;
    }

    const select = document.getElementById('installDeviceSelect');
    select.innerHTML = '';
    devices.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d.udid;
      opt.textContent = `${d.name} (${d.ios_version}) - ${d.connection}`;
      select.appendChild(opt);
    });

    document.getElementById('installIpaName').textContent = unescapedName;
    const confirmBtn = document.getElementById('confirmInstallBtn');
    const newBtn = confirmBtn.cloneNode(true);
    confirmBtn.parentNode.replaceChild(newBtn, confirmBtn);

    newBtn.addEventListener('click', async () => {
      const udid = select.value;
      UI.closeModal('installModal');
      UI.showToast(`Установка ${unescapedName} на iPhone...`, 'info');
      await API.installCatalogApp(bundleId, udid);
    });

    UI.openModal('installModal');
  },

  async loadPopularApps() {
    const container = document.getElementById('popularAppsGrid');
    if (!container) return;
    container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-muted);">Загрузка каталога приложений...</div>';

    const res = await API.getPopularApps(this.currentCategory, this.searchQuery, 100, 0);
    container.innerHTML = '';
    if (!res.apps || res.apps.length === 0) {
      container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-muted);">Приложения не найдены</div>';
      return;
    }

    res.apps.forEach(app => {
      const card = UI.renderAppCard(app);
      container.appendChild(card);

      // Lazy-load iTunes high-res artwork in background
      API.lookupApp(app.id).then(meta => {
        if (meta && meta.icon) {
          const img = card.querySelector('.app-icon');
          if (img && img.tagName === 'DIV') {
            const newImg = document.createElement('img');
            newImg.src = meta.icon;
            newImg.className = 'app-icon';
            newImg.alt = app.name;
            img.replaceWith(newImg);
          }
        }
      });
    });
  },

  async loadPurchases() {
    const container = document.getElementById('purchasesGrid');
    if (!container) return;
    container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-muted);">Синхронизация покупок Apple ID... Это может занять некоторое время.</div>';

    const res = await API.getPurchasedApps(true);
    container.innerHTML = '';
    if (!res.success || !res.apps || res.apps.length === 0) {
      container.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-muted);">
        ${res.error || 'История покупок пуста или требуется авторизация в Apple ID'}
      </div>`;
      return;
    }

    res.apps.forEach(app => {
      const card = UI.renderAppCard({
        id: app.id,
        name: app.name,
        category: app.kind,
        min_ios: app.purchase_date ? `Куплено: ${app.purchase_date.split(' ')[0]}` : null
      });
      container.appendChild(card);
    });
  },

  async executeAppStoreSearch() {
    const container = document.getElementById('searchAppsGrid');
    if (!container) return;
    if (!this.searchQuery) {
      container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-muted);">Введите название или ID приложения в строку поиска</div>';
      return;
    }

    container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-muted);">Поиск в App Store...</div>';
    const res = await API.search(this.searchQuery);
    container.innerHTML = '';
    if (!res.results || res.results.length === 0) {
      container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-muted);">По запросу ничего не найдено</div>';
      return;
    }

    res.results.forEach(app => {
      const card = UI.renderAppCard(app);
      container.appendChild(card);
    });
  },

  async loadLibrary() {
    const container = document.getElementById('libraryGrid');
    if (!container) return;
    container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-muted);">Загрузка библиотеки скачанных IPA...</div>';

    const ipas = await API.getLibrary();
    container.innerHTML = '';
    if (!ipas || ipas.length === 0) {
      container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-muted);">Папка Apps пуста. Скачайте приложение из каталога!</div>';
      return;
    }

    ipas.forEach(ipa => {
      const card = document.createElement('div');
      card.className = 'app-card';
      const iconSrc = ipa.icon_base64 || '';
      const iconHtml = iconSrc 
        ? `<img src="${iconSrc}" class="app-icon" alt="${ipa.name}">`
        : `<div class="app-icon">📦</div>`;

      card.innerHTML = `
        <div class="app-card-top">
          ${iconHtml}
          <div class="app-meta">
            <div class="app-name">${ipa.name}</div>
            <div class="app-id-tag">${ipa.bundle_id || ipa.filename}</div>
            <div class="app-badge-row">
              <span class="app-badge ios">iOS ${ipa.min_ios || '12.0'}+</span>
              <span class="app-badge">${ipa.size_formatted}</span>
              ${ipa.version ? `<span class="app-badge cat">v${ipa.version}</span>` : ''}
            </div>
          </div>
        </div>
        <div class="app-card-actions">
          <button class="btn btn-danger btn-sm btn-icon" onclick="App.deleteIpa('${escape(ipa.filename)}')">🗑️</button>
          <a href="/download-ipa/${encodeURIComponent(ipa.filename)}" class="btn btn-secondary btn-sm" download>💾 Сохранить</a>
          <button class="btn btn-primary btn-sm" style="flex: 1;" onclick="App.openInstallModal('${escape(ipa.filename)}', '${ipa.min_ios || ''}')">
            📲 Установить на iPhone
          </button>
        </div>
      `;
      container.appendChild(card);
    });

    const badge = document.getElementById('libraryTabBadge');
    if (badge) badge.textContent = ipas.length;
  },

  async loadDevices() {
    const container = document.getElementById('devicesContainer');
    if (!container) return;
    container.innerHTML = '<div style="text-align: center; padding: 40px; color: var(--text-muted);">Поиск подключенных устройств (USB / Wi-Fi)...</div>';

    const devices = await API.getDevices();
    this.connectedDevices = devices;
    container.innerHTML = '';
    if (!devices || devices.length === 0) {
      container.innerHTML = `
        <div style="background: var(--bg-card); border: 1px dashed var(--border-color); border-radius: var(--radius-md); padding: 40px; text-align: center;">
          <div style="font-size: 36px; margin-bottom: 12px;">🔌</div>
          <div style="font-size: 16px; font-weight: 700; margin-bottom: 6px;">Устройства не подключены</div>
          <div style="font-size: 13px; color: var(--text-secondary); max-width: 440px; margin: 0 auto 16px;">
            Подключите iPhone или iPad к компьютеру по проводу Lightning / Type-C и обязательно нажмите «Доверять этому компьютеру» на экране устройства.
          </div>
          <button class="btn btn-secondary" onclick="App.loadDevices()">🔄 Обновить список</button>
        </div>
      `;
      return;
    }

    devices.forEach(dev => {
      const card = document.createElement('div');
      card.className = 'app-card';
      card.style.marginBottom = '16px';
      card.innerHTML = `
        <div style="display: flex; align-items: center; justify-content: space-between;">
          <div style="display: flex; align-items: center; gap: 14px;">
            <div style="width: 48px; height: 48px; border-radius: 12px; background: rgba(52, 199, 89, 0.15); display: flex; align-items: center; justify-content: center; font-size: 24px;">📱</div>
            <div>
              <div style="font-size: 16px; font-weight: 700;">${dev.name}</div>
              <div style="font-size: 12px; color: var(--text-secondary);">iOS ${dev.ios_version} • UDID: ${dev.display_udid} • Подключение: ${dev.connection}</div>
            </div>
          </div>
          <div style="display: flex; gap: 8px;">
            <button class="btn btn-secondary btn-sm" onclick="App.inspectDeviceApps('${dev.udid}')">📋 Приложения</button>
          </div>
        </div>
      `;
      container.appendChild(card);
    });
  },

  async loadCustomApps() {
    const container = document.getElementById('customAppsContainer');
    if (!container) return;
    const apps = await API.getCustomApps();
    container.innerHTML = '';
    if (!apps || apps.length === 0) {
      container.innerHTML = '<div style="text-align: center; padding: 40px; color: var(--text-muted);">Пользовательский список пуст. Нажмите «Добавить приложение» выше!</div>';
      return;
    }

    const grid = document.createElement('div');
    grid.className = 'apps-grid';
    apps.forEach(app => {
      const card = UI.renderAppCard(app);
      grid.appendChild(card);
    });
    container.appendChild(grid);
  },

  async loadAccountsList() {
    const container = document.getElementById('savedAccountsContainer');
    if (!container) return;
    const res = await API.getAccounts();
    container.innerHTML = '';

    if (res.active && res.active.is_logged_in) {
      const activeEl = document.createElement('div');
      activeEl.className = 'app-card';
      activeEl.style.borderColor = 'var(--accent-green)';
      activeEl.innerHTML = `
        <div style="display: flex; align-items: center; justify-content: space-between;">
          <div>
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="font-weight: 700;">${res.active.name}</span>
              <span class="app-badge ios">Активный</span>
              <span class="app-badge cat">${res.active.storefront || 'RUS'}</span>
            </div>
            <div style="font-size: 13px; color: var(--text-secondary); margin-top: 4px;">${res.active.email}</div>
          </div>
          <button class="btn btn-danger btn-sm" onclick="App.logout()">Выйти</button>
        </div>
      `;
      container.appendChild(activeEl);
    }

    if (res.saved && res.saved.length > 0) {
      res.saved.forEach(acc => {
        const row = document.createElement('div');
        row.className = 'app-card';
        row.style.marginTop = '10px';
        row.innerHTML = `
          <div style="display: flex; align-items: center; justify-content: space-between;">
            <div>
              <div style="font-weight: 600;">${acc}</div>
              <div style="font-size: 12px; color: var(--text-muted);">Сохраненный аккаунт</div>
            </div>
            <div style="display: flex; gap: 8px;">
              <button class="btn btn-secondary btn-sm" onclick="App.switchAccount('${acc}')">Переключиться</button>
              <button class="btn btn-danger btn-sm btn-icon" onclick="App.deleteAccount('${acc}')">🗑️</button>
            </div>
          </div>
        `;
        container.appendChild(row);
      });
    }
  },

  async handleLoginSubmit() {
    const email = document.getElementById('loginEmail').value.trim();
    const password = document.getElementById('loginPassword').value;
    const authCode = document.getElementById('loginAuthCode').value.trim() || null;
    if (!email || !password) return;

    UI.showToast('Вход в аккаунт Apple...', 'info');
    const res = await API.login(email, password, authCode);

    if (res.success) {
      UI.showToast(`Успешный вход: ${res.account.name}!`, 'success');
      UI.closeModal('loginModal');
      await this.refreshStatus();
      await this.loadTab(this.currentTab);
    } else if (res.needs_2fa) {
      UI.closeModal('loginModal');
      UI.show2FAModal(email, async (code) => {
        UI.showToast('Подтверждение 2FA...', 'info');
        const retryRes = await API.login(email, password, code);
        if (retryRes.success) {
          UI.showToast(`Успешный вход: ${retryRes.account.name}!`, 'success');
          await this.refreshStatus();
          await this.loadTab(this.currentTab);
        } else {
          UI.showToast(retryRes.error || 'Ошибка входа по 2FA', 'error');
        }
      });
    } else {
      UI.showToast(res.error || 'Ошибка входа', 'error');
    }
  },

  async logout() {
    if (!confirm('Вы уверены, что хотите выйти из текущего аккаунта Apple?')) return;
    await API.logout();
    UI.showToast('Вы вышли из аккаунта Apple', 'info');
    await this.refreshStatus();
    await this.loadTab(this.currentTab);
  },

  async switchAccount(email) {
    UI.showToast(`Переключение на аккаунт ${email}...`, 'info');
    const res = await API.switchAccount(email);
    if (res.success) {
      UI.showToast(`Переключено на ${email}`, 'success');
      await this.refreshStatus();
      await this.loadTab(this.currentTab);
    } else {
      UI.showToast(res.error || 'Ошибка переключения', 'error');
    }
  },

  async deleteAccount(email) {
    if (!confirm(`Удалить сохраненный аккаунт ${email}?`)) return;
    await API.deleteAccount(email);
    UI.showToast(`Аккаунт ${email} удален`, 'info');
    await this.loadAccountsList();
  },

  async purchaseApp(appId, appName) {
    const unescapedName = unescape(appName);
    UI.showToast(`Привязка лицензии: ${unescapedName}...`, 'info');
    const res = await API.purchase(appId, null, false);
    if (res.success) {
      UI.showToast(`Лицензия для ${unescapedName} успешно получена!`, 'success');
    } else {
      UI.showToast(res.error || 'Не удалось привязать приложение', 'error');
    }
  },

  async downloadApp(appId, appName, versionId = null) {
    const unescapedName = unescape(appName);
    UI.showToast(`Начало загрузки: ${unescapedName}...`, 'info');
    await API.download(appId, versionId, null, unescapedName);
  },

  async openVersionSelector(appId, appName) {
    const unescapedName = unescape(appName);
    const modal = document.getElementById('versionSelectorModal');
    const title = document.getElementById('versionModalTitle');
    const body = document.getElementById('versionModalList');

    title.textContent = `Версии: ${unescapedName}`;
    body.innerHTML = '<div style="text-align: center; padding: 30px; color: var(--text-muted);">Загрузка списка версий...</div>';
    UI.openModal('versionSelectorModal');

    const res = await API.getVersions(appId);
    if (!res.success || !res.versions || res.versions.length === 0) {
      body.innerHTML = '<div style="text-align: center; padding: 30px; color: var(--text-muted);">Версии не найдены или требуется вход в Apple ID</div>';
      return;
    }

    body.innerHTML = '';
    const desc = document.createElement('div');
    desc.style.fontSize = '13px';
    desc.style.color = 'var(--text-secondary)';
    desc.style.marginBottom = '14px';
    desc.textContent = `Найдено ${res.versions.length} версий. Выберите версию для скачивания:`;
    body.appendChild(desc);

    const list = document.createElement('div');
    list.style.display = 'flex';
    list.style.flexDirection = 'column';
    list.style.gap = '8px';

    res.versions.slice(0, 30).forEach((vid, idx) => {
      const item = document.createElement('div');
      item.style.display = 'flex';
      item.style.alignItems = 'center';
      item.style.justifyContent = 'space-between';
      item.style.background = 'var(--bg-primary)';
      item.style.padding = '10px 14px';
      item.style.borderRadius = 'var(--radius-sm)';
      item.style.border = '1px solid var(--border-color)';

      item.innerHTML = `
        <div>
          <span style="font-weight: 600; font-size: 13px;">ID: ${vid}</span>
          <span id="ver_meta_${vid}" style="font-size: 12px; color: var(--accent); margin-left: 10px;"></span>
        </div>
        <button class="btn btn-primary btn-sm" onclick="App.downloadApp('${appId}', '${escape(unescapedName)}', '${vid}'); UI.closeModal('versionSelectorModal');">
          Скачать
        </button>
      `;
      list.appendChild(item);

      // Lazy load metadata
      if (idx < 10) {
        API.getVersionMetadata(appId, vid).then(meta => {
          const span = document.getElementById(`ver_meta_${vid}`);
          if (span && meta && meta.display_version) {
            span.textContent = `v${meta.display_version}`;
          }
        });
      }
    });

    body.appendChild(list);
  },

  async openInstallModal(filename, minIos) {
    const unescapedFile = unescape(filename);
    const select = document.getElementById('installDeviceSelect');
    select.innerHTML = '';

    const devices = await API.getDevices();
    if (!devices || devices.length === 0) {
      UI.showToast('Нет подключенных устройств. Подключите iPhone по USB!', 'error');
      return;
    }

    devices.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d.udid;
      opt.textContent = `${d.name} (${d.ios_version}) - ${d.connection}`;
      select.appendChild(opt);
    });

    document.getElementById('installIpaName').textContent = unescapedFile;
    const confirmBtn = document.getElementById('confirmInstallBtn');
    const newBtn = confirmBtn.cloneNode(true);
    confirmBtn.parentNode.replaceChild(newBtn, confirmBtn);

    newBtn.addEventListener('click', async () => {
      const udid = select.value;
      UI.closeModal('installModal');
      UI.showToast('Отправка команды установки на устройство...', 'info');
      await API.installIpa(udid, unescapedFile);
    });

    UI.openModal('installModal');
  },

  async deleteIpa(filename) {
    const unescapedFile = unescape(filename);
    if (!confirm(`Удалить файл ${unescapedFile}?`)) return;
    await API.deleteIpa(unescapedFile);
    UI.showToast('Файл удален', 'info');
    await this.loadLibrary();
  },

  async inspectDeviceApps(udid) {
    UI.showToast('Получение установленных приложений с устройства...', 'info');
    const res = await API.getDeviceApps(udid);
    if (!res.success) {
      UI.showToast(res.error || 'Ошибка чтения приложений', 'error');
      return;
    }

    const modal = document.getElementById('versionSelectorModal');
    const title = document.getElementById('versionModalTitle');
    const body = document.getElementById('versionModalList');
    title.textContent = `Приложения на устройстве (${res.apps.length})`;
    body.innerHTML = '';

    const list = document.createElement('div');
    list.style.display = 'flex';
    list.style.flexDirection = 'column';
    list.style.gap = '6px';
    list.style.maxHeight = '500px';
    list.style.overflowY = 'auto';

    res.apps.forEach(a => {
      const row = document.createElement('div');
      row.style.padding = '8px 12px';
      row.style.background = 'var(--bg-primary)';
      row.style.borderRadius = 'var(--radius-sm)';
      row.style.fontSize = '13px';
      row.innerHTML = `<strong>${a.title}</strong> <span style="color: var(--text-muted); font-size: 11px;">(${a.bundle_id})</span>`;
      list.appendChild(row);
    });

    body.appendChild(list);
    UI.openModal('versionSelectorModal');
  }
};

window.addEventListener('DOMContentLoaded', () => {
  App.init();
});
