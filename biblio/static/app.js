'use strict';
const $ = id => document.getElementById(id);
const API_VERSION = '6';
let csrf = '', currentUser = null, libraryData = null, accountList = [], editAccount = null;
let page = 1, query = '', records = [], searchAccount = null, searchGeneration = 0, noticeTimer;
let sessionGeneration = 0, settingsBusy = false, libraryLoadId = 0, loadingSeq = 0;
const labels = {renovable:'Puedes renovarlo',renovable_desde:'Renovación disponible más adelante',limite_alcanzado:'Límite de renovaciones alcanzado',no_renovable:'No renovable',prestado_con_retraso:'Préstamo con retraso',lector_caducado:'Carné caducado',lector_suspendido:'Carné suspendido',desconocido:'Consulta con tu biblioteca'};
const statuses = {pending:'Pendiente de aprobación',approved:'Acceso autorizado',rejected:'Solicitud rechazada',revoked:'Acceso retirado o solicitud cancelada'};
const permissionLabel = value => value === 'manage' ? 'Gestión completa' : 'Solo lectura';
const date = value => value ? new Date(value + (value.length === 10 ? 'T12:00:00' : '')).toLocaleDateString('es-ES', {day:'2-digit',month:'2-digit',year:'numeric'}) : '—';
function node(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}
function notify(text, error=false, persistent=false) {
  clearTimeout(noticeTimer);
  $('notice').textContent = text;
  $('notice').className = error ? 'error' : '';
  $('notice').hidden = false;
  if (!persistent) noticeTimer = setTimeout(() => $('notice').hidden = true, 9000);
}
async function api(path, body) {
  const generation = sessionGeneration;
  const response = await fetch('/api/' + path, {
    credentials:'same-origin', cache:'no-store',
    headers:body ? {'Content-Type':'application/json','X-CSRF-Token':csrf} : {},
    method:body ? 'POST' : 'GET', body:body ? JSON.stringify(body) : undefined
  });
  if (response.headers.get('X-Biblio-API-Version') !== API_VERSION) {
    const error=new Error('El servidor está ejecutando una versión anterior o incompatible de BiblioCM. Reinícialo con python -m biblio.web y recarga esta página.');
    error.code='API_VERSION';
    throw error;
  }
  const data = await response.json();
  if (generation !== sessionGeneration) throw new Error('La sesión ha cambiado.');
  if (!response.ok) {
    if (response.status === 401 && !['login','register','auth/passkeys/login'].includes(path)) showSession(false);
    const failure = new Error(data.error || 'No se pudo completar la operación');
    // `code` es el único campo estable del error: hoy solo `reauth_required`.
    if (data.code) failure.code = data.code;
    throw failure;
  }
  return data;
}
async function busy(button, callback) {
  button.disabled = true;
  // Bloqueo accesible mientras la petición sigue en vuelo: `aria-busy` en el
  // botón y, si la acción declara progreso, su texto y un aviso en la región
  // viva. No hay timeout ni reintento: si la respuesta no llega, el error del
  // fetch se notifica y la mutación no se vuelve a enviar.
  button.setAttribute('aria-busy','true');
  const resting = button.textContent;
  const pending = button.dataset.pendingText;
  if (pending) { button.textContent = pending; notify(pending); }
  try { await callback(); }
  catch (e) { notify(e.message || 'No hay conexión. Inténtalo de nuevo.', true, e.code==='API_VERSION'); }
  finally {
    button.disabled = false;
    button.removeAttribute('aria-busy');
    if (pending) button.textContent = resting;
    if (button.id === 'previous' || button.id === 'next') updatePagination();
  }
}
function showSession(active) {
  // Toda resolución de la sesión (éxito o error) termina el estado de arranque.
  $('boot-loading').hidden = true;
  $('welcome').hidden = active;
  $('dashboard').hidden = !active;
  $('logout').hidden = !active;
  if (!active) {
    sessionGeneration++;
    // Una carga en vuelo pertenece a la sesión que se cierra: se invalida y se
    // retira el estado de carga aquí, porque su `finally` ya no debe tocar la UI.
    libraryLoadId++;
    loadingSeq++;
    setLibraryLoading(false);
    // Las portadas de la sesión cerrada se invalidan y revocan: ninguna blob
    // URL de esa sesión vuelve a servir tras el logout.
    revokeCovers();
    csrf = ''; currentUser = null; libraryData = null; accountList = []; records = [];
    clearSearch(); resetAccountForm();
    ['loan-list','reservation-list','stats','detail-content','linked-accounts','incoming-requests','outgoing-requests','account-errors'].forEach(id => $(id).replaceChildren());
    $('account-filter').replaceChildren(node('option','Todas las cuentas'));
    $('catalog-account').replaceChildren();
    $('greeting').textContent = 'Mi biblioteca';
    $('my-identity').textContent = ''; $('reader-info').textContent = ''; $('request-count').textContent = '';
    $('detail').close(); $('reauth').close();
    $('link-account').reset(); $('request-access').reset(); $('login').reset(); $('register').reset();
    $('email-form').reset(); $('password-form').reset(); $('recovery').reset();
    $('email-verify-row').hidden=true; $('recovery-reset').hidden=true; $('recovery-request').hidden=false;
    $('register').hidden=true; $('recovery').hidden=true; $('login').hidden=false;
    setView('loans');
  }
}
function setView(view) {
  document.querySelectorAll('[data-view]').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  ['loans','reservations','catalog','settings'].forEach(id => $(id).hidden = id !== view);
  $('account-filter-row').hidden = !['loans','reservations'].includes(view);
}
function empty(container,text) { container.append(node('p',text,'empty')); }
// Solo rutas de portada de esta aplicación. Cualquier otra cosa (URL del OPAC,
// dominio externo, javascript:) se ignora y se conserva el marcador.
const COVER_URL = /^\/api\/cover\?account=[A-Za-z0-9_%.~-]{1,300}&record=\d{1,20}$/;
// Caché de portada temporal en RAM (ADR-014): blob URL por ruta, con tope de
// entradas y revocación explícita. Nada se persiste (ni CacheStorage, ni
// localStorage, ni IndexedDB) y el service worker sigue sin interceptar la ruta.
const coverCache = new Map();
const coverPending = new Map();
const COVER_CACHE_MAX = 60;
// Cada invalidación descarta también las descargas en vuelo de antes: una
// portada de un panel o de una autorización anteriores no debe aparecer después.
let coverGeneration = 0;
function coverAccount(path) {
  const match = /^\/api\/cover\?account=([^&]*)&record=\d{1,20}$/.exec(path);
  return match ? decodeURIComponent(match[1]) : null;
}
function revokeCovers(match) {
  coverGeneration++;
  for (const path of [...coverCache.keys()]) {
    if (!match || match(path)) {
      URL.revokeObjectURL(coverCache.get(path));
      coverCache.delete(path);
    }
  }
}
function coverFetch(path) {
  const generation = coverGeneration;
  return fetch(path, {credentials:'same-origin', cache:'no-store'}).then(response => {
    if (!response.ok) throw new Error('cover');
    return response.blob();
  }).then(blob => {
    const blobUrl = URL.createObjectURL(blob);
    if (generation !== coverGeneration) { URL.revokeObjectURL(blobUrl); throw new Error('cover'); }
    if (coverCache.size >= COVER_CACHE_MAX) {
      const oldest = coverCache.keys().next().value;
      URL.revokeObjectURL(coverCache.get(oldest));
      coverCache.delete(oldest);
    }
    coverCache.set(path, blobUrl);
    return blobUrl;
  });
}
function coverImage(url,className) {
  if (typeof url !== 'string' || !COVER_URL.test(url)) return null;
  const img = node('img');
  img.alt = ''; img.loading = 'lazy'; img.decoding = 'async';
  if (className) img.className = className;
  img.addEventListener('error', () => img.remove());
  const cached = coverCache.get(url);
  if (cached) { img.src = cached; return img; }
  let pending = coverPending.get(url);
  if (!pending) {
    pending = coverFetch(url).finally(() => coverPending.delete(url));
    coverPending.set(url, pending);
  }
  // La tarjeta se añade al documento en la misma tanda, de modo que cuando la
  // respuesta llega el nodo ya está colocado; si falla, se retira y queda la inicial.
  pending.then(src => { if (img.isConnected) img.src = src; })
         .catch(() => { if (img.isConnected && !img.getAttribute('src')) img.remove(); });
  return img;
}
function book(title,author,cover) {
  const card = node('article',undefined,'book');
  const art = node('div',undefined,'book-cover');
  art.append(node('span',(title || 'B').charAt(0).toUpperCase(),'book-cover-letter'));
  const img = coverImage(cover);
  if (img) art.append(img);
  card.append(art);
  const body = node('div',undefined,'book-body');
  body.append(node('h3',title || 'Sin título'));
  if (author) body.append(node('p',author));
  card.append(body);
  return {card,body};
}
function action(body,text,callback,pending) {
  const button = node('button',text); button.type = 'button';
  if (pending) button.dataset.pendingText = pending;
  button.addEventListener('click',() => busy(button,callback));
  body.append(button); return button;
}
function accountName(account) { return account.label + (account.own ? '' : ' · @' + account.username); }
function syncAccounts(accounts) {
  const fingerprint = list => JSON.stringify(list.map(a => [a.id,a.permission,a.label]));
  const changed = fingerprint(accountList) !== fingerprint(accounts);
  const previous = accountList;
  accountList = accounts;
  for (const [id,all] of [['account-filter',true],['catalog-account',false]]) {
    const old = $(id).value; $(id).replaceChildren();
    if (all) { const option=node('option','Todas las cuentas'); option.value=''; $(id).append(option); }
    for (const account of accounts) {
      const option=node('option',accountName(account)+' · '+permissionLabel(account.permission));
      option.value=account.id; $(id).append(option);
    }
    if (accounts.some(a => a.id === old)) $(id).value=old;
  }
  if (changed) {
    // Invalidar las portadas cuya cuenta desapareció o vio cambiar su permiso:
    // la caché no sirve imágenes de una autorización que ya no está.
    const current = new Map(accounts.map(a => [a.id, a.permission]));
    const before = new Map(previous.map(a => [a.id, a.permission]));
    revokeCovers(path => {
      const id = coverAccount(path);
      return id !== null && (!current.has(id) || current.get(id) !== before.get(id));
    });
    clearSearch(); $('detail').close();
    if (libraryData) {
      for (const group of ['loans','reservations']) {
        libraryData[group]=libraryData[group].filter(item => accounts.some(a => a.id===item.account.id));
        for (const item of libraryData[group]) item.account=accounts.find(a => a.id===item.account.id);
      }
      renderLibrary();
    }
  }
  $('search').querySelector('button').disabled = !accounts.length;
  if (editAccount && !accounts.some(a => a.id === editAccount && a.own)) resetAccountForm();
  return changed;
}
// Estado de carga del panel: región viva + aria-busy con spinner y texto.
// Cada fase que puede mantenerlo encendido recibe un token (`beginLoading`):
// solo la fase más reciente puede apagarlo, así que una respuesta vieja no
// reanuncia la carga ni deja el panel «cargando» sobre otro ya resuelto, y un
// cierre de sesión incrementa el contador y lo apaga de inmediato.
function setLibraryLoading(active) {
  $('library-loading').hidden = !active;
  $('dashboard').setAttribute('aria-busy', active ? 'true' : 'false');
}
function beginLoading() {
  const token = ++loadingSeq;
  setLibraryLoading(true);
  return token;
}
function endLoading(token) {
  if (token !== loadingSeq) return;
  setLibraryLoading(false);
}
// Refresco completo (permisos + panel) con el estado encendido desde la primera
// petición: `settings` precede a `library` en login, restauración y «Actualizar»
// y mientras tanto el panel no tiene datos que mostrar.
async function reloadPanel() {
  const generation = sessionGeneration;
  const token = beginLoading();
  try {
    await loadSettings();
    if (generation !== sessionGeneration) return;
    await loadLibrary();
  } finally {
    endLoading(token);
  }
}
async function loadLibrary() {
  const generation = sessionGeneration;
  const load = ++libraryLoadId;
  const token = beginLoading();
  try {
    const data = await api('library');
    if (generation !== sessionGeneration || load !== libraryLoadId) return data;
    libraryData = data; currentUser = data.user; showSession(true);
    $('greeting').textContent = 'Hola, ' + currentUser.name;
    $('reader-info').textContent = data.accounts.length + ' cuentas en tu espacio de lectura · @' + currentUser.username;
    syncAccounts(data.accounts);
    $('account-errors').replaceChildren();
    for (const account of data.accounts) {
      const problem = account.error || (account.reader && (account.reader.expired ? 'Carné caducado.' : account.reader.suspended ? 'Carné suspendido.' : ''));
      if (!problem) continue;
      const row=node('p',accountName(account)+': '+problem,'account-error');
      action(row,account.own ? 'Revisar en Configuración' : 'Ver autorización',async () => { setView('settings'); await loadSettings(); });
      $('account-errors').append(row);
    }
    renderLibrary();
    if (!data.accounts.length) setView('settings');
    return data;
  } catch (e) {
    // Respuesta de una sesión que ya no existe (logout en vuelo): la UI ya se
    // reinició, así que se descarta sin gritar ni tocar el panel nuevo.
    if (generation !== sessionGeneration) return libraryData;
    throw e;
  } finally {
    if (load === libraryLoadId && generation === sessionGeneration) endLoading(token);
  }
}
function renderLibrary() {
  if (!libraryData) return;
  const selected=$('account-filter').value;
  const loans=libraryData.loans.filter(l => !selected || l.account.id === selected).sort((a,b) => a.days_left-b.days_left);
  const reservations=libraryData.reservations.filter(r => !selected || r.account.id === selected);
  $('stats').replaceChildren();
  for (const [label,value,note] of [['Préstamos activos',loans.length,'En las cuentas seleccionadas'],['Vencen en 3 días',loans.filter(l => l.days_left<=3).length,'Incluye préstamos con retraso'],['Reservas',reservations.length,'Tus próximas lecturas']]) {
    const el=node('div',undefined,'stat');
    el.append(node('span',label),node('strong',String(value)),node('span',note)); $('stats').append(el);
  }
  $('loan-list').replaceChildren();
  if (!loans.length) empty($('loan-list'),'No hay préstamos activos en las cuentas consultadas.');
  for (const loan of loans) {
    const {card,body}=book(loan.clean_title || loan.title,loan.author,loan.cover_url);
    body.append(node('p',accountName(loan.account),'account-label'),node('p',loan.library),
      node('span',loan.days_left<0 ? `${Math.abs(loan.days_left)} días de retraso` : loan.days_left===0 ? 'Vence hoy' : `${loan.days_left} días restantes`,'badge '+(loan.days_left<0 ? 'danger' : loan.days_left<=3 ? 'warning' : '')),
      node('p','Devolver antes del '+date(loan.due_date)),node('p',labels[loan.renewal_state] || loan.renewal_state));
    if (loan.renewal_available_from) body.append(node('p','Desde el '+date(loan.renewal_available_from)));
    if (loan.account.permission === 'read') body.append(node('span','Autorización de solo lectura','permission'));
    else if (loan.renewal_state === 'renovable') action(body,'Renovar préstamo →',async () => {
      const result=await api('renew',{account:loan.account.id,barcode:loan.barcode});
      const updated=await loadLibrary();
      const confirmed=updated && updated.loans.find(item => item.barcode===loan.barcode && item.account.id===loan.account.id);
      if (confirmed) {
        const remaining=confirmed.days_left===0 ? 'vence hoy' : confirmed.days_left===1 ? '1 día restante' : `${confirmed.days_left} días restantes`;
        notify(`«${confirmed.clean_title || confirmed.title}» renovado. Devolución: ${date(confirmed.due_date)} · ${remaining}.`);
      } else notify(result.message);
    },'Renovando…');
    $('loan-list').append(card);
  }
  $('reservation-list').replaceChildren();
  if (!reservations.length) empty($('reservation-list'),'No hay reservas pendientes en las cuentas consultadas.');
  for (const reservation of reservations) {
    const {card,body}=book(reservation.title,undefined,reservation.cover_url);
    body.append(node('p',accountName(reservation.account),'account-label'),node('span',reservation.state,'badge'),node('p',reservation.branch));
    if (reservation.expires) body.append(node('p','Hasta el '+date(reservation.expires)));
    if (reservation.account.permission === 'read') body.append(node('span','Autorización de solo lectura','permission'));
    else action(body,'Anular reserva',async () => {
      if (!confirm('¿Anular la reserva de «'+reservation.title+'» de '+accountName(reservation.account)+'?')) return;
      const result=await api('cancel',{account:reservation.account.id,reservation:reservation.reservation_id}); notify(result.message); await loadLibrary();
    });
    $('reservation-list').append(card);
  }
}
function clearSearch() {
  searchGeneration++; page=1; records=[]; searchAccount=null;
  $('results').replaceChildren(); $('pagination').hidden=true;
  $('search-info').textContent='Busca entre los títulos de la red de bibliotecas.';
}
function updatePagination() {
  $('previous').disabled=page===1; $('next').disabled=!records.length;
  $('page-label').textContent='Página '+page;
}
async function search() {
  const account=accountList.find(a => a.id === $('catalog-account').value);
  if (!account) throw new Error('Vincula un carné o recibe una autorización antes de consultar el catálogo.');
  const generation=++searchGeneration;
  $('search-info').textContent='Buscando con '+accountName(account)+'…';
  try {
    const data=await api('search?account='+encodeURIComponent(account.id)+'&q='+encodeURIComponent(query)+'&page='+page);
    if (generation!==searchGeneration) return;
    searchAccount=account; records=data.records; $('results').replaceChildren();
    $('search-info').textContent=data.total+' resultados para «'+query+'» · '+accountName(account);
    if (!records.length) empty($('results'),'No hay resultados en esta página. Prueba otro título, autor o ISBN.');
    for (const record of records) {
      const {card,body}=book(record.title,record.author,record.cover_url);
      body.append(node('p',[record.publication,record.year].filter(Boolean).join(' · ')));
      if (record.extent) body.append(node('p',record.extent));
      if (record.summary) body.append(node('p',record.summary));
      if (record.isbn) body.append(node('p','ISBN '+record.isbn));
      action(body,account.permission==='manage' ? 'Ver ejemplares y reservar →' : 'Ver ejemplares →',() => detail(record,account));
      $('results').append(card);
    }
    $('pagination').hidden=page===1 && !records.length; updatePagination();
  } catch(e) { if (generation===searchGeneration) $('search-info').textContent='La búsqueda no se ha completado.'; throw e; }
}
async function detail(record,account) {
  $('detail-title').textContent=record.title;
  $('detail-content').replaceChildren(node('p','Consultando con '+accountName(account)+'…')); $('detail').showModal();
  const generation=searchGeneration;
  try {
    const data=await api('copies?account='+encodeURIComponent(account.id)+'&record='+encodeURIComponent(record.record_id));
    if (generation!==searchGeneration || !$('detail').open) return;
      $('detail-content').replaceChildren(node('p','Cuenta: '+accountName(account),'account-label'));
      const cover = coverImage(record.cover_url,'detail-cover');
      if (cover) $('detail-content').append(cover);
      if (record.extent) $('detail-content').append(node('p','Edición / soporte: '+record.extent,'muted'));
    const libraries=new Set(data.copies.map(copy => copy.branch || copy.library).filter(Boolean));
    const availableCount=data.copies.filter(copy => copy.available_now).length;
    $('detail-content').append(node('p',`${data.copies.length} ${data.copies.length===1 ? 'ejemplar' : 'ejemplares'} en ${libraries.size} ${libraries.size===1 ? 'biblioteca' : 'bibliotecas'} · ${availableCount} ${availableCount===1 ? 'disponible' : 'disponibles'} ahora`,'detail-summary'));
    const allCopies=node('section'); allCopies.append(node('h3','Todos los ejemplares de esta ficha'));
    $('detail-content').append(allCopies);
    if (!data.copies.length) empty(allCopies,'No se encontraron ejemplares para este título.');
    for (const copy of data.copies) {
      const row=node('article',undefined,'copy');
      row.append(node('strong',copy.branch || copy.library),node('p',[copy.location,copy.signature].filter(Boolean).join(' · ')),node('p',[copy.copy_type,copy.support].filter(Boolean).join(' · ')),node('span',copy.availability,'badge '+(copy.available_now ? '' : 'warning')));
      allCopies.append(row);
    }
    if (account.permission==='read') { $('detail-content').append(node('p','Solo lectura: el titular no ha autorizado la creación de reservas.','permission')); return; }
    $('detail-content').append(node('p','El portal distingue entre ejemplares disponibles para recoger y ejemplares que admiten reserva. Las opciones dependen de esta ficha, del estado del ejemplar y de tu cuenta.','muted'));
    const reservableSection=node('section'); reservableSection.id='reservable-options'; reservableSection.hidden=true;
    action($('detail-content'),'Consultar ejemplares reservables',async () => {
      const result=await api('reservable?account='+encodeURIComponent(account.id)+'&record='+encodeURIComponent(record.record_id));
      if (generation!==searchGeneration || !$('detail').open) return;
      if (!Array.isArray(result.copies) || result.copies.some(copy =>
        !(typeof copy.library==='string' && copy.library.trim()) && !(typeof copy.branch==='string' && copy.branch.trim()))) {
        throw new Error('La respuesta de reservables no contiene los datos de biblioteca. Actualiza el servidor y vuelve a consultar.');
      }
      const list=node('div'); list.append(node('h3','Ejemplares reservables'),node('p','Reservar para '+accountName(account),'account-label'));
      const reservableLibraries=new Set(result.copies.map(copy => copy.branch || copy.library).filter(Boolean));
      list.append(node('p',`${result.copies.length} ${result.copies.length===1 ? 'opción' : 'opciones'} de reserva${reservableLibraries.size ? ' en '+reservableLibraries.size+' '+(reservableLibraries.size===1 ? 'biblioteca' : 'bibliotecas') : ''}. Solo se muestran las que ofrece el portal para esta cuenta.`,'muted'));
      if (!result.copies.length) empty(list,'El portal no ofrece ejemplares reservables para esta cuenta en este momento. Consulta arriba los ejemplares disponibles para recoger.');
      for (const copy of result.copies) {
        const row=node('article',undefined,'copy');
        row.append(node('strong',copy.branch || copy.library));
        if (copy.library && copy.branch && copy.library!==copy.branch) row.append(node('p',copy.library));
        row.append(node('p',[copy.location,copy.signature].filter(Boolean).join(' · ')));
        if (copy.copy_type) row.append(node('p',copy.copy_type));
        if (copy.availability) row.append(node('span',copy.availability,'badge warning'));
        action(row,'Reservar este ejemplar',async () => {
          if (!confirm('¿Reservar este ejemplar de «'+record.title+'» para '+accountName(account)+'?')) return;
          const result=await api('reserve',{account:account.id,record:record.record_id,index:copy.index,barcode:copy.barcode});
          notify(result.message); $('detail').close(); await loadLibrary();
        }); list.append(row);
      }
      reservableSection.replaceChildren(list); reservableSection.hidden=false;
    });
    $('detail-content').append(reservableSection);
  } catch(e) { if ($('detail').open) $('detail-content').replaceChildren(node('p',e.message)); throw e; }
}
function resetAccountForm() {
  editAccount=null; $('link-account').reset(); $('link-account-title').textContent='Vincular un carné';
  $('account-card-row').hidden=false; $('account-card').required=true; $('cancel-account-edit').hidden=true;
}
function permissionSelect(value) {
  const select=node('select'); select.setAttribute('aria-label','Permiso de acceso');
  for (const level of ['read','manage']) { const option=node('option',permissionLabel(level)); option.value=level; select.append(option); }
  select.value=value; return select;
}
async function decide(link,actionName,level) {
  const result=await api('links/decide',{id:link.id,action:actionName,permission:level}); notify(result.message);
  await loadSettings(); await loadLibrary();
}
async function loadSettings() {
  const generation = sessionGeneration;
  let data;
  try {
    data = await api('settings');
  } catch (e) {
    // Respuesta de una sesión que ya no existe: la UI ya se reinició, se
    // descarta sin gritar en el aviso ni repoblar el panel.
    if (generation !== sessionGeneration) return false;
    throw e;
  }
  if (generation !== sessionGeneration) return false;
  const changed=syncAccounts(data.accounts);
  currentUser=data.user;
  $('my-identity').textContent=currentUser.name+' · @'+currentUser.username+' · Comparte este usuario para recibir solicitudes.';
  // Estado del email (FR-AUTH-002): verificado, pendiente o sin añadir.
  $('email-state').textContent = currentUser.email_verified
    ? 'Email verificado: '+currentUser.email+'. Puedes entrar también con él.'
    : currentUser.email
      ? 'Pendiente de verificar: '+currentUser.email+'. Entra el código que recibiste por correo.'
      : 'Añade un email verificado para entrar también con él y para poder recuperar tu contraseña.';
  if (currentUser.email) $('email-input').value=currentUser.email;
  $('email-verify-row').hidden=!(currentUser.email && !currentUser.email_verified);
  // Passkeys y Google (FR-AUTH-004/FR-AUTH-005) en Configuración.
  renderPasskeys(data.passkeys || []);
  const linked = (data.identities || []).some(item => item.provider === 'google');
  $('google-link').hidden = linked || !googleEnabled;
  $('google-unlink').hidden = !linked || !googleEnabled;
  $('google-state').textContent = !googleEnabled
    ? 'El acceso con Google no está configurado en este servidor.'
    : linked
      ? 'Tu cuenta de Google está vinculada: puedes usarla para entrar.'
      : 'Vincula tu cuenta de Google para poder entrar con ella. Nunca se usa para encontrar ni crear cuentas.';
  const pending=data.incoming.filter(l => l.status==='pending').length;
  $('request-count').textContent=pending ? String(pending) : '';
  $('linked-accounts').replaceChildren();
  if (!data.accounts.length) empty($('linked-accounts'),'Vincula tu primer carné o solicita acceso a otro usuario para empezar.');
  for (const account of data.accounts) {
    const card=node('article',undefined,'settings-card');
    card.append(node('h4',accountName(account)),node('p',account.own ? 'Vinculada por ti · '+account.masked_card : 'Autorizada por '+account.name+' · @'+account.username),node('span',permissionLabel(account.permission),'badge'));
    if (account.own) {
      action(card,'Actualizar clave / nombre',async () => {
        editAccount=account.id; $('link-account-title').textContent='Actualizar '+account.label;
        $('account-label').value=account.label; $('account-password').value='';
        $('account-card-row').hidden=true; $('account-card').required=false; $('cancel-account-edit').hidden=false;
        $('account-label').focus();
      });
      action(card,'Desvincular carné',async () => {
        if (!confirm('¿Eliminar el carné «'+account.label+'» y sus credenciales guardadas? También dejará de estar disponible para quienes hayas autorizado.')) return;
        const result=await api('accounts/delete',{account:account.id}); notify(result.message); await loadSettings(); await loadLibrary();
      });
    } else card.append(node('p','Las credenciales solo las puede modificar quien vinculó este carné.'));
    $('linked-accounts').append(card);
  }
  for (const [id,links,incoming] of [['incoming-requests',data.incoming,true],['outgoing-requests',data.outgoing,false]]) {
    $(id).replaceChildren();
    if (!links.length) empty($(id),incoming ? 'No has recibido solicitudes de acceso.' : 'Todavía no has solicitado acceso a otra persona.');
    for (const link of links) {
      const card=node('article',undefined,'settings-card');
      card.append(node('h4','@'+(incoming ? link.requester_username : link.owner_username)),
        node('p',incoming ? link.requester_name : link.owner_name),node('span',statuses[link.status],'badge'),node('p',permissionLabel(link.permission)));
      if (incoming && ['pending','approved'].includes(link.status)) {
        const selector=permissionSelect(link.permission); card.append(selector);
        action(card,link.status==='pending' ? 'Aprobar con este permiso' : 'Guardar permiso',() => decide(link,link.status==='pending' ? 'approve' : 'permission',selector.value));
        if (link.status==='pending') action(card,'Rechazar',() => decide(link,'reject'));
      }
      if (link.status==='approved' || (!incoming && link.status==='pending')) action(card,link.status==='pending' ? 'Cancelar solicitud' : incoming ? 'Revocar acceso' : 'Dejar de acceder',async () => {
        if (!confirm('¿Retirar esta autorización o solicitud?')) return;
        await decide(link,'revoke');
      });
      $(id).append(card);
    }
  }
  return changed;
}
async function enter(data) {
  csrf=data.csrf; currentUser=data.user; showSession(true); resetAccountForm();
  try {
    await reloadPanel();
  } catch (e) {
    // Sin panel resuelto no se deja un dashboard vacío: se vuelve al acceso.
    if (!libraryData) showSession(false);
    throw e;
  }
}
$('login').addEventListener('submit',event => {
  event.preventDefault(); busy($('login').querySelector('[type=submit]'),async () => {
    const data=await api('login',{username:$('username').value,password:$('password').value});
    $('password').value=''; await enter(data);
  });
});
$('register').addEventListener('submit',event => {
  event.preventDefault(); busy($('register').querySelector('[type=submit]'),async () => {
    const data=await api('register',{username:$('register-username').value,name:$('register-name').value,password:$('register-password').value});
    $('register-password').value=''; await enter(data);
  });
});
$('show-register').addEventListener('click',() => { $('login').hidden=true; $('recovery').hidden=true; $('register').hidden=false; $('password').value=''; $('register-name').focus(); });
$('show-login').addEventListener('click',() => { $('register').hidden=true; $('recovery').hidden=true; $('login').hidden=false; $('register-password').value=''; $('username').focus(); });
// Recuperación de contraseña (FR-AUTH-003): dos pasos, códigos de un solo uso.
$('show-recovery').addEventListener('click',() => { $('login').hidden=true; $('register').hidden=true; $('recovery').hidden=false; $('recovery-reset').hidden=true; $('recovery-request').hidden=false; $('recovery').reset(); $('recovery-email').focus(); });
$('recovery-back').addEventListener('click',() => { $('recovery').hidden=true; $('login').hidden=false; $('recovery').reset(); $('recovery-reset').hidden=true; $('recovery-request').hidden=false; $('username').focus(); });
$('recovery-send').addEventListener('click',() => busy($('recovery-send'),async () => {
  const result=await api('auth/password/recovery/request',{email:$('recovery-email').value});
  notify(result.message || 'Si ese email está verificado, recibirás un código.');
  $('recovery-request').hidden=true; $('recovery-reset').hidden=false; $('recovery-token').focus();
}));
$('recovery-confirm').addEventListener('click',() => busy($('recovery-confirm'),async () => {
  const result=await api('auth/password/recovery/reset',{token:$('recovery-token').value.trim(),password:$('recovery-password').value});
  notify(result.message || 'Contraseña actualizada.');
  $('recovery').reset(); $('recovery-reset').hidden=true; $('recovery-request').hidden=false;
  $('recovery').hidden=true; $('login').hidden=false; $('username').focus();
}));
$('logout').addEventListener('click',() => busy($('logout'),async () => { await api('logout',{}); showSession(false); }));
$('refresh').addEventListener('click',() => busy($('refresh'),reloadPanel));
document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click',() => {
  setView(button.dataset.view);
  if (button.dataset.view==='settings') busy(button,async () => { if (await loadSettings()) await loadLibrary(); });
}));
$('link-account').addEventListener('submit',event => {
  event.preventDefault(); busy($('link-account').querySelector('[type=submit]'),async () => {
    const body={label:$('account-label').value,password:$('account-password').value};
    if (editAccount) body.account=editAccount; else body.card=$('account-card').value;
    const result=await api(editAccount ? 'accounts/update' : 'accounts/add',body);
    notify(result.message); resetAccountForm(); await loadSettings(); await loadLibrary();
  });
});
$('cancel-account-edit').addEventListener('click',resetAccountForm);
$('email-form').addEventListener('submit',event => {
  event.preventDefault(); busy($('email-form').querySelector('[type=submit]'),async () => {
    const email=$('email-input').value.trim();
    const result=await api('auth/email/request',{email:email});
    notify(result.message || 'Si el email es válido y no está en uso, recibirás un código.');
    // El servidor no cambia el usuario hasta consumir el código: el estado
    // pendiente se pinta aquí y `loadSettings` lo confirma tras verificar.
    $('email-state').textContent='Pendiente de verificar: '+email+'. Entra el código que recibiste por correo.';
    $('email-verify-row').hidden=false; $('email-token').focus();
  });
});
$('email-verify').addEventListener('click',() => busy($('email-verify'),async () => {
  const result=await api('auth/email/verify',{token:$('email-token').value.trim()});
  notify('Email verificado. Ya puedes entrar con él.');
  $('email-token').value='';
  await loadSettings();
}));
$('password-form').addEventListener('submit',event => {
  event.preventDefault(); busy($('password-form').querySelector('[type=submit]'),async () => {
    const result=await api('auth/password/change',{current_password:$('current-password').value,password:$('new-password').value});
    notify(result.message || 'Contraseña actualizada.');
    $('password-form').reset();
  });
});
// Passkeys (FR-AUTH-004): credenciales descubribles con UV, añadidas y borradas
// solo con reautenticación explícita (contraseña o passkey vigente).
let googleEnabled = false;
function b64url(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
// El navegador exige BufferSource en `challenge`, `user.id` e `id`, mientras
// que el API entrega y acepta base64url: la traducción es solo codificación.
function fromB64url(value) {
  const binary = atob(value.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((value.length + 3) % 4));
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index++) bytes[index] = binary.charCodeAt(index);
  return bytes.buffer;
}
function creationOptions(publicKey) {
  return Object.assign({}, publicKey, {challenge: fromB64url(publicKey.challenge),
    user: Object.assign({}, publicKey.user, {id: fromB64url(publicKey.user.id)}),
    excludeCredentials: (publicKey.excludeCredentials || []).map(item =>
      Object.assign({}, item, {id: fromB64url(item.id)}))});
}
function authenticationOptions(publicKey) {
  return Object.assign({}, publicKey, {challenge: fromB64url(publicKey.challenge),
    allowCredentials: (publicKey.allowCredentials || []).map(item =>
      Object.assign({}, item, {id: fromB64url(item.id)}))});
}
function creationCredential(credential) {
  return {id: credential.id, rawId: b64url(credential.rawId), type: credential.type,
    response: {clientDataJSON: b64url(credential.response.clientDataJSON),
      attestationObject: b64url(credential.response.attestationObject),
      transports: credential.response.getTransports ? credential.response.getTransports() : []}};
}
function assertionCredential(credential) {
  return {id: credential.id, rawId: b64url(credential.rawId), type: credential.type,
    response: {clientDataJSON: b64url(credential.response.clientDataJSON),
      authenticatorData: b64url(credential.response.authenticatorData),
      signature: b64url(credential.response.signature),
      userHandle: credential.response.userHandle ? b64url(credential.response.userHandle) : null}};
}
// Solo contexto seguro: sobre HTTP no local el navegador no expone WebAuthn y
// el servidor además rechaza la operación (NFR-SVC-003). Además Chromium exige
// un `rpId` con forma de dominio: con una IP literal (`http://127.0.0.1`) la
// passkey no puede crearse, así que en ese caso se explica y se ocultan los
// controles; `http://localhost:8000` sí vale.
const webauthnAvailable = () => window.isSecureContext && 'PublicKeyCredential' in window;
const ipLiteralHost = () => /^(\d{1,3}\.){3}\d{1,3}$/.test(window.location.hostname)
  || window.location.hostname.includes(':');
