const API = {
  baseUrl: (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
    ? ''
    : 'http://localhost:5050',

  async request(endpoint, method = 'GET', data = null) {
    const url = endpoint.startsWith('http') ? endpoint : `${this.baseUrl}${endpoint}`;
    const options = {
      method,
      headers: {
        'Content-Type': 'application/json'
      }
    };
    if (data && (method === 'POST' || method === 'DELETE')) {
      options.body = JSON.stringify(data);
    }
    try {
      const resp = await fetch(url, options);
      if (resp.headers.get('content-type')?.includes('application/json')) {
        return await resp.json();
      }
      return { success: resp.ok };
    } catch (err) {
      console.warn(`API Error on ${url}:`, err);
      return { success: false, error: err.message };
    }
  },

  getStatus() {
    return this.request('/api/status');
  },

  login(email, password, auth_code = null, keychain_passphrase = null) {
    return this.request('/api/auth/login', 'POST', { email, password, auth_code, keychain_passphrase });
  },

  logout() {
    return this.request('/api/auth/revoke', 'POST', {});
  },

  getAccounts() {
    return this.request('/api/accounts');
  },

  switchAccount(email) {
    return this.request('/api/accounts/switch', 'POST', { email });
  },

  deleteAccount(email) {
    return this.request('/api/accounts', 'DELETE', { email });
  },

  async getCatalogApps() {
    try {
      const resp = await fetch('apps.json');
      if (resp.ok) {
        return await resp.json();
      }
    } catch (e) {
      console.warn('Error fetching apps.json:', e);
    }
    return [];
  },

  categorize(name) {
    const low = (name || '').toLowerCase();
    if (/банк|сбер|тинькофф|т-банк|альфа|втб|газпром|псб|инвест|страхов|деньги|капитал|cash|credit|fin/.test(low)) return 'finance';
    if (/vpn|wg|amnezia|clash|proxy|shadowrocket|wireguard|adguard/.test(low)) return 'vpn';
    if (/gpt|claude|deepseek|ии|ai|chat|нейро/.test(low)) return 'ai';
    if (/vk|вконтакте|telegram|мессенджер|whatsapp|mail|почта|видео|соц/.test(low)) return 'social';
    if (/2гис|карты|навигатор|такси|авто|транспорт|парков/.test(low)) return 'maps';
    if (/кино|звук|музыка|тв|фильм|сериал|video|music/.test(low)) return 'media';
    if (/госуслуг|налог|мои документы|фнс|паспорт|мос/.test(low)) return 'gov';
    if (/ozon|wildberries|авито|маркет|еда|доставка|лавка|самокат|шоп/.test(low)) return 'shop';
    return 'tools';
  },

  async getStaticPopularApps() {
    try {
      const resp = await fetch('data/AppsList.txt');
      if (resp.ok) {
        const text = await resp.text();
        const lines = text.split('\n');
        const apps = [];
        lines.forEach((line, idx) => {
          line = line.trim();
          if (!line || line.startsWith('#') || !line.includes(':')) return;
          const colonIdx = line.lastIndexOf(':');
          const name = line.substring(0, colonIdx).trim();
          const id = line.substring(colonIdx + 1).trim();
          if (/^\d+$/.test(id)) {
            apps.push({
              index: idx + 1,
              name: name,
              id: id,
              category: this.categorize(name)
            });
          }
        });
        return apps;
      }
    } catch (e) {
      console.warn('Static popular apps load error:', e);
    }
    return [];
  },

  async getPopularApps(category = 'all', q = '', limit = 100, offset = 0) {
    const params = new URLSearchParams({ category, q, limit, offset });
    const res = await this.request(`/api/catalog/popular?${params.toString()}`);
    if (res && res.apps && res.apps.length > 0) {
      return res;
    }
    // Static fallback if server is offline or returned no apps
    const allApps = await this.getStaticPopularApps();
    let filtered = allApps;
    if (category && category !== 'all') {
      filtered = filtered.filter(a => a.category === category);
    }
    if (q) {
      const lowQ = q.toLowerCase();
      filtered = filtered.filter(a => a.name.toLowerCase().includes(lowQ) || a.id.includes(lowQ));
    }
    return {
      success: true,
      total: filtered.length,
      apps: filtered.slice(offset, offset + limit)
    };
  },

  getCustomApps() {
    return this.request('/api/catalog/custom');
  },

  addCustomApp(name, id) {
    return this.request('/api/catalog/custom', 'POST', { name, id });
  },

  deleteCustomApp(id) {
    return this.request('/api/catalog/custom', 'DELETE', { id });
  },

  lookupApp(id) {
    return this.request(`/api/catalog/lookup?id=${id}`);
  },

  getPurchasedApps(allYears = true, sinceYear = null) {
    const params = new URLSearchParams({ all_years: allYears });
    if (sinceYear) params.append('since_year', sinceYear);
    return this.request(`/api/catalog/purchases?${params.toString()}`);
  },

  search(q) {
    return this.request(`/api/search?q=${encodeURIComponent(q)}`);
  },

  purchase(app_id, bundle_id = null, all_accounts = false) {
    return this.request('/api/purchase', 'POST', { app_id, bundle_id, all_accounts });
  },

  getVersions(app_id) {
    return this.request(`/api/versions?app_id=${app_id}`);
  },

  getVersionMetadata(app_id, version_id) {
    return this.request(`/api/version-metadata?app_id=${app_id}&version_id=${version_id}`);
  },

  download(app_id, version_id = null, bundle_id = null, app_name = null) {
    return this.request('/api/download', 'POST', { app_id, version_id, bundle_id, app_name });
  },

  installCatalogApp(bundle_id, udid = null) {
    return this.request('/api/install-catalog-app', 'POST', { bundle_id, udid });
  },

  getLibrary() {
    return this.request('/api/library');
  },

  deleteIpa(filename) {
    return this.request('/api/library', 'DELETE', { filename });
  },

  getDevices() {
    return this.request('/api/devices');
  },

  installIpa(udid, filename) {
    return this.request('/api/devices/install', 'POST', { udid, filename });
  },

  getDeviceApps(udid) {
    return this.request(`/api/devices/apps?udid=${encodeURIComponent(udid)}`);
  },

  getSettings() {
    return this.request('/api/settings');
  },

  updateSettings(settings) {
    return this.request('/api/settings', 'POST', settings);
  },

  initSSE(onMessage) {
    const sseUrl = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
      ? '/api/events'
      : `${this.baseUrl}/api/events`;

    let evtSource;
    try {
      evtSource = new EventSource(sseUrl);
      
      evtSource.addEventListener('task_start', (e) => {
        onMessage('task_start', JSON.parse(e.data));
      });
      evtSource.addEventListener('task_log', (e) => {
        onMessage('task_log', JSON.parse(e.data));
      });
      evtSource.addEventListener('task_complete', (e) => {
        onMessage('task_complete', JSON.parse(e.data));
      });
      evtSource.addEventListener('auth_change', (e) => {
        onMessage('auth_change', JSON.parse(e.data));
      });
      
      evtSource.onerror = (err) => {
        // SSE connection silent retry
      };
    } catch (e) {
      console.warn('SSE not supported or server offline:', e);
    }

    return evtSource;
  }
};
