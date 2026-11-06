'use strict';
const $ = id => document.getElementById(id);
let savedSession = null;
try { savedSession = JSON.parse(localStorage.getItem('rosen_sesion') || 'null'); } catch {}
let token = savedSession?.access_token || sessionStorage.getItem('rosen_token') || '';
let refreshToken = savedSession?.refresh_token || '';
let expiresAt = savedSession?.expires_at || 0;
let refreshing = null;
let historyOffset = 0, historyBusy = false;
let data = null, page = 0, reviewed = null, fileVersion = 0;
let role = null;
let activityTimer = null, activityVisit = null, activityIdentity = null, activitySending = false;
let accessOffset = 0, accessBusy = false, selectedPerson = null, personRequest = 0;
function randomId() {
  // getRandomValues funciona también al abrir la web por HTTP en la red local.
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
  const hex = [...bytes].map(b => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}
let deviceId;
try {
  deviceId = localStorage.getItem('rosen_dispositivo');
  if (!/^[0-9a-f-]{36}$/i.test(deviceId || '')) {
    deviceId = randomId(); localStorage.setItem('rosen_dispositivo', deviceId);
  }
} catch { deviceId = randomId(); }
let liveUpdates = null, loadingStock = false, reloadPending = false;
let seller = null;
try {
  const saved = JSON.parse(localStorage.getItem('rosen_vendedor') || 'null');
  if (typeof saved?.nombre === 'string' && saved.nombre.trim()
      && typeof saved?.apellido === 'string' && saved.apellido.trim()) seller = saved;
} catch { /* Un registro inválido vuelve a solicitar el nombre. */ }
const isUpload = location.pathname === '/subir';
const isAdministrative = location.pathname === '/administrativo';
const normalize = value => String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().toLowerCase();

document.querySelectorAll('nav a').forEach(a => {
  if (a.pathname === location.pathname) a.setAttribute('aria-current', 'page');
});
function message(text, error = false) {
  $('notice').textContent = text;
  $('notice').style.color = error ? '#b7151c' : '#236743';
}
function clearPreview() {
  reviewed = null;
  $('preview').hidden = true;
  $('publish').disabled = true;
  $('previewHead').replaceChildren();
  $('previewRows').replaceChildren();
}
function show() {
  const admin = !!token && role === 'administrador';
  const inventoryPage = !isUpload && !isAdministrative;
  document.querySelectorAll('[data-admin-only]').forEach(link => { link.hidden = !admin; });
  $('login').hidden = !!token || inventoryPage;
  $('sellerEntry').hidden = !inventoryPage || !!token || !!seller;
  $('adminLoginLink').hidden = !!token;
  $('sellerGreeting').hidden = !inventoryPage || !!token || !seller;
  $('sellerGreeting').textContent = seller ? `Hola, ${seller.nombre} ${seller.apellido}` : '';
  $('logout').hidden = !token;
  $('upload').hidden = !admin || !isUpload;
  $('inventory').hidden = !inventoryPage || !(token && role || !token && seller);
  $('administrative').hidden = !admin || !isAdministrative;
  syncLiveUpdates();
  syncActivity();
}
function syncActivity() {
  const identity = token && role ? 'usuario' : !token && seller && !isUpload && !isAdministrative ? 'vendedor' : null;
  if (identity === activityIdentity) return;
  endActivity();
  activityIdentity = identity;
  if (!identity) return;
  activityVisit = randomId();
  pulseActivity();
  activityTimer = setInterval(() => {
    if (!document.hidden) pulseActivity();
  }, 30000);
}
function activityPayload(active) {
  return {visita: activityVisit, dispositivo: deviceId,
    nombre: !token ? seller?.nombre || '' : '', apellido: !token ? seller?.apellido || '' : '', activo: active};
}
function endActivity() {
  if (activityTimer) clearInterval(activityTimer);
  activityTimer = null;
  if (activityVisit) {
    fetch('/api/actividad', {method: 'POST', keepalive: true,
      headers: {'Content-Type': 'application/json', ...(token ? {Authorization: 'Bearer ' + token} : {})},
      body: JSON.stringify(activityPayload(false))}).catch(() => {});
  }
  activityVisit = null; activityIdentity = null;
}
async function pulseActivity() {
  if (!activityVisit || activitySending) return;
  activitySending = true;
  try {
    await api('/api/actividad', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(activityPayload(!document.hidden))});
    $('activityNotice').textContent = '';
  } catch {
    $('activityNotice').textContent = 'No se pudo registrar la actividad. Si aún no está configurado, ejecuta registro_accesos.sql en Supabase.';
  } finally { activitySending = false; }
  if (isAdministrative && role === 'administrador' && !document.hidden) loadAccesses();
}
window.addEventListener('pagehide', endActivity);
window.addEventListener('pageshow', () => { if (!activityVisit) syncActivity(); });
document.addEventListener('visibilitychange', () => { if (activityVisit) pulseActivity(); });
function syncLiveUpdates() {
  const viewingStock = !$('inventory').hidden || !$('administrative').hidden;
  if (!viewingStock) {
    if (liveUpdates) liveUpdates.close();
    liveUpdates = null; return;
  }
  if (liveUpdates) return;
  liveUpdates = new EventSource('/api/stock-eventos');
  liveUpdates.addEventListener('stock-updated', () => load(true));
  // Recupera cambios ocurridos mientras el teléfono perdió la conexión.
  liveUpdates.onopen = () => load(true);
}
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && liveUpdates) load(true);
});
$('sellerForm').onsubmit = async event => {
  event.preventDefault();
  const form = new FormData(event.target);
  const entered = {nombre: String(form.get('nombre') || '').trim(), apellido: String(form.get('apellido') || '').trim()};
  if (!entered.nombre || !entered.apellido) { message('Ingresa tu nombre y apellido.', true); return; }
  seller = entered;
  try { localStorage.setItem('rosen_vendedor', JSON.stringify(seller)); }
  catch { message('Este navegador no permite recordar tus datos.'); }
  show(); await load();
};

