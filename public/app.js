// ─── STATE ────────────────────────────────────────────────────────────────────

function isMobile() { return window.innerWidth <= 600; }

let map = null;
let markers = {};
let mines = [];
let currentUser = null;
let pendingLatLng = null;
let mapInitialized = false;
let filterState = { name: '', region: '', district: '' };
let userLocationMarker = null;
let userAccuracyCircle = null;

const REGIONS = [
  'Акмолинская область','Актюбинская область','Алматинская область',
  'Атырауская область','Восточно-Казахстанская область','Жамбылская область',
  'Жетысуская область','Западно-Казахстанская область','Карагандинская область',
  'Костанайская область','Кызылординская область','Мангыстауская область',
  'Павлодарская область','Северо-Казахстанская область','Туркестанская область',
  'Улытауская область','Абайская область','г. Алматы','г. Астана','г. Шымкент',
];

// ─── INIT ──────────────────────────────────────────────────────────────────────

window.addEventListener('DOMContentLoaded', () => {
  const token = localStorage.getItem('token');
  const user = localStorage.getItem('user');

  if (token && user) {
    currentUser = JSON.parse(user);
    showView('map');
  } else {
    showView('landing');
  }

  // Populate region dropdowns
  const regionOptions = REGIONS.map(r => `<option value="${r}">${r}</option>`).join('');
  const searchRegionEl = document.getElementById('searchRegion');
  if (searchRegionEl) searchRegionEl.innerHTML += regionOptions;
  const addRegionEl = document.getElementById('addRegion');
  if (addRegionEl) addRegionEl.innerHTML += regionOptions;

  // Enter key support for forms
  document.getElementById('loginPassword').addEventListener('keydown', e => {
    if (e.key === 'Enter') handleLogin();
  });
  document.getElementById('regConfirm').addEventListener('keydown', e => {
    if (e.key === 'Enter') handleRegister();
  });
});

// ─── VIEW ROUTER ───────────────────────────────────────────────────────────────

function showView(view, subview) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));

  const target = document.getElementById(`${view}-view`);
  target.classList.add('active');

  if (view === 'auth' && subview) {
    switchAuthTab(subview);
  }

  if (view === 'map') {
    document.getElementById('navUsername').textContent = currentUser?.username || '';
    if (!mapInitialized) {
      initMap();
    } else {
      setTimeout(() => map.invalidateSize(), 50);
      loadMines();
    }
  }
}

// ─── AUTH ──────────────────────────────────────────────────────────────────────

function switchAuthTab(tab) {
  document.getElementById('loginTab').classList.toggle('active', tab === 'login');
  document.getElementById('registerTab').classList.toggle('active', tab === 'register');
  document.getElementById('loginForm').classList.toggle('active', tab === 'login');
  document.getElementById('registerForm').classList.toggle('active', tab === 'register');
  clearErrors();
}

function clearErrors() {
  ['loginError', 'registerError', 'addMineError'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.remove('show');
  });
}

function showError(id, msg) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = msg;
  el.classList.add('show');
}