const passkeysUsable = () => webauthnAvailable() && !ipLiteralHost();
function askReauth() {
  return new Promise((resolve, reject) => {
    $('reauth-error').textContent = '';
    $('reauth-password').value = '';
    $('reauth').showModal();
    $('reauth-password').focus();
    let finished = false;
    const finish = action => {
      if (finished) return;
      finished = true;
      $('reauth-form').removeEventListener('submit', submit);
      $('reauth-close').removeEventListener('click', cancelled);
      $('reauth').removeEventListener('close', cancelled);
      $('reauth').close();
      action === 'confirm' ? resolve() : reject(new Error('Cancelado: la acción no se ha completado.'));
    };
    const cancelled = () => finish('cancel');
    const submit = event => {
      event.preventDefault();
      api('auth/reauth', {password: $('reauth-password').value})
        .then(() => { $('reauth-password').value = ''; finish('confirm'); })
        .catch(error => { $('reauth-error').textContent = error.message; });
    };
    $('reauth-form').addEventListener('submit', submit);
    $('reauth-close').addEventListener('click', cancelled);
    $('reauth').addEventListener('close', cancelled);
  });
}
async function withReauth(work) {
  try { return await work(); }
  catch (error) {
    if (error.code !== 'reauth_required') throw error;
    await askReauth();
    return work();
  }
}
function renderPasskeys(list) {
  $('passkey-list').replaceChildren();
  if (!list.length) $('passkey-list').append(node('li', 'Todavía no has añadido ninguna passkey.', 'muted'));
  for (const passkey of list) {
    const item = node('li', undefined, 'passkey-item');
    item.append(node('span', passkey.label + ' · ' + date(passkey.created_at)));
    action(item, 'Borrar passkey', () => withReauth(async () => {
      const result = await api('auth/passkeys/delete', {id: passkey.id});
      notify(result.message); await loadSettings();
    }));
    $('passkey-list').append(item);
  }
}
$('passkey-add').addEventListener('click',() => busy($('passkey-add'), () => withReauth(async () => {
  if (!passkeysUsable()) throw new Error('Las passkeys necesitan http://localhost, un dominio o HTTPS.');
  const options = await api('auth/passkeys/register/options', {});
  const credential = await navigator.credentials.create({publicKey: creationOptions(options.publicKey)});
  if (!credential) throw new Error('El dispositivo no ha creado ninguna passkey.');
  const result = await api('auth/passkeys/register',
    {credential: creationCredential(credential), label: $('passkey-label').value.trim() || 'Passkey'});
  notify(result.message); $('passkey-label').value = ''; await loadSettings();
})));
$('passkey-login').addEventListener('click',() => busy($('passkey-login'),async () => {
  if (!passkeysUsable()) throw new Error('Las passkeys necesitan un origen local o HTTPS.');
  const options = await api('auth/passkeys/login/options', {});
  const credential = await navigator.credentials.get({publicKey: authenticationOptions(options.publicKey)});
  if (!credential) throw new Error('No se ha podido usar la passkey.');
  await enter(await api('auth/passkeys/login', {credential: assertionCredential(credential)}));
}));
// Acceso con Google (FR-AUTH-005): opt-in del servidor, identidad por `sub` y
// vinculación explícita con reautenticación; nunca merge por email.
function googleStart(mode) {
  return api('auth/google/start', {mode}).then(data => window.location.assign(data.authorize_url));
}
$('google-login').addEventListener('click',() => busy($('google-login'),() => googleStart('login')));
$('google-signup').addEventListener('click',() => busy($('google-signup'),() => googleStart('signup')));
$('google-link').addEventListener('click',() => busy($('google-link'),() => withReauth(() => googleStart('link'))));
$('google-unlink').addEventListener('click',() => busy($('google-unlink'),() => withReauth(async () => {
  const result = await api('auth/google/unlink', {});
  notify(result.message); await loadSettings();
})));
$('request-access').addEventListener('submit',event => {
  event.preventDefault(); busy($('request-access').querySelector('[type=submit]'),async () => {
    const result=await api('links/request',{username:$('request-username').value,permission:$('request-permission').value});
    notify(result.message); $('request-access').reset(); await loadSettings();
  });
});
$('account-filter').addEventListener('change',renderLibrary);
$('catalog-account').addEventListener('change',clearSearch);
$('search').addEventListener('submit',event => { event.preventDefault(); query=$('query').value.trim(); if (!query) return; page=1; busy($('search').querySelector('button'),search); });
$('previous').addEventListener('click',() => busy($('previous'),async () => { page--; await search(); }));
$('next').addEventListener('click',() => busy($('next'),async () => { page++; await search(); }));
$('close-detail').addEventListener('click',() => $('detail').close());
let installPrompt;
window.addEventListener('beforeinstallprompt',event => { event.preventDefault(); installPrompt=event; $('install').hidden=false; });
$('install').addEventListener('click',() => busy($('install'),async () => { await installPrompt.prompt(); installPrompt=null; $('install').hidden=true; }));
window.addEventListener('offline',() => notify('Sin conexión. Tus datos se consultarán cuando vuelvas a estar conectado.',true));
// Invalidación al recargar o cerrar la pestaña (ADR-014): las blob URLs mueren
// con el documento, pero se revocan de forma explícita.
window.addEventListener('pagehide',() => revokeCovers());
// Origen no confiable (NFR-SVC-003): HTTP desde una dirección que el navegador
// no considera local. El aviso es persistente; en ese contexto las passkeys
// quedan deshabilitadas (hoy no hay passkeys: la constante es su preparación).
const secureOrigin = window.isSecureContext;
document.documentElement.dataset.secureOrigin = secureOrigin ? 'true' : 'false';
if (!secureOrigin) $('origin-warning').hidden = false;
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
// Detect approvals and revocations without repeatedly querying the library portal.
async function refreshPermissions() {
  if (!currentUser || document.hidden || settingsBusy) return;
  settingsBusy=true;
  try { if (await loadSettings()) await loadLibrary(); }
  catch (e) { if (!navigator.onLine || !currentUser) return; notify(e.message,true); }
  finally { settingsBusy=false; }
}
setInterval(refreshPermissions,60000);
document.addEventListener('visibilitychange',() => { if (!document.hidden) refreshPermissions(); });
const googleMessages = {
  linked: 'Cuenta de Google vinculada. Ya puedes usarla para entrar.',
  signed: 'Has entrado en BiblioCM con Google.',
  exists: 'Esa cuenta de Google ya está en uso, o tu email ya pertenece a una cuenta de BiblioCM.',
  'not-linked': 'Esa cuenta de Google todavía no está vinculada a ninguna cuenta de BiblioCM.',
  denied: 'Has cancelado el acceso con Google.',
  error: 'No se pudo completar el acceso con Google. Inténtalo de nuevo.'
};
(async () => {
  // Retorno desde el proveedor (`/?google=…`): se limpia la URL y se avisa; el
  // servidor ya consumió el `state`, así que no se puede repetir esa visita.
  const googleOutcome = new URLSearchParams(window.location.search).get('google');
  if (googleOutcome) {
    window.history.replaceState({}, '', window.location.pathname);
    notify(googleMessages[googleOutcome] || googleMessages.error,
           ['error', 'not-linked', 'exists'].includes(googleOutcome));
  }
  try {
    const session=await api('session');
    googleEnabled = Boolean(session.google && session.google.enabled);
    $('google-login-row').hidden = !googleEnabled;
    $('passkey-login-row').hidden = !passkeysUsable();
    if (!passkeysUsable()) {
      $('passkey-add').disabled = true;
      $('passkey-help').textContent = !webauthnAvailable()
        ? 'Las passkeys están deshabilitadas en este origen. Abre la app en http://localhost:8000 o detrás de HTTPS (guía mkcert en docs/operations.md).'
        : 'Chromium no admite passkeys con una dirección IP: abre la app como http://localhost:8000 (misma máquina) o detrás de HTTPS con un nombre de dominio.';
    }
    if (session.authenticated) await enter(session); else showSession(false);
  }
  catch (e) {
    // Sin panel resuelto no se deja la pantalla en blanco: se muestra el acceso.
    if (!libraryData) showSession(false);
    if (e.code==='API_VERSION') document.querySelectorAll('#login button,#register button').forEach(button => button.disabled=true);
    notify(e.message,true,e.code==='API_VERSION');
  }
  finally {
    $('boot-loading').hidden = true;
  }
})();