async function restoreSession() {
  role = null; show();
  try {
    const profile = await api('/api/me');
    role = profile.rol;
    if (role !== 'administrador' && (isUpload || isAdministrative)) {
      location.replace('/inventario'); return;
    }
    show(); message('');
    if (!isUpload) await load();
  } catch (error) {
    if (error.status === 401 || error.status === 403) logout();
    message(error.message, true);
  }
}
function saveSession(result) {
  token = result.access_token; refreshToken = result.refresh_token;
  expiresAt = Date.now() + result.expires_in * 1000;
  localStorage.setItem('rosen_sesion', JSON.stringify({
    access_token: token, refresh_token: refreshToken, expires_at: expiresAt,
  }));
  sessionStorage.removeItem('rosen_token');
}
async function refreshAccess() {
  if (!refreshing) {
    refreshing = (async () => {
      const response = await fetch('/api/refresh', {method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({refresh_token: refreshToken})});
      if (!response.ok) {
        const error = Error(response.status < 500 ? 'La sesión venció. Inicia sesión nuevamente.' : 'No se pudo renovar la sesión. Intenta nuevamente.');
        error.status = response.status;
        if ([400, 401, 403].includes(response.status)) { logout(); error.status = 401; }
        throw error;
      }
      saveSession(await response.json());
    })().finally(() => { refreshing = null; });
  }
  return refreshing;
}
async function api(path, options = {}, retried = false) {
  const authenticated = !!token && path !== '/api/login';
  if (authenticated && refreshToken && expiresAt <= Date.now() + 30000) await refreshAccess();
  let response;
  try {
    response = await fetch(path, {...options, headers: {
      ...(token ? {Authorization: 'Bearer ' + token} : {}), ...options.headers,
    }});
  } catch { throw Error('Sin conexión con el servidor. Intenta nuevamente.'); }
  let body;
  try { body = await response.json(); }
  catch { throw Error('El servidor devolvió una respuesta inesperada.'); }
  if (!response.ok) {
    if (response.status === 401 && authenticated && refreshToken && !retried) {
      await refreshAccess(); return api(path, options, true);
    }
    if (response.status === 401 && authenticated) logout();
    const error = Error(typeof body.detail === 'string' ? body.detail : 'No se pudo completar la operación.');
    error.status = response.status; throw error;
  }
  return body;
}
function logout() {
  endActivity();
  token = ''; role = null; data = null; fileVersion++;
  sessionStorage.removeItem('rosen_token');
  refreshToken = ''; expiresAt = 0;
  localStorage.removeItem('rosen_sesion');
  clearPreview(); $('file').value = '';
  $('rows').replaceChildren(); $('head').replaceChildren(); $('stats').replaceChildren();
  $('historyRows').replaceChildren(); $('historyHead').replaceChildren();
  $('peopleRows').replaceChildren(); $('accessRows').replaceChildren();
  $('accessDialog').close(); selectedPerson = null; personRequest++;
  show();
}
$('logout').onclick = () => {
  logout(); message('Sesión cerrada.');
  if (seller && !isUpload && !isAdministrative) load();
};
$('loginForm').onsubmit = async event => {
  event.preventDefault();
  const button = event.target.querySelector('button');
  button.disabled = true; message('Iniciando sesión…');
  try {
    const result = await api('/api/login', {method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(Object.fromEntries(new FormData(event.target)))});
    saveSession(result);
    event.target.reset(); await restoreSession();
  } catch (error) { message(error.message, true); }
  finally { button.disabled = false; }
};
function table(columns, rows, headId, rowsId) {
  $(headId).replaceChildren(); $(rowsId).replaceChildren();
  const header = document.createElement('tr');
  for (const column of columns) {
    const th = document.createElement('th'); th.scope = 'col';
    th.textContent = column; header.append(th);
  }
  const productLinks = rowsId === 'rows';
  const skuIndex = columns.findIndex(column => normalize(column) === 'sku');
  const nameIndex = columns.findIndex(column => normalize(column) === 'nombre');
  if (productLinks) {
    const th = document.createElement('th'); th.scope = 'col';
    th.textContent = 'Producto en Rosen'; header.append(th);
  }
  $(headId).append(header);
  for (const row of rows) {
    const tr = document.createElement('tr');
    columns.forEach((column, index) => {
      const td = document.createElement('td'); td.dataset.label = column;
      const value = row[index];
      if (rowsId === 'rows' && normalize(column) === 'stock disponible') {
        const amount = quantity(value);
        const state = amount === null ? 'unknown' : amount <= 0 ? 'empty' : amount <= 5 ? 'low' : 'available';
        const badge = document.createElement('span');
        badge.className = 'stock-badge stock-' + state;
        badge.textContent = value ?? '—';
        td.append(badge);
      } else td.textContent = value ?? '';
      tr.append(td);
    });
    if (productLinks) {
      const td = document.createElement('td'); td.dataset.label = 'Producto en Rosen';
      const sku = String(row[skuIndex] ?? '').trim();
      const name = String(row[nameIndex] ?? '').trim();
      const query = sku || name;
      if (query) {
        const link = document.createElement('a');
        const url = new URL('https://www.rosen.cl/catalogsearch/result/');
        url.searchParams.set('q', query);
        link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
        link.className = 'product-link'; link.textContent = 'Buscar en Rosen ↗';
        link.setAttribute('aria-label', `Buscar ${name || sku} en Rosen (abre una nueva pestaña)`);
        td.append(link);
      } else td.textContent = 'Sin SKU o nombre';
      tr.append(td);
    }
    $(rowsId).append(tr);
  }
}
$('file').onchange = () => { fileVersion++; clearPreview(); message(''); };
$('cancelPreview').onclick = () => { fileVersion++; clearPreview(); message('Vista previa cancelada.'); };
$('uploadForm').onsubmit = async event => {
  event.preventDefault(); clearPreview();
  const file = $('file').files[0], version = ++fileVersion;
  if (!file) return;
  if (file.size > 5 * 1024 * 1024) { message('El archivo supera 5 MB.', true); return; }
  const button = event.target.querySelector('button');
  button.disabled = true; message('Validando Excel…');
  try {
    const form = new FormData(); form.append('file', file);
    const result = await api('/api/preview', {method: 'POST', body: form});
    if (version !== fileVersion) return;
    reviewed = {file, sha256: result.sha256};
    table(result.columnas, result.filas, 'previewHead', 'previewRows');
    $('previewSummary').textContent = `${result.nombre} · ${(file.size / 1024).toFixed(1)} KB · ${result.cantidad} filas · ${result.columnas.length} columnas. Mostrando las primeras ${result.filas.length} filas.`;
    $('preview').hidden = false; $('publish').disabled = false;
    message('Archivo válido. Revisa los datos antes de confirmar la publicación.');
  } catch (error) { if (version === fileVersion) message(error.message, true); }
  finally { button.disabled = false; }
};
$('publish').onclick = async () => {
  if (!reviewed) return;
  if (!confirm('¿Reemplazar el inventario compartido por este archivo completo?')) return;
  const selected = reviewed;
  $('publish').disabled = true; $('file').disabled = true;
  $('deleteCurrent').disabled = true;
  $('cancelPreview').disabled = true; $('uploadForm').querySelector('button').disabled = true;
  message('Publicando inventario…');
  try {
    const form = new FormData(); form.append('file', selected.file);
    const result = await api('/api/upload', {method: 'POST', body: form,
      headers: {'X-Preview-SHA256': selected.sha256}});
    clearPreview(); $('uploadForm').reset();
    message(`${result.cantidad} filas publicadas. Ya puedes abrir Ver inventario.`);
  } catch (error) { message(error.message, true); $('publish').disabled = !reviewed; }
  finally {
    $('file').disabled = false; $('cancelPreview').disabled = false;
    $('uploadForm').querySelector('button').disabled = false;
    $('deleteCurrent').disabled = false;
  }
};
$('deleteCurrent').onclick = async () => {
  if (!confirm('¿Eliminar el Excel actual y todos sus datos publicados? Los vendedores dejarán de ver este inventario. Esta acción no se puede deshacer.')) return;
  $('deleteCurrent').disabled = true; $('publish').disabled = true;
  $('uploadForm').querySelector('button').disabled = true;
  $('file').disabled = true; $('cancelPreview').disabled = true;
  message('Eliminando inventario actual…');
  try {
    const result = await api('/api/excel-actual', {
      method: 'DELETE', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({confirmar: true}),
    });
    fileVersion++; clearPreview(); $('uploadForm').reset();
    message(result.mensaje);
  } catch (error) { message(error.message, true); }
  finally {
    $('deleteCurrent').disabled = false; $('publish').disabled = !reviewed;
    $('uploadForm').querySelector('button').disabled = false;
    $('file').disabled = false; $('cancelPreview').disabled = false;
  }
};
function columnIndex(name) {
  return (data?.columnas || []).findIndex(column => normalize(column) === normalize(name));
}
function option(select, value, label) {
  const item = document.createElement('option'); item.value = value;
  item.textContent = label; select.append(item);
}
// No interpreta separadores ambiguos: evita confundir 1.000 unidades con 1 unidad.
function quantity(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value !== 'string' || !/^[+-]?\d+$/.test(value.trim())) return null;
  const number = Number(value.trim()); return Number.isFinite(number) ? number : null;
}
function stat(label, value, tone = '') {
  const card = document.createElement('div'); card.className = 'stat';
  const title = document.createElement('span'); title.textContent = label;
  const count = document.createElement('strong'); count.className = tone;
  count.textContent = value; card.append(title, count); $('stats').append(card);
}
function render() {
  if (isAdministrative) { renderAdministrative(); return; }
  const rows = data?.filas || [];
  const query = normalize($('search').value);
  const filtered = rows.filter(row => row.some(value => normalize(value).includes(query)));
  const pages = Math.max(1, Math.ceil(filtered.length / 50));
  page = Math.max(0, Math.min(page, pages - 1));
  table(data?.columnas || [], filtered.slice(page * 50, page * 50 + 50), 'head', 'rows');
  $('empty').hidden = filtered.length > 0;
  $('pagination').textContent = `Página ${page + 1} de ${pages} · ${filtered.length} resultados`;
  $('prev').disabled = page === 0; $('next').disabled = page >= pages - 1;
}
async function load(background = false) {
  const silent = background === true;
  if (loadingStock) { reloadPending = true; return; }
  loadingStock = true;
  const refresh = isAdministrative ? null : $('refresh');
  if (refresh) refresh.disabled = true;
  if (!silent) message('Cargando inventario…');
  try {
    const updated = await api(isAdministrative ? '/api/administrativo' : token ? '/api/stock' : '/api/stock-vendedores');
    if (isAdministrative) await loadHistory();
    if (silent && updated?.fecha === data?.fecha && data !== null) return;
    data = updated;
    if (!silent) page = 0;
    $(isAdministrative ? 'adminSummary' : 'summary').textContent = data
      ? `${data.nombre} · ${data.filas.length} filas · Actualizado ${new Date(data.fecha).toLocaleString('es-CL')}`
      : 'Todavía no se ha publicado un Excel.';
    render(); message(silent ? 'Inventario actualizado automáticamente.' : '');
  } catch (error) { message(error.message, true); }
  finally {
    if (refresh) refresh.disabled = false; loadingStock = false;
    if (reloadPending) { reloadPending = false; if (liveUpdates) load(true); }
  }
}
function renderAdministrative() {
  $('stats').replaceChildren();
  const rows = data?.filas || [], selected = columnIndex('Stock Disponible');
  stat('Total de registros', rows.length);
  const limit = 5;
  const values = rows.map(row => selected < 0 ? null : quantity(row[selected]));
  stat('Con stock', values.filter(v => v !== null && v > 0).length, 'positive');
  stat('Sin stock', values.filter(v => v !== null && v <= 0).length, 'negative');
  stat('Stock bajo', values.filter(v => v !== null && v > 0 && v <= limit).length, 'low');
  stat('Sin dato válido', values.filter(v => v === null).length);
}
async function loadHistory() {
  if (historyBusy || role !== 'administrador') return;
  historyBusy = true;
  $('historyPrev').disabled = true; $('historyNext').disabled = true;
  $('historyStatus').textContent = 'Consultando historial…';
  try {
    const result = await api(`/api/historial?offset=${historyOffset}`);
    const rows = result.registros.map(item => [
      new Date(item.fecha).toLocaleString('es-CL', {timeZone: 'America/Santiago'}),
      item.email, item.nombre_archivo, item.cantidad_filas,
    ]);
    table(['Fecha y hora (Chile)', 'Actualizado por', 'Archivo', 'Filas'], rows, 'historyHead', 'historyRows');
    $('historyStatus').textContent = rows.length ? '' : 'No hay actualizaciones registradas. El historial comienza al activar su configuración SQL.';
    $('historyPage').textContent = `Página ${historyOffset / 25 + 1}`;
    $('historyPrev').disabled = historyOffset === 0;
    $('historyNext').disabled = !result.hay_mas;
  } catch (error) {
    $('historyRows').replaceChildren();
    $('historyStatus').textContent = 'No se pudo consultar el historial. Si todavía no lo hiciste, ejecuta historial_actualizaciones.sql en Supabase. ' + error.message;
    $('historyPrev').disabled = historyOffset === 0;
  } finally { historyBusy = false; }
}
$('historyPrev').onclick = () => { historyOffset = Math.max(0, historyOffset - 25); loadHistory(); };
$('historyNext').onclick = () => { historyOffset += 25; loadHistory(); };
async function loadAccesses() {
  if (accessBusy || role !== 'administrador') return;
  accessBusy = true; $('activityRefresh').disabled = true;
  try {
    const result = await api('/api/actividad');
    const date = value => new Date(value).toLocaleString('es-CL', {timeZone: 'America/Santiago'});
    table(['Nombre / correo', 'Tipo', 'Estado', 'Última entrada', 'Última actividad'],
      result.personas.map(item => [item.nombre, item.tipo, item.conectado ? 'Conectado' : 'Sin conexión', date(item.entrada), date(item.ultima_actividad)]),
      'peopleHead', 'peopleRows');
    [...$('peopleRows').children].forEach((row, index) => {
      const person = result.personas[index];
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'person-history'; button.textContent = person.nombre;
      button.setAttribute('aria-haspopup', 'dialog');
      button.setAttribute('aria-label', 'Ver historial de entradas de ' + person.nombre);
      button.onclick = () => {
        selectedPerson = {nombre: person.nombre, tipo: person.tipo}; accessOffset = 0;
        $('accessPerson').textContent = person.nombre;
        $('accessRows').replaceChildren(); $('accessPage').textContent = '';
        $('accessDialog').showModal(); loadPersonHistory();
      };
      row.children[0].replaceChildren(button);
    });
    $('activityStatus').textContent = result.personas.length ? 'Mostrando hasta 100 navegadores recientes. Actualización automática cada 30 segundos.' : 'Todavía no hay accesos registrados.';
  } catch (error) {
    $('activityStatus').textContent = 'No se pudieron consultar los accesos. Verifica que hayas ejecutado registro_accesos.sql. ' + error.message;
  } finally { accessBusy = false; $('activityRefresh').disabled = false; }
}
async function loadPersonHistory() {
  if (!selectedPerson || role !== 'administrador') return;
  const revision = ++personRequest;
  $('accessPrev').disabled = true; $('accessNext').disabled = true;
  $('accessStatus').textContent = 'Cargando historial…';
  try {
    const params = new URLSearchParams({...selectedPerson, offset: String(accessOffset)});
    const result = await api('/api/actividad/historial?' + params);
    if (revision !== personRequest || !$('accessDialog').open) return;
    const date = value => new Date(value).toLocaleString('es-CL', {timeZone: 'America/Santiago'});
    table(['Entrada (Chile)', 'Última actividad'],
      result.accesos.map(item => [date(item.entrada), date(item.ultima_actividad)]), 'accessHead', 'accessRows');
    $('accessStatus').textContent = result.accesos.length ? '' : 'No hay entradas registradas.';
    $('accessPage').textContent = `Página ${accessOffset / 25 + 1}`;
    $('accessPrev').disabled = accessOffset === 0;
    $('accessNext').disabled = !result.hay_mas;
  } catch (error) {
    if (revision !== personRequest) return;
    $('accessRows').replaceChildren(); $('accessStatus').textContent = error.message;
    $('accessPrev').disabled = accessOffset === 0;
  }
}
$('closeAccess').onclick = () => $('accessDialog').close();
$('accessDialog').addEventListener('close', () => { selectedPerson = null; personRequest++; });
$('activityRefresh').onclick = loadAccesses;
$('accessPrev').onclick = () => { accessOffset = Math.max(0, accessOffset - 25); loadPersonHistory(); };
$('accessNext').onclick = () => { accessOffset += 25; loadPersonHistory(); };
$('search').oninput = () => { page = 0; render(); };
$('prev').onclick = () => { page--; render(); };
$('next').onclick = () => { page++; render(); };
$('refresh').onclick = load;
show(); if (token) restoreSession();
else if (seller && !isUpload && !isAdministrative) load();