async function handleLogin() {
  const username = document.getElementById('loginUsername').value.trim();
  const password = document.getElementById('loginPassword').value;

  if (!username || !password) {
    showError('loginError', 'Заполните все поля');
    return;
  }

  const btn = document.getElementById('loginBtn');
  btn.disabled = true;
  btn.textContent = 'Вход…';

  try {
    const res = await api('POST', '/api/auth/login', { username, password });
    localStorage.setItem('token', res.token);
    localStorage.setItem('user', JSON.stringify(res.user));
    currentUser = res.user;
    showToast('Добро пожаловать, ' + res.user.username + '!', 'success');
    showView('map');
  } catch (err) {
    showError('loginError', err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Войти';
  }
}

async function handleRegister() {
  const username = document.getElementById('regUsername').value.trim();
  const password = document.getElementById('regPassword').value;
  const confirm = document.getElementById('regConfirm').value;

  if (!username || !password || !confirm) {
    showError('registerError', 'Заполните все поля');
    return;
  }
  if (password !== confirm) {
    showError('registerError', 'Пароли не совпадают');
    return;
  }

  const btn = document.getElementById('registerBtn');
  btn.disabled = true;
  btn.textContent = 'Создание…';

  try {
    const res = await api('POST', '/api/auth/register', { username, password });
    localStorage.setItem('token', res.token);
    localStorage.setItem('user', JSON.stringify(res.user));
    currentUser = res.user;
    showToast('Аккаунт создан! Добро пожаловать, ' + res.user.username + '!', 'success');
    showView('map');
  } catch (err) {
    showError('registerError', err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Создать аккаунт';
  }
}

function handleLogout() {
  localStorage.removeItem('token');
  localStorage.removeItem('user');
  currentUser = null;
  showToast('Вы вышли из системы', 'info');
  showView('landing');
}

// ─── MAP ───────────────────────────────────────────────────────────────────────

function initMap() {
  mapInitialized = true;

  map = L.map('map', {
    center: [48.0, 68.0],
    zoom: 5,
    zoomControl: true,
  });

  // Tile providers in fallback order.
  // Local proxy is first: server.py fetches tiles server-side, bypassing browser network restrictions.
  const TILE_PROVIDERS = [
    {
      url: '/api/tiles/{z}/{x}/{y}.png',
      opts: { attribution: '© <a href="https://yandex.ru/maps">Яндекс Карты</a>', maxZoom: 19 }
    },
    {
      url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
      opts: { attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors', maxZoom: 19, subdomains: 'abc' }
    },
    {
      url: 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png',
      opts: { attribution: '© OpenStreetMap contributors © CARTO', maxZoom: 19, subdomains: 'abcd' }
    },
    {
      url: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png',
      opts: { attribution: '© OpenStreetMap contributors © CARTO', maxZoom: 19, subdomains: 'abcd' }
    }
  ];

  let activeTileLayer = null;
  let tileProviderIndex = 0;
  let tileErrorCount = 0;
  let tileLayerSwitched = false;

  function tryTileProvider(index) {
    if (index >= TILE_PROVIDERS.length) {
      showToast('Не удалось загрузить тайлы карты — проверьте интернет-соединение', 'error');
      return;
    }
    if (activeTileLayer) map.removeLayer(activeTileLayer);
    tileErrorCount = 0;
    tileLayerSwitched = false;
    const p = TILE_PROVIDERS[index];
    activeTileLayer = L.tileLayer(p.url, p.opts);
    activeTileLayer.on('tileerror', () => {
      tileErrorCount++;
      if (!tileLayerSwitched && tileErrorCount >= 4) {
        tileLayerSwitched = true;
        tileProviderIndex = index + 1;
        tryTileProvider(tileProviderIndex);
      }
    });
    activeTileLayer.addTo(map);
  }

  tryTileProvider(tileProviderIndex);
  setTimeout(() => map.invalidateSize(), 100);

  // Click on empty map → add mine
  map.on('click', (e) => {
    if (currentUser) {
      pendingLatLng = e.latlng;
      openAddModal(e.latlng);
    } else {
      showToast('Войдите в систему чтобы добавлять объекты', 'info');
    }
  });

  loadMines();
}

// ─── MINES ─────────────────────────────────────────────────────────────────────

async function loadMines() {
  closeMobileSheet();
  document.getElementById('mapLoader').style.display = 'flex';
  document.getElementById('mineCountBadge').style.display = 'none';

  try {
    mines = await api('GET', '/api/mines');
    renderMarkers();
  } catch (err) {
    showToast('Ошибка загрузки данных', 'error');
  } finally {
    document.getElementById('mapLoader').style.display = 'none';
    document.getElementById('mineCountBadge').style.display = 'block';
  }
}

function getFilteredMines() {
  const name = filterState.name.toLowerCase();
  const region = filterState.region.toLowerCase();
  const district = filterState.district.toLowerCase();
  return mines.filter(m => {
    if (name && !m.name.toLowerCase().includes(name)) return false;
    if (region && (m.region || '').toLowerCase() !== region) return false;
    if (district && !(m.district || '').toLowerCase().includes(district)) return false;
    return true;
  });
}

function applyFilters() {
  filterState.name = document.getElementById('searchName').value.trim();
  filterState.region = document.getElementById('searchRegion').value;
  filterState.district = document.getElementById('searchDistrict').value.trim();
  renderMarkers();
  const active = filterState.name || filterState.region || filterState.district;
  const footer = document.getElementById('searchFooter');
  if (footer) footer.style.display = active ? 'flex' : 'none';
}

function toggleSearch() {
  const panel = document.getElementById('searchPanel');
  const btn = document.getElementById('searchToggleBtn');
  const open = panel.classList.toggle('mobile-open');
  btn.textContent = open ? '✕' : '🔍';
  btn.title = open ? 'Закрыть поиск' : 'Поиск';
}

// ─── MOBILE SHEET ──────────────────────────────────────────────────────────────

function openMobileSheet(mine) {
  const body = document.getElementById('mobileSheetBody');
  if (!body) return;
  body.innerHTML = '';
  body.appendChild(createPopupContent(mine));
  document.getElementById('mobileSheet').classList.add('open');
  document.getElementById('mobileSheetBackdrop').classList.add('open');
  document.body.style.overflow = 'hidden';
}

function closeMobileSheet() {
  const sheet = document.getElementById('mobileSheet');
  const backdrop = document.getElementById('mobileSheetBackdrop');
  if (!sheet) return;
  sheet.classList.remove('open');
  backdrop.classList.remove('open');
  document.body.style.overflow = '';
}

// ─── GEOLOCATION ───────────────────────────────────────────────────────────────

function locateUser() {
  if (!navigator.geolocation) {
    showToast('Геолокация не поддерживается браузером', 'error');
    return;
  }

  const btn = document.getElementById('locateBtn');
  if (btn) { btn.classList.add('locating'); btn.disabled = true; }

  navigator.geolocation.getCurrentPosition(
    (pos) => {
      if (btn) { btn.classList.remove('locating'); btn.disabled = false; }
      updateUserLocation(pos.coords.latitude, pos.coords.longitude, pos.coords.accuracy);
    },
    (err) => {
      if (btn) { btn.classList.remove('locating'); btn.disabled = false; }
      const msgs = {
        1: 'Доступ к геолокации запрещён — разрешите в настройках браузера',
        2: 'Не удалось определить местоположение',
        3: 'Превышено время ожидания геолокации',
      };
      showToast(msgs[err.code] || 'Ошибка геолокации', 'error');
    },
    { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 }
  );
}

function updateUserLocation(lat, lng, accuracy) {
  if (!map) return;

  if (userAccuracyCircle) { map.removeLayer(userAccuracyCircle); userAccuracyCircle = null; }
  if (userLocationMarker) { map.removeLayer(userLocationMarker); userLocationMarker = null; }

  userAccuracyCircle = L.circle([lat, lng], {
    radius: accuracy,
    color: '#2196F3',
    fillColor: '#2196F3',
    fillOpacity: 0.08,
    weight: 1,
    opacity: 0.35,
    interactive: false,
  }).addTo(map);

  const icon = L.divIcon({
    className: '',
    html: '<div class="user-location-dot"></div>',
    iconSize: [20, 20],
    iconAnchor: [10, 10],
  });

  userLocationMarker = L.marker([lat, lng], { icon, zIndexOffset: 2000 })
    .addTo(map)
    .bindPopup(
      `<div style="text-align:center;padding:6px 10px;font-size:13px;white-space:nowrap">
        📍 <strong>Вы здесь</strong><br>
        <span style="font-size:11px;color:#8a8f9e">Точность: ±${Math.round(accuracy)} м</span>
      </div>`,
      { closeButton: false }
    );

  map.flyTo([lat, lng], Math.max(map.getZoom(), 13), { duration: 1.2 });
  showToast('Местоположение найдено', 'success');
}

function clearFilters() {
  filterState = { name: '', region: '', district: '' };
  document.getElementById('searchName').value = '';
  document.getElementById('searchRegion').value = '';
  document.getElementById('searchDistrict').value = '';
  renderMarkers();
  const footer = document.getElementById('searchFooter');
  if (footer) footer.style.display = 'none';
}

function previewCoords() {
  const lat = parseFloat(document.getElementById('addLat').value);
  const lng = parseFloat(document.getElementById('addLng').value);
  if (isNaN(lat) || isNaN(lng)) {
    showToast('Введите корректные координаты', 'error');
    return;
  }
  map.flyTo([lat, lng], Math.max(map.getZoom(), 12));
  showToast(`Координаты: ${lat.toFixed(5)}, ${lng.toFixed(5)}`, 'info');
}

function renderMarkers() {
  // Clear existing markers
  Object.values(markers).forEach(m => map.removeLayer(m));
  markers = {};

  const filtered = getFilteredMines();
  const countEl = document.getElementById('mineCount');
  if (countEl) {
    countEl.textContent = filtered.length < mines.length
      ? `${filtered.length} / ${mines.length}`
      : mines.length;
  }
  const countSpan = document.getElementById('searchCount');
  if (countSpan && (filterState.name || filterState.region || filterState.district)) {
    countSpan.textContent = `Найдено: ${filtered.length}`;
  }

  filtered.forEach(mine => {
    const color = statusColor(mine.status);
    const icon = L.divIcon({
      className: '',
      html: `<div class="custom-marker" style="background:${color}">
               <span class="custom-marker-inner">${typeIcon(mine.type)}</span>
             </div>`,
      iconSize: [32, 32],
      iconAnchor: [16, 32],
      popupAnchor: [0, -32]
    });

    const marker = L.marker([mine.lat, mine.lng], { icon }).addTo(map);

    if (isMobile()) {
      marker.on('click', () => openMobileSheet(mine));
    } else {
      marker.bindPopup(() => createPopupContent(mine), {
        maxWidth: 360,
        minWidth: 300,
        className: 'mine-popup',
        autoPan: true,
        autoPanPadding: [20, 80]
      });
    }

    markers[mine.id] = marker;
  });
}

function statusColor(status) {
  switch (status) {
    case 'Активный': return '#4caf79';
    case 'Законсервирован': return '#e8a020';
    case 'Закрыт': return '#e05252';
    default: return '#8a8f9e';
  }
}

function statusBadgeClass(status) {
  switch (status) {
    case 'Активный': return 'badge-active';
    case 'Законсервирован': return 'badge-conserved';
    case 'Закрыт': return 'badge-closed';
    default: return '';
  }
}

function typeIcon(type) {
  switch (type) {
    case 'Родник': return '💧';
    case 'Источник': return '🌊';
    case 'Скважина': return '🔩';
    case 'Колодец': return '🪣';
    default: return '📍';
  }
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

// ─── WATER QUALITY HELPERS ─────────────────────────────────────────────────────

function calcWaterQuality(ph, min, cond, hard) {
  if (ph == null && min == null && cond == null && hard == null) return null;
  let rejected = false, analysis = false;
  if (ph != null) {
    if (ph < 6.0 || ph > 9.5) rejected = true;
    else if (ph < 6.5 || ph > 8.5) analysis = true;
  }
  if (min != null) {
    if (min > 1500) rejected = true;
    else if (min > 1000) analysis = true;
  }
  if (cond != null) {
    if (cond > 2500) rejected = true;
    else if (cond > 1500) analysis = true;
  }
  if (hard != null) {
    if (hard > 10) rejected = true;
    else if (hard > 7) analysis = true;
  }
  if (rejected) return 'Отклонён';
  if (analysis) return 'Анализ';
  return 'Подходит';
}

function renderWQBadge(el, quality) {
  if (!el) return;
  if (!quality) {
    el.className = 'wq-auto-badge';
    el.textContent = '— введите показатели —';
    return;
  }
  el.className = `wq-auto-badge badge ${wqBadgeClass(quality)}`;
  el.textContent = wqBadgeLabel(quality);
}

function calcAddWQ() {
  const ph = document.getElementById('addPh').value;
  const min = document.getElementById('addMineralization').value;
  const cond = document.getElementById('addConductivity').value;
  const hard = document.getElementById('addHardness').value;
  renderWQBadge(
    document.getElementById('addWQBadge'),
    calcWaterQuality(
      ph !== '' ? parseFloat(ph) : null,
      min !== '' ? parseFloat(min) : null,
      cond !== '' ? parseFloat(cond) : null,
      hard !== '' ? parseFloat(hard) : null
    )
  );
}

function calcEditWQ(mineId) {
  const ph = document.getElementById(`edit-ph-${mineId}`)?.value;
  const min = document.getElementById(`edit-min-${mineId}`)?.value;
  const cond = document.getElementById(`edit-cond-${mineId}`)?.value;
  const hard = document.getElementById(`edit-hard-${mineId}`)?.value;
  renderWQBadge(
    document.getElementById(`edit-wq-badge-${mineId}`),
    calcWaterQuality(
      ph != null && ph !== '' ? parseFloat(ph) : null,
      min != null && min !== '' ? parseFloat(min) : null,
      cond != null && cond !== '' ? parseFloat(cond) : null,
      hard != null && hard !== '' ? parseFloat(hard) : null
    )
  );
}

function wqBadgeClass(wq) {
  if (wq === 'Подходит') return 'badge-wq-good';
  if (wq === 'Анализ') return 'badge-wq-analysis';
  if (wq === 'Отклонён') return 'badge-wq-bad';
  return '';
}

function wqBadgeLabel(wq) {
  if (wq === 'Подходит') return 'ПОДХОДИТ';
  if (wq === 'Анализ') return 'АНАЛИЗ';
  if (wq === 'Отклонён') return 'ОТКЛОНЁН';
  return wq || '';
}

function createWQPanel(mine) {
  const hasMetrics = mine.ph != null || mine.mineralization != null || mine.conductivity != null || mine.hardness != null;
  const hasExtras = mine.temperature_c != null || mine.sediment;
  if (!hasMetrics && !hasExtras) return '';

  let phClass = 'ph-neutral';
  if (mine.ph != null) {
    phClass = (mine.ph >= 7.0 && mine.ph <= 7.8) ? 'ph-good' : (mine.ph < 6.5 || mine.ph > 9.0) ? 'ph-bad' : 'ph-neutral';
  }

  return `
    <div class="wq-panel">
      ${hasMetrics ? `<div class="wq-metrics">
        ${mine.ph != null ? `<div class="wq-metric">
          <div class="wq-metric-label">Водородный индекс</div>
          <div class="wq-metric-value ${phClass}">pH ${mine.ph}</div>
        </div>` : ''}
        ${mine.mineralization != null ? `<div class="wq-metric">
          <div class="wq-metric-label">Минерализация</div>
          <div class="wq-metric-value">${mine.mineralization} мг/л</div>
        </div>` : ''}
        ${mine.conductivity != null ? `<div class="wq-metric">
          <div class="wq-metric-label">Проводимость</div>
          <div class="wq-metric-value">${mine.conductivity} мкСм/см</div>
        </div>` : ''}
        ${mine.hardness != null ? `<div class="wq-metric">
          <div class="wq-metric-label">Общая жёсткость</div>
          <div class="wq-metric-value">${mine.hardness} мг-экв/л</div>
        </div>` : ''}
      </div>` : ''}
      ${hasExtras ? `<div class="wq-extras${hasMetrics ? ' wq-extras-border' : ''}">
        ${mine.temperature_c != null ? `<div class="wq-extra"><span class="wq-extra-label">🌡 Температура воды:</span><span>${mine.temperature_c} °C</span></div>` : ''}
        ${mine.sediment ? `<div class="wq-extra"><span class="wq-extra-label">🔬 Осадок / примеси:</span><span>${escHtml(mine.sediment)}</span></div>` : ''}
      </div>` : ''}
    </div>`;
}

// ─── POPUP CONTENT ─────────────────────────────────────────────────────────────

function createPopupContent(mine) {
  const isOwner = currentUser && currentUser.id === mine.user_id;
  const depthStr = mine.depth_m ? `${mine.depth_m} м` : 'Н/Д';
  const yearStr = mine.year_opened || 'Н/Д';

  const div = document.createElement('div');
  div.innerHTML = `
    <div class="popup-card" id="popup-view-${mine.id}">
      <div class="popup-name">${escHtml(mine.name)}</div>
      <div class="popup-badges">
        <span class="badge badge-type">${escHtml(mine.type)}</span>
        <span class="badge ${statusBadgeClass(mine.status)}">${escHtml(mine.status)}</span>
        ${mine.water_quality ? `<span class="badge ${wqBadgeClass(mine.water_quality)}">${wqBadgeLabel(mine.water_quality)}</span>` : ''}
      </div>
      <div class="popup-fields">
        <div class="popup-field">
          <div class="popup-field-label">Глубина</div>
          <div class="popup-field-value">${depthStr}</div>
        </div>
        <div class="popup-field">
          <div class="popup-field-label">Год открытия</div>
          <div class="popup-field-value">${yearStr}</div>
        </div>
        ${mine.region ? `<div class="popup-field">
          <div class="popup-field-label">Регион</div>
          <div class="popup-field-value" style="font-size:12px">${escHtml(mine.region)}</div>
        </div>` : ''}
        ${mine.district ? `<div class="popup-field">
          <div class="popup-field-label">Район</div>
          <div class="popup-field-value" style="font-size:12px">${escHtml(mine.district)}</div>
        </div>` : ''}
      </div>
      ${mine.description ? `<p class="popup-desc">${escHtml(mine.description)}</p>` : ''}
      ${createWQPanel(mine)}

      <hr class="popup-divider" />
      <div class="popup-section-label">📷 Фото и видео</div>
      <div class="media-gallery" id="mediaGallery-${mine.id}">
        <div class="no-notes">Загрузка…</div>
      </div>
      ${currentUser ? `
        <div class="media-upload-row">
          <label class="btn btn-ghost btn-sm media-upload-btn" for="mediaInput-${mine.id}">+ Добавить фото / видео</label>
          <input type="file" id="mediaInput-${mine.id}" accept="image/*,video/mp4,video/webm,video/mov,video/avi" multiple style="display:none" onchange="handleMediaUpload(${mine.id}, this)" />
        </div>
      ` : ''}

      <hr class="popup-divider" />
      <div class="popup-notes-label">💬 Заметки <span style="color:var(--text3);font-weight:400">(${mine.note_count || 0})</span></div>
      <div class="notes-list" id="notesList-${mine.id}">
        <div class="no-notes">Загрузка заметок…</div>
      </div>

      ${currentUser ? `
        <div class="note-add">
          <textarea id="noteInput-${mine.id}" placeholder="Добавить заметку…"></textarea>
          <button class="btn btn-outline btn-sm" onclick="handleAddNote(${mine.id})">Добавить заметку</button>
        </div>
      ` : `<p class="auth-required-note">Войдите чтобы добавлять заметки</p>`}

      ${isOwner ? `
        <div class="popup-actions">
          <button class="btn btn-outline btn-sm" onclick="openEditForm(${mine.id})">✏️ Редактировать</button>
          <button class="btn btn-danger btn-sm" onclick="handleDeleteMine(${mine.id})">🗑 Удалить</button>
        </div>
      ` : ''}
    </div>

    <!-- EDIT FORM (hidden by default) -->
    <div class="edit-form" id="edit-form-${mine.id}">
      <div style="font-weight:600;margin-bottom:4px">✏️ Редактирование: ${escHtml(mine.name)}</div>
      <div class="form-group">
        <label>Название</label>
        <input type="text" id="edit-name-${mine.id}" value="${escAttr(mine.name)}" />
      </div>
      <div class="edit-form form-row" style="display:grid;gap:10px">
        <div class="form-group">
          <label>Тип</label>
          <select id="edit-type-${mine.id}">
            ${['Родник','Источник','Колодец'].map(t =>
              `<option value="${t}" ${mine.type===t?'selected':''}>${t}</option>`
            ).join('')}
          </select>
        </div>
        <div class="form-group">
          <label>Статус</label>
          <select id="edit-status-${mine.id}">
            ${['Активный','Законсервирован','Закрыт'].map(s =>
              `<option value="${s}" ${mine.status===s?'selected':''}>${s}</option>`
            ).join('')}
          </select>
        </div>
      </div>
      <div class="edit-form form-row" style="display:grid;gap:10px">
        <div class="form-group">
          <label>Глубина (м)</label>
          <input type="number" id="edit-depth-${mine.id}" value="${mine.depth_m||0}" />
        </div>
        <div class="form-group">
          <label>Год открытия</label>
          <input type="number" id="edit-year-${mine.id}" value="${mine.year_opened||''}" />
        </div>
      </div>
      <div class="form-group">
        <label>Описание</label>
        <textarea id="edit-desc-${mine.id}" rows="3">${escHtml(mine.description||'')}</textarea>
      </div>
      <div style="font-size:11px;color:var(--text3);text-transform:uppercase;letter-spacing:0.07em;padding:4px 0;border-bottom:1px solid var(--border);margin-bottom:4px">💧 Качество воды</div>
      <div class="edit-form form-row" style="display:grid;gap:10px">
        <div class="form-group">
          <label>pH</label>
          <input type="number" id="edit-ph-${mine.id}" value="${mine.ph != null ? mine.ph : ''}" step="0.1" min="0" max="14" placeholder="напр. 7.5" oninput="calcEditWQ(${mine.id})" />
        </div>
        <div class="form-group">
          <label>Минерализация (мг/л)</label>
          <input type="number" id="edit-min-${mine.id}" value="${mine.mineralization != null ? mine.mineralization : ''}" min="0" placeholder="напр. 200" oninput="calcEditWQ(${mine.id})" />
        </div>
      </div>
      <div class="edit-form form-row" style="display:grid;gap:10px">
        <div class="form-group">
          <label>Проводимость (мкСм/см)</label>
          <input type="number" id="edit-cond-${mine.id}" value="${mine.conductivity != null ? mine.conductivity : ''}" min="0" placeholder="напр. 320" oninput="calcEditWQ(${mine.id})" />
        </div>
        <div class="form-group">
          <label>Жёсткость (мг-экв/л)</label>
          <input type="number" id="edit-hard-${mine.id}" value="${mine.hardness != null ? mine.hardness : ''}" step="0.1" min="0" placeholder="напр. 3.5" oninput="calcEditWQ(${mine.id})" />
        </div>
      </div>
      <div class="edit-form form-row" style="display:grid;gap:10px">
        <div class="form-group">
          <label>Температура (°C)</label>
          <input type="number" id="edit-temp-${mine.id}" value="${mine.temperature_c != null ? mine.temperature_c : ''}" step="0.5" placeholder="напр. 8" />
        </div>
        <div class="form-group">
          <label>Качество воды</label>
          <div id="edit-wq-badge-${mine.id}" class="wq-auto-badge ${mine.water_quality ? 'badge ' + wqBadgeClass(mine.water_quality) : ''}">${mine.water_quality ? wqBadgeLabel(mine.water_quality) : '— введите показатели —'}</div>
        </div>
      </div>
      <div class="form-group">
        <label>Осадок / примеси</label>
        <input type="text" id="edit-sediment-${mine.id}" value="${escAttr(mine.sediment||'')}" placeholder="напр. Нет" />
      </div>
      <div class="edit-form form-row" style="display:grid;gap:10px">
        <div class="form-group">
          <label>Регион</label>
          <select id="edit-region-${mine.id}">
            <option value="">— Выберите —</option>
            ${REGIONS.map(r => `<option value="${r}" ${mine.region===r?'selected':''}>${r}</option>`).join('')}
          </select>
        </div>
        <div class="form-group">
          <label>Район</label>
          <input type="text" id="edit-district-${mine.id}" value="${escAttr(mine.district||'')}" placeholder="напр. Алматинский" />
        </div>
      </div>
      <div style="display:flex;gap:8px;margin-top:4px">
        <button class="btn btn-primary btn-sm" onclick="handleEditMine(${mine.id})">Сохранить</button>
        <button class="btn btn-ghost btn-sm" onclick="closeEditForm(${mine.id})">Отмена</button>
      </div>
    </div>
  `;

  loadNotes(mine.id);
  loadMedia(mine.id);

  return div;
}

function openEditForm(mineId) {
  document.getElementById(`popup-view-${mineId}`).style.display = 'none';
  document.getElementById(`edit-form-${mineId}`).classList.add('show');
}

function closeEditForm(mineId) {
  document.getElementById(`popup-view-${mineId}`).style.display = 'block';
  document.getElementById(`edit-form-${mineId}`).classList.remove('show');
}

async function handleEditMine(mineId) {
  const phVal = document.getElementById(`edit-ph-${mineId}`).value;
  const minVal = document.getElementById(`edit-min-${mineId}`).value;
  const condVal = document.getElementById(`edit-cond-${mineId}`).value;
  const hardVal = document.getElementById(`edit-hard-${mineId}`).value;
  const tempVal = document.getElementById(`edit-temp-${mineId}`).value;
  const data = {
    name: document.getElementById(`edit-name-${mineId}`).value.trim(),
    type: document.getElementById(`edit-type-${mineId}`).value,
    status: document.getElementById(`edit-status-${mineId}`).value,
    depth_m: parseInt(document.getElementById(`edit-depth-${mineId}`).value) || 0,
    year_opened: parseInt(document.getElementById(`edit-year-${mineId}`).value) || null,
    description: document.getElementById(`edit-desc-${mineId}`).value.trim(),
    ph: phVal !== '' ? parseFloat(phVal) : null,
    mineralization: minVal !== '' ? parseFloat(minVal) : null,
    conductivity: condVal !== '' ? parseFloat(condVal) : null,
    hardness: hardVal !== '' ? parseFloat(hardVal) : null,
    temperature_c: tempVal !== '' ? parseFloat(tempVal) : null,
    sediment: document.getElementById(`edit-sediment-${mineId}`).value.trim() || null,
    region: document.getElementById(`edit-region-${mineId}`)?.value.trim() || null,
    district: document.getElementById(`edit-district-${mineId}`)?.value.trim() || null,
  };

  if (!data.name) { showToast('Введите название', 'error'); return; }

  try {
    await api('PUT', `/api/mines/${mineId}`, data);
    showToast('Объект обновлён', 'success');
    map.closePopup();
    await loadMines();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function handleDeleteMine(mineId) {
  const mine = mines.find(m => m.id === mineId);
  if (!confirm(`Удалить объект "${mine?.name}"? Это действие необратимо.`)) return;

  try {
    await api('DELETE', `/api/mines/${mineId}`);
    showToast('Объект удалён', 'success');
    map.closePopup();
    await loadMines();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// ─── NOTES ─────────────────────────────────────────────────────────────────────

async function loadNotes(mineId) {
  const container = document.getElementById(`notesList-${mineId}`);
  if (!container) return;

  try {
    const notes = await api('GET', `/api/mines/${mineId}/notes`);
    if (notes.length === 0) {
      container.innerHTML = '<div class="no-notes">Заметок пока нет</div>';
    } else {
      container.innerHTML = notes.map(note => `
        <div class="note-item">
          <div class="note-header">
            <span class="note-author">@${escHtml(note.username)}</span>
            <span class="note-date">${formatDate(note.created_at)}</span>
          </div>
          <div class="note-content">${escHtml(note.content)}</div>
        </div>
      `).join('');
      container.scrollTop = container.scrollHeight;
    }
  } catch (err) {
    container.innerHTML = '<div class="no-notes">Ошибка загрузки заметок</div>';
  }
}

async function handleAddNote(mineId) {
  const textarea = document.getElementById(`noteInput-${mineId}`);
  if (!textarea) return;
  const content = textarea.value.trim();
  if (!content) { showToast('Введите текст заметки', 'error'); return; }

  try {
    await api('POST', `/api/mines/${mineId}/notes`, { content });
    textarea.value = '';
    showToast('Заметка добавлена', 'success');
    await loadNotes(mineId);
    // Update count in mines array
    const mine = mines.find(m => m.id === mineId);
    if (mine) mine.note_count = (mine.note_count || 0) + 1;
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// ─── MEDIA ─────────────────────────────────────────────────────────────────────

async function loadMedia(mineId) {
  const gallery = document.getElementById(`mediaGallery-${mineId}`);
  if (!gallery) return;

  try {
    const items = await api('GET', `/api/mines/${mineId}/media`);
    if (items.length === 0) {
      gallery.innerHTML = '<div class="no-notes">Фото и видео пока нет</div>';
      return;
    }

    gallery.innerHTML = items.map(item => {
      const canDelete = currentUser && (currentUser.id === item.user_id || currentUser.id === item.mine_owner_id);
      const deleteBtn = currentUser
        ? `<button class="media-delete-btn" title="Удалить" onclick="handleDeleteMedia(${mineId}, ${item.id})">✕</button>`
        : '';

      if (item.media_type === 'photo') {
        return `<div class="media-item">
          <img src="/uploads/${escAttr(item.filename)}" alt="${escAttr(item.original_name || 'фото')}"
               onclick="openLightbox('/uploads/${escAttr(item.filename)}')" loading="lazy" />
          ${deleteBtn}
          <div class="media-item-author">@${escHtml(item.username)}</div>
        </div>`;
      } else {
        return `<div class="media-item media-item-video">
          <video src="/uploads/${escAttr(item.filename)}" controls preload="metadata"></video>
          ${deleteBtn}
          <div class="media-item-author">@${escHtml(item.username)}</div>
        </div>`;
      }
    }).join('');
  } catch (err) {
    gallery.innerHTML = '<div class="no-notes">Ошибка загрузки медиа</div>';
  }
}

async function handleMediaUpload(mineId, inputEl) {
  const files = Array.from(inputEl.files);
  if (!files.length) return;

  const token = localStorage.getItem('token');
  let uploaded = 0;

  const label = document.querySelector(`label[for="mediaInput-${mineId}"]`);
  if (label) { label.textContent = 'Загрузка…'; label.style.pointerEvents = 'none'; }

  for (const file of files) {
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch(`/api/mines/${mineId}/media`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Ошибка загрузки');
      uploaded++;
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  if (label) { label.textContent = '+ Добавить фото / видео'; label.style.pointerEvents = ''; }
  inputEl.value = '';

  if (uploaded > 0) {
    showToast(`Загружено: ${uploaded} файл(ов)`, 'success');
    await loadMedia(mineId);
  }
}

async function handleDeleteMedia(mineId, mediaId) {
  if (!confirm('Удалить этот файл?')) return;
  try {
    await api('DELETE', `/api/mines/${mineId}/media/${mediaId}`);
    showToast('Файл удалён', 'success');
    await loadMedia(mineId);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function openLightbox(src) {
  let lb = document.getElementById('lightbox');
  if (!lb) {
    lb = document.createElement('div');
    lb.id = 'lightbox';
    lb.className = 'lightbox';
    lb.innerHTML = '<img id="lightboxImg" /><button class="lightbox-close" onclick="closeLightbox()">✕</button>';
    lb.addEventListener('click', e => { if (e.target === lb) closeLightbox(); });
    document.body.appendChild(lb);
  }
  document.getElementById('lightboxImg').src = src;
  lb.classList.add('open');
  document.body.style.overflow = 'hidden';
}

function closeLightbox() {
  const lb = document.getElementById('lightbox');
  if (lb) lb.classList.remove('open');
  document.body.style.overflow = '';
}

// ─── ADD MINE MODAL ────────────────────────────────────────────────────────────

function openAddModal(latlng) {
  document.getElementById('addLat').value = latlng ? latlng.lat.toFixed(5) : '';
  document.getElementById('addLng').value = latlng ? latlng.lng.toFixed(5) : '';
  document.getElementById('addName').value = '';
  document.getElementById('addType').value = '';
  document.getElementById('addStatus').value = '';
  document.getElementById('addDepth').value = '';
  document.getElementById('addYear').value = '';
  document.getElementById('addDesc').value = '';
  document.getElementById('addRegion').value = '';
  document.getElementById('addDistrict').value = '';
  document.getElementById('addPh').value = '';
  document.getElementById('addMineralization').value = '';
  document.getElementById('addConductivity').value = '';
  document.getElementById('addHardness').value = '';
  document.getElementById('addTemperature').value = '';
  document.getElementById('addSediment').value = '';
  renderWQBadge(document.getElementById('addWQBadge'), null);
  document.getElementById('addMineError').classList.remove('show');
  document.getElementById('addMineModal').classList.add('open');
  setTimeout(() => document.getElementById('addName').focus(), 100);
}

function closeAddModal() {
  document.getElementById('addMineModal').classList.remove('open');
  pendingLatLng = null;
}

document.getElementById('addMineModal').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeAddModal();
});

async function handleAddMine() {
  const name = document.getElementById('addName').value.trim();
  const type = document.getElementById('addType').value;
  const status = document.getElementById('addStatus').value;
  const depth = parseInt(document.getElementById('addDepth').value) || 0;
  const year = parseInt(document.getElementById('addYear').value) || null;
  const desc = document.getElementById('addDesc').value.trim();
  const lat = parseFloat(document.getElementById('addLat').value);
  const lng = parseFloat(document.getElementById('addLng').value);
  const region = document.getElementById('addRegion').value.trim() || null;
  const district = document.getElementById('addDistrict').value.trim() || null;
  const phRaw = document.getElementById('addPh').value;
  const minRaw = document.getElementById('addMineralization').value;
  const condRaw = document.getElementById('addConductivity').value;
  const hardRaw = document.getElementById('addHardness').value;
  const tempRaw = document.getElementById('addTemperature').value;
  const ph = phRaw !== '' ? parseFloat(phRaw) : null;
  const mineralization = minRaw !== '' ? parseFloat(minRaw) : null;
  const conductivity = condRaw !== '' ? parseFloat(condRaw) : null;
  const hardness = hardRaw !== '' ? parseFloat(hardRaw) : null;
  const temperature_c = tempRaw !== '' ? parseFloat(tempRaw) : null;
  const water_quality = calcWaterQuality(ph, mineralization, conductivity, hardness);
  const sediment = document.getElementById('addSediment').value.trim() || null;

  if (!name) { showError('addMineError', 'Введите название'); return; }
  if (!type) { showError('addMineError', 'Выберите тип'); return; }
  if (!status) { showError('addMineError', 'Выберите статус'); return; }
  if (isNaN(lat) || isNaN(lng)) { showError('addMineError', 'Введите корректные координаты (широта и долгота)'); return; }
  if (lat < -90 || lat > 90) { showError('addMineError', 'Широта должна быть от −90 до 90'); return; }
  if (lng < -180 || lng > 180) { showError('addMineError', 'Долгота должна быть от −180 до 180'); return; }

  const btn = document.getElementById('addMineBtn');
  btn.disabled = true;
  btn.textContent = 'Сохранение…';

  try {
    const mine = await api('POST', '/api/mines', {
      name, type, status,
      depth_m: depth,
      year_opened: year,
      description: desc,
      lat, lng,
      region, district,
      ph, mineralization, conductivity, hardness, temperature_c, water_quality, sediment
    });
    closeAddModal();
    showToast(`Объект "${mine.name}" добавлен`, 'success');
    await loadMines();
    // Open the popup for the new mine
    setTimeout(() => {
      const marker = markers[mine.id];
      if (marker) marker.openPopup();
    }, 200);
  } catch (err) {
    showError('addMineError', err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Сохранить объект';
  }
}

// ─── API HELPER ────────────────────────────────────────────────────────────────

async function api(method, url, body) {
  const token = localStorage.getItem('token');
  const opts = {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    }
  };
  if (body) opts.body = JSON.stringify(body);

  const res = await fetch(url, opts);
  const data = await res.json();

  if (!res.ok) {
    if (res.status === 401 || res.status === 403) {
      // Token expired
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      currentUser = null;
      showView('auth');
      throw new Error('Сессия истекла. Войдите снова.');
    }
    throw new Error(data.error || 'Ошибка сервера');
  }

  return data;
}

// ─── TOAST ─────────────────────────────────────────────────────────────────────

function showToast(msg, type = 'info') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;

  const icons = { success: '✅', error: '❌', info: 'ℹ️' };
  toast.innerHTML = `<span>${icons[type] || ''}</span><span>${escHtml(msg)}</span>`;

  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('out');
    toast.addEventListener('animationend', () => toast.remove());
  }, 3000);
}

// ─── UTILS ─────────────────────────────────────────────────────────────────────

function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function escAttr(str) {
  if (!str) return '';
  return String(str).replace(/"/g, '&quot;');
}
