/**
 * SNUKED HOSTER Premium Mini App - Main Application
 * OWNER/ADMIN Global Access Implementation
 * - Normal users: only own projects, profile shows only @username + photo
 * - Owner: global access, owner panel, user list with photo+@username only
 */

const state = {
  currentPage: 'home',
  user: null,
  projects: [],
  currentProject: null,
  activity: [],
  loading: true,
  authFailed: false,
  editingFile: null,
  logsInterval: null,
  is_owner: false,
  adminStats: null,
  adminUsers: [],
  currentAdminUserId: null,
  currentAdminUsername: null,
  currentAdminPhoto: null,
  adminViewing: false,
  adminFileList: [],
};

const API_BASE = '';

async function apiRequest(path, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...tg.getAuthHeaders(),
    ...(options.headers || {})
  };
  if (options.body instanceof FormData) {
    delete headers['Content-Type'];
  }
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    headers,
    ...options
  });
  if (res.status === 401) throw new Error('Unauthorized - Please reopen from Telegram');
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

function showToast(message, type = 'info', duration = 3000) {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
  toast.innerHTML = `
    <span class="toast-icon">${icons[type] || icons.info}</span>
    <span class="toast-message">${message}</span>
    <button class="toast-close" onclick="this.parentElement.remove()">✕</button>
  `;
  container.appendChild(toast);
  tg.haptic(type === 'error' ? 'error' : type === 'success' ? 'success' : 'light');
  setTimeout(() => {
    toast.style.animation = 'toastOut 0.3s forwards';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

function showModal(content) {
  const container = document.getElementById('modal-container');
  const modalContent = document.getElementById('modal-content');
  modalContent.innerHTML = content;
  container.classList.remove('hidden');
  document.body.style.overflow = 'hidden';
  tg.haptic('light');
}
function closeModal() {
  const container = document.getElementById('modal-container');
  container.classList.add('hidden');
  document.body.style.overflow = '';
}
function showConfirmModal(title, message, onConfirm, confirmText = 'Confirm', cancelText = 'Cancel', isDanger = false) {
  const content = `
    <div class="modal-header">
      <div class="modal-title">${title}</div>
      <button class="modal-close" onclick="closeModal()">✕</button>
    </div>
    <div class="modal-body">
      <p class="text-sm text-secondary">${message}</p>
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="closeModal()">${cancelText}</button>
      <button class="btn ${isDanger ? 'btn-danger' : 'btn-primary'}" id="confirm-btn">${confirmText}</button>
    </div>
  `;
  showModal(content);
  document.getElementById('confirm-btn').onclick = () => {
    closeModal();
    onConfirm();
  };
}

// Auth
async function authenticate() {
  try {
    const initData = tg.getInitData();
    if (initData) {
      try {
        await apiRequest('/api/auth/telegram', {
          method: 'POST',
          body: JSON.stringify({ initData })
        });
      } catch (e) {
        console.warn('Telegram auth handshake failed, trying /me', e);
      }
    }
    const me = await apiRequest('/api/me');
    state.user = me;
    state.is_owner = !!me.is_owner;
    state.authFailed = false;
    return true;
  } catch (err) {
    console.error('Auth failed', err);
    state.authFailed = true;
    if (!tg.isInsideTelegram() && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')) {
      console.warn('Dev mode mock user');
      state.user = {
        owner_id: 123456,
        username: 'dev_user',
        display_username: '@dev_user',
        photo_url: null,
        is_owner: false,
        stats: { total: 0, running: 0, stopped: 0, memory_usage: 0 }
      };
      state.is_owner = false;
      state.authFailed = false;
      return true;
    }
    return false;
  }
}

async function loadProjects() {
  try {
    const data = await apiRequest('/api/projects');
    state.projects = data.projects || [];
    return state.projects;
  } catch (err) {
    console.error('Failed to load projects', err);
    showToast('Failed to load projects', 'error');
    return [];
  }
}
async function loadActivity() {
  try {
    const data = await apiRequest('/api/activity?limit=20');
    state.activity = data.activity || [];
    return state.activity;
  } catch (err) {
    return [];
  }
}

// Helpers
function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
}
function formatFileSize(bytes) {
  if (!bytes && bytes !== 0) return '0 B';
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B','KB','MB','GB'];
  const i = Math.floor(Math.log(bytes)/Math.log(k));
  return parseFloat((bytes/Math.pow(k,i)).toFixed(1)) + ' ' + sizes[i];
}
function timeAgo(timestamp) {
  if (!timestamp) return 'unknown';
  let date = typeof timestamp === 'number' ? new Date(timestamp*1000) : new Date(timestamp);
  const seconds = Math.floor((new Date() - date)/1000);
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds/60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds/3600)}h ago`;
  if (seconds < 604800) return `${Math.floor(seconds/86400)}d ago`;
  return date.toLocaleDateString();
}
function getFileIcon(ext) {
  if (!ext) return '📄';
  ext = ext.toLowerCase().replace('.','');
  const icons = { py:'🐍', js:'🟨', ts:'🔷', json:'📋', txt:'📄', md:'📝', zip:'📦', env:'🔑', yml:'⚙️', yaml:'⚙️', html:'🌐', css:'🎨', sh:'💻' };
  return icons[ext] || '📄';
}
function getLanguageFromExt(ext) {
  ext = (ext||'').toLowerCase().replace('.','');
  const map = { py:'Python', js:'JavaScript', ts:'TypeScript', json:'JSON', md:'Markdown', sh:'Shell', yml:'YAML', yaml:'YAML', html:'HTML', css:'CSS', txt:'Text', env:'Env' };
  return map[ext] || ext.toUpperCase() || 'File';
}
function getActivityIcon(action) {
  const icons = { create_project:'🆕', upload:'📤', start:'▶️', stop:'⏹️', restart:'🔄', delete:'🗑️', edit_file:'✏️', upload_file:'📤', create_file:'📄', delete_file:'🗑️', rename_file:'✏️', login:'🔑', telegram_login:'🔐' };
  return icons[action] || '📊';
}
function formatActivity(a) {
  const map = { create_project:'Created project', upload:'Uploaded file', start:'Started project', stop:'Stopped project', restart:'Restarted project', delete:'Deleted project', edit_file:'Edited file', upload_file:'Uploaded file', create_file:'Created file', delete_file:'Deleted file', rename_file:'Renamed file', login:'Logged in', telegram_login:'Logged in via Telegram' };
  return map[a.action] || a.action;
}
function renderAvatar(photo_url, username, sizeClass='') {
  const safeUser = escapeHtml(username||'@user');
  if (photo_url) {
    return `<div class="user-card-avatar ${sizeClass}"><img src="${escapeHtml(photo_url)}" alt="${safeUser}" onerror="this.style.display='none'; this.parentElement.textContent='${(username||'U').replace('@','')[0]?.toUpperCase()||'U'}'"></div>`;
  }
  const initial = (username||'U').replace('@','')[0]?.toUpperCase() || 'U';
  return `<div class="user-card-avatar ${sizeClass}">${initial}</div>`;
}
function renderProfileAvatar(photo_url, username, large=false) {
  const cls = large ? 'profile-avatar-large' : 'user-card-avatar';
  if (photo_url) {
    return `<div class="${cls}"><img src="${escapeHtml(photo_url)}" alt="${escapeHtml(username)}" onerror="this.style.display='none'; this.parentElement.textContent='${(username||'U').replace('@','')[0]?.toUpperCase()||'U'}'"></div>`;
  }
  const initial = (username||'U').replace('@','')[0]?.toUpperCase() || 'U';
  return `<div class="${cls}">${initial}</div>`;
}

// Navigation
function navigateTo(page, params = {}) {
  tg.haptic('selection');
  if (state.logsInterval) {
    clearInterval(state.logsInterval);
    state.logsInterval = null;
  }
  state.currentPage = page;
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.page === page || (page.startsWith('owner') && btn.dataset.page === 'owner'));
  });
  // Back button logic
  const backMap = {
    home: null,
    projects: 'home',
    project: 'projects',
    files: 'project',
    editor: 'files',
    logs: 'project',
    create: 'home',
    activity: 'home',
    settings: 'home',
    owner: 'home',
    'owner-users': 'owner',
    'owner-user-projects': 'owner-users',
    'owner-all-projects': 'owner',
    'owner-project': 'owner-all-projects',
    'owner-files': 'owner-project',
    'owner-editor': 'owner-files',
    'owner-logs': 'owner-project',
  };
  const backTarget = backMap[page];
  if (!backTarget) tg.hideBackButton();
  else {
    tg.showBackButton(() => {
      if (page === 'files' || page === 'logs' || page === 'project') {
        if (state.adminViewing) navigateTo('owner-project', {id: params.id || state.currentProject?.id});
        else navigateTo(backTarget, params);
      } else if (page === 'editor') {
        if (state.adminViewing) navigateTo('owner-files', {id: params.projectId});
        else navigateTo('files', {id: params.projectId});
      } else if (page === 'owner-user-projects') {
        navigateTo('owner-users');
      } else if (page === 'owner-project' && state.currentAdminUserId) {
        navigateTo('owner-user-projects', {userId: state.currentAdminUserId});
      } else {
        navigateTo(backTarget);
      }
    });
  }

  switch(page) {
    case 'home': renderHome(); break;
    case 'projects': renderProjects(); break;
    case 'project': renderProjectDetail(params.id, {adminMode: false}); break;
    case 'files': renderFileManager(params.id, {adminMode: false}); break;
    case 'editor': renderEditor(params.projectId, params.path, {adminMode: false}); break;
    case 'logs': renderLogs(params.id, false); break;
    case 'create': renderCreateProject(); break;
    case 'activity': renderActivity(); break;
    case 'settings': renderSettings(); break;
    case 'owner': renderOwnerPanel(); break;
    case 'owner-users': renderOwnerUsers(); break;
    case 'owner-user-projects': renderOwnerUserProjects(params.userId, params.username, params.photo_url); break;
    case 'owner-all-projects': renderOwnerAllProjects(); break;
    case 'owner-project': renderProjectDetail(params.id, {adminMode: true}); break;
    case 'owner-files': renderFileManager(params.id, {adminMode: true}); break;
    case 'owner-editor': renderEditor(params.projectId, params.path, {adminMode: true}); break;
    case 'owner-logs': renderLogs(params.id, true); break;
    default: renderHome();
  }
  document.getElementById('app-content').scrollTop = 0;
  // FAB visibility
  const fab = document.getElementById('fab-create');
  if (fab) {
    if (['home','projects'].includes(page)) fab.classList.remove('hidden');
    else fab.classList.add('hidden');
  }
}

function renderSkeleton() {
  return `
    <div class="skeleton skeleton-title"></div>
    <div class="skeleton skeleton-text" style="width:80%"></div>
    <div class="skeleton skeleton-text" style="width:60%"></div>
    <div class="skeleton skeleton-card"></div>
    <div class="skeleton skeleton-card"></div>
  `;
}

// HOME
async function renderHome() {
  const content = document.getElementById('app-content');
  content.innerHTML = renderSkeleton();
  try {
    await Promise.all([loadProjects(), loadActivity()]);
    const user = state.user || {};
    const stats = user.stats || { total:0, running:0, stopped:0 };
    const recentProjects = state.projects.slice(0,3);
    const recentActivity = state.activity.slice(0,5);
    const displayName = user.display_username || '@username_unavailable';
    const photo = user.photo_url;

    content.innerHTML = `
      <div class="welcome-card card" style="background: var(--gradient-dark); border: 1px solid var(--border-secondary);">
        <div class="card-header">
          <div style="display:flex; align-items:center; gap:0.75rem;">
            ${renderProfileAvatar(photo, displayName, false)}
            <div>
              <div class="card-title">Welcome, ${escapeHtml(displayName)}! 👋 ${state.is_owner ? '<span class="owner-badge">👑 Owner</span>' : ''}</div>
              <div class="card-subtitle">${new Date().toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric'})} • Premium Hosting</div>
            </div>
          </div>
          <div class="card-icon">🚀</div>
        </div>
        <div style="display:flex; gap:0.5rem; margin-top:1rem;">
          <button class="btn btn-primary btn-sm" onclick="navigateTo('create')">+ New Project</button>
          <button class="btn btn-secondary btn-sm" onclick="navigateTo('projects')">View All</button>
          ${state.is_owner ? `<button class="btn btn-secondary btn-sm" style="border-color: rgba(245,158,11,0.3);" onclick="navigateTo('owner')">👑 Owner Panel</button>` : ''}
        </div>
      </div>

      <div class="stats-grid">
        <div class="stat-card"><div class="stat-value">${stats.total}</div><div class="stat-label">Total Projects</div><div class="stat-change positive">● All time</div></div>
        <div class="stat-card"><div class="stat-value" style="color: var(--accent-success)">${stats.running}</div><div class="stat-label">Running</div><div class="stat-change positive">● Active now</div></div>
        <div class="stat-card"><div class="stat-value">${stats.stopped}</div><div class="stat-label">Stopped</div><div class="stat-change">○ Idle</div></div>
        <div class="stat-card"><div class="stat-value">${Math.round(stats.memory_usage||0)} MB</div><div class="stat-label">Memory Used</div><div class="stat-change positive">● Live usage</div></div>
      </div>

      <div class="section">
        <div class="flex items-center justify-between mb-4">
          <h3 style="font-size:1rem; font-weight:600;">Recent Projects</h3>
          <button class="btn btn-secondary btn-sm" onclick="navigateTo('projects')">View All</button>
        </div>
        ${recentProjects.length===0 ? `
          <div class="empty-state card">
            <div class="empty-icon">📦</div>
            <div class="empty-title">No projects yet</div>
            <div class="empty-desc">Create your first bot hosting project to get started</div>
            <button class="btn btn-primary" onclick="navigateTo('create')">Create Project</button>
          </div>
        ` : recentProjects.map(p=>renderProjectCard(p,false)).join('')}
      </div>

      ${recentActivity.length>0 ? `
        <div class="section mt-4">
          <div class="flex items-center justify-between mb-4">
            <h3 style="font-size:1rem; font-weight:600;">Recent Activity</h3>
            <button class="btn btn-secondary btn-sm" onclick="navigateTo('activity')">View All</button>
          </div>
          <div class="activity-list">
            ${recentActivity.map(a=>`
              <div class="activity-item">
                <div class="activity-icon">${getActivityIcon(a.action)}</div>
                <div class="activity-content">
                  <div class="activity-title">${formatActivity(a)}</div>
                  <div class="activity-meta">${timeAgo(a.created_at)} • ${a.details||''}</div>
                </div>
              </div>
            `).join('')}
          </div>
        </div>
      `:''}
    `;
  } catch(err) {
    content.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">⚠️</div>
        <div class="empty-title">Failed to load dashboard</div>
        <div class="empty-desc">${escapeHtml(err.message)}</div>
        <button class="btn btn-primary" onclick="renderHome()">Retry</button>
      </div>
    `;
  }
}

function renderProjectCard(project, adminMode=false) {
  const status = project.runtime_status || 'stopped';
  const runtime = project.runtime || 'python';
  const runtimeIcon = runtime.includes('node') ? '🟢' : runtime.includes('python') ? '🐍' : '📦';
  const ownerBadge = adminMode && project.owner_username ? `<span style="font-size:0.7rem; color: var(--text-secondary);">@${escapeHtml(project.owner_username.replace('@',''))}</span>` : '';
  const clickAction = adminMode ? `navigateTo('owner-project', {id: ${project.id}})` : `navigateTo('project', {id: ${project.id}})`;
  const stopFn = adminMode ? `stopProject(${project.id}, true)` : `stopProject(${project.id}, false)`;
  const startFn = adminMode ? `startProject(${project.id}, true)` : `startProject(${project.id}, false)`;
  const restartFn = adminMode ? `restartProject(${project.id}, true)` : `restartProject(${project.id}, false)`;
  const logsFn = adminMode ? `navigateTo('owner-logs', {id: ${project.id}})` : `navigateTo('logs', {id: ${project.id}})`;
  const filesFn = adminMode ? `navigateTo('owner-files', {id: ${project.id}})` : `navigateTo('files', {id: ${project.id}})`;

  return `
    <div class="project-card" onclick="${clickAction}">
      <div class="project-card-header">
        <div>
          <div class="project-name">${runtimeIcon} ${escapeHtml(project.name)} ${ownerBadge}</div>
          <div class="project-meta">
            <span>${escapeHtml(runtime)}</span>
            <span>•</span>
            <span>${escapeHtml(project.main_file||'No entrypoint')}</span>
            <span>•</span>
            <span>${timeAgo(project.created_at)}</span>
          </div>
        </div>
        <div class="project-status ${status==='running'?'status-running':'status-stopped'}">
          <span class="status-dot"></span>
          ${escapeHtml(status)}
        </div>
      </div>
      <div class="project-actions">
        ${status==='running' ? `
          <button class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); ${stopFn}">⏹ Stop</button>
          <button class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); ${restartFn}">🔄 Restart</button>
        ` : `
          <button class="btn btn-success btn-sm" onclick="event.stopPropagation(); ${startFn}">▶️ Start</button>
        `}
        <button class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); ${logsFn}">📋 Logs</button>
        <button class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); ${filesFn}">📁 Files</button>
      </div>
    </div>
  `;
}

async function renderProjects() {
  const content = document.getElementById('app-content');
  content.innerHTML = `
    <div class="flex items-center justify-between mb-4">
      <h2 style="font-size:1.25rem; font-weight:700;">My Projects</h2>
      <button class="btn btn-primary btn-sm" onclick="navigateTo('create')">+ New</button>
    </div>
    ${renderSkeleton()}
  `;
  await loadProjects();
  if (state.projects.length===0) {
    content.innerHTML = `
      <div class="flex items-center justify-between mb-4">
        <h2 style="font-size:1.25rem; font-weight:700;">My Projects</h2>
        <button class="btn btn-primary btn-sm" onclick="navigateTo('create')">+ New</button>
      </div>
      <div class="empty-state card">
        <div class="empty-icon">📦</div>
        <div class="empty-title">No projects yet</div>
        <div class="empty-desc">Upload your bot files or create a new project to start hosting</div>
        <button class="btn btn-primary" onclick="navigateTo('create')">Create Project</button>
      </div>
    `;
    return;
  }
  content.innerHTML = `
    <div class="flex items-center justify-between mb-4">
      <h2 style="font-size:1.25rem; font-weight:700;">My Projects (${state.projects.length})</h2>
      <button class="btn btn-primary btn-sm" onclick="navigateTo('create')">+ New</button>
    </div>
    ${state.projects.map(p=>renderProjectCard(p,false)).join('')}
  `;
}

async function renderProjectDetail(projectId, opts={adminMode:false}) {
  const adminMode = !!opts.adminMode;
  state.adminViewing = adminMode;
  const content = document.getElementById('app-content');
  content.innerHTML = renderSkeleton();
  try {
    const url = adminMode ? `/api/admin/projects/${projectId}` : `/api/projects/${projectId}`;
    const project = await apiRequest(url);
    state.currentProject = project;
    const status = project.runtime_status;
    const resource = project.resource || {};
    const runtime = project.runtime || 'python';

    const backNav = adminMode ? (state.currentAdminUserId ? `navigateTo('owner-user-projects', {userId: ${state.currentAdminUserId}})` : `navigateTo('owner-all-projects')`) : `navigateTo('projects')`;
    const filesNav = adminMode ? `navigateTo('owner-files', {id: ${project.id}})` : `navigateTo('files', {id: ${project.id}})`;
    const logsNav = adminMode ? `navigateTo('owner-logs', {id: ${project.id}})` : `navigateTo('logs', {id: ${project.id}})`;
    const startFn = adminMode ? `startProject(${project.id}, true)` : `startProject(${project.id}, false)`;
    const stopFn = adminMode ? `stopProject(${project.id}, true)` : `stopProject(${project.id}, false)`;
    const restartFn = adminMode ? `restartProject(${project.id}, true)` : `restartProject(${project.id}, false)`;
    const deleteFn = adminMode ? `deleteProject(${project.id}, true)` : `deleteProject(${project.id}, false)`;

    content.innerHTML = `
      <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:1.25rem;">
        <button class="btn btn-secondary btn-icon" onclick="${backNav}">←</button>
        <h2 style="font-size:1.25rem; font-weight:700; flex:1;" class="truncate">${escapeHtml(project.name)}</h2>
        <button class="btn btn-secondary btn-sm" onclick="showProjectMenu(${project.id}, ${adminMode})">⋯</button>
      </div>

      ${adminMode ? `
        <div class="owner-panel-header">
          <div class="owner-icon">👑</div>
          <div>
            <div style="font-weight:600; font-size:0.875rem;">Owner Management Mode</div>
            <div style="font-size:0.75rem; color: var(--text-secondary);">Managing ${project.owner_display_username ? escapeHtml(project.owner_display_username) : '@'+escapeHtml(project.owner_username||'user')}'s project • ${project.owner_photo_url ? 'Photo available' : 'No photo'}</div>
          </div>
        </div>
        <div class="card" style="display:flex; align-items:center; gap:0.75rem; padding:0.75rem 1rem;">
          ${project.owner_photo_url ? `<div class="user-card-avatar" style="width:32px; height:32px;"><img src="${escapeHtml(project.owner_photo_url)}" onerror="this.style.display='none'"></div>` : renderAvatar(null, project.owner_display_username||project.owner_username)}
          <div>
            <div style="font-weight:600; font-size:0.875rem;">${escapeHtml(project.owner_display_username||'@'+(project.owner_username||'unknown'))}</div>
            <div style="font-size:0.7rem; color: var(--text-secondary);">Owner of this project</div>
          </div>
        </div>
      ` : ''}

      <div class="card" style="background: var(--gradient-dark);">
        <div class="flex items-center justify-between">
          <div>
            <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:0.5rem;">
              <div class="project-status ${status==='running'?'status-running':'status-stopped'}" style="font-size:0.75rem;">
                <span class="status-dot"></span>
                ${escapeHtml(status)}
              </div>
              <span class="text-xs text-secondary">${escapeHtml(runtime)} • ${escapeHtml(project.main_file||'No entrypoint')}</span>
            </div>
            <div class="text-sm text-secondary">Created ${timeAgo(project.created_at)} • ${project.files?.length||0} files</div>
          </div>
          <div style="text-align:right;">
            <div class="text-sm" style="font-weight:600;">${Math.round(resource.memory||0)} MB</div>
            <div class="text-xs text-tertiary">${Math.round(resource.uptime||0)}s uptime</div>
          </div>
        </div>
        <div style="display:grid; grid-template-columns: repeat(3,1fr); gap:0.5rem; margin-top:1.25rem;">
          ${status==='running' ? `
            <button class="btn btn-secondary" onclick="${stopFn}">⏹ Stop</button>
            <button class="btn btn-secondary" onclick="${restartFn}">🔄 Restart</button>
            <button class="btn btn-secondary" onclick="${logsNav}">📋 Logs</button>
          ` : `
            <button class="btn btn-primary" onclick="${startFn}">▶️ Start</button>
            <button class="btn btn-secondary" onclick="${logsNav}">📋 Logs</button>
            <button class="btn btn-secondary" onclick="${filesNav}">📁 Files</button>
          `}
        </div>
      </div>

      <div class="stats-grid" style="grid-template-columns: repeat(3,1fr);">
        <div class="stat-card"><div class="stat-value" style="font-size:1.25rem;">${project.files?.length||0}</div><div class="stat-label">Files</div></div>
        <div class="stat-card"><div class="stat-value" style="font-size:1.25rem;">${resource.pid||'-'}</div><div class="stat-label">PID</div></div>
        <div class="stat-card"><div class="stat-value" style="font-size:1.25rem;">${resource.restart_count||0}</div><div class="stat-label">Restarts</div></div>
      </div>

      <div class="card">
        <div class="card-header"><div class="card-title">Project Info</div></div>
        <div style="display:flex; flex-direction:column; gap:0.75rem;">
          <div class="flex justify-between"><span class="text-sm text-secondary">Name</span><span class="text-sm" style="font-weight:500;">${escapeHtml(project.name)}</span></div>
          <div class="flex justify-between"><span class="text-sm text-secondary">Runtime</span><span class="text-sm" style="font-weight:500;">${escapeHtml(runtime)}</span></div>
          <div class="flex justify-between"><span class="text-sm text-secondary">Entrypoint</span><span class="text-sm font-mono">${escapeHtml(project.main_file||'Not set')}</span></div>
          <div class="flex justify-between"><span class="text-sm text-secondary">Slug</span><span class="text-sm font-mono text-xs">${escapeHtml(project.slug)}</span></div>
          <div class="flex justify-between"><span class="text-sm text-secondary">Status</span><span class="text-sm" style="color:${status==='running'?'var(--accent-success)':''}; font-weight:600;">${escapeHtml(status)}</span></div>
        </div>
      </div>

      <div class="card">
        <div class="card-header"><div class="card-title">Quick Actions</div></div>
        <div style="display:grid; grid-template-columns: repeat(2,1fr); gap:0.75rem;">
          <button class="btn btn-secondary" onclick="${filesNav}"><span>📁</span> File Manager</button>
          <button class="btn btn-secondary" onclick="${logsNav}"><span>📋</span> View Logs</button>
          <button class="btn btn-secondary" onclick="navigateTo('create')"><span>📤</span> Upload Files</button>
          <button class="btn btn-danger" onclick="${deleteFn}"><span>🗑️</span> Delete</button>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="card-title">Files (${project.files_detailed?.length||project.files?.length||0})</div>
          <button class="btn btn-secondary btn-sm" onclick="${filesNav}">Manage</button>
        </div>
        <div class="file-list">
          ${(project.files_detailed||[]).slice(0,5).map(f=>`
            <div class="file-item" onclick="${adminMode ? `navigateTo('owner-editor', {projectId: ${project.id}, path: '${escapeHtml(f.path)}'})` : `navigateTo('editor', {projectId: ${project.id}, path: '${escapeHtml(f.path)}'})`}">
              <div class="file-icon ${f.extension.replace('.','')}">${getFileIcon(f.extension)}</div>
              <div class="file-info">
                <div class="file-name">${escapeHtml(f.path)}</div>
                <div class="file-meta">${formatFileSize(f.size)} • ${escapeHtml(f.extension)} • ${getLanguageFromExt(f.extension)}</div>
              </div>
            </div>
          `).join('') || (project.files||[]).slice(0,5).map(f=>`
            <div class="file-item"><div class="file-icon">📄</div><div class="file-info"><div class="file-name">${escapeHtml(f)}</div></div></div>
          `).join('') || '<div class="text-sm text-secondary" style="padding:1rem; text-align:center;">No files</div>'}
        </div>
        ${(project.files_detailed?.length||project.files?.length||0)>5 ? `<div class="text-xs text-center text-secondary" style="padding:0.75rem;">+${(project.files_detailed?.length||project.files?.length||0)-5} more files</div>` : ''}
      </div>
    `;
  } catch(err) {
    content.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">❌</div>
        <div class="empty-title">Failed to load project</div>
        <div class="empty-desc">${escapeHtml(err.message)}</div>
        <button class="btn btn-secondary" onclick="${adminMode ? `navigateTo('owner-all-projects')` : `navigateTo('projects')`}">Back</button>
      </div>
    `;
  }
}

async function renderFileManager(projectId, opts={adminMode:false}) {
  const adminMode = !!opts.adminMode;
  state.adminViewing = adminMode;
  const content = document.getElementById('app-content');
  const backTarget = adminMode ? `navigateTo('owner-project', {id: ${projectId}})` : `navigateTo('project', {id: ${projectId}})`;
  content.innerHTML = `
    <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:1.25rem;">
      <button class="btn btn-secondary btn-icon" onclick="${backTarget}">←</button>
      <h2 style="font-size:1.125rem; font-weight:700; flex:1;">File Manager ${adminMode?'<span class="owner-badge" style="font-size:0.6rem;">OWNER</span>':''}</h2>
      <button class="btn btn-primary btn-sm" onclick="showCreateFileModal(${projectId}, ${adminMode})">+ New</button>
    </div>
    ${renderSkeleton()}
  `;
  try {
    const url = adminMode ? `/api/admin/projects/${projectId}/files` : `/api/projects/${projectId}/files`;
    const data = await apiRequest(url);
    const files = data.files || [];
    state.adminFileList = files;

    content.innerHTML = `
      <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:1.25rem;">
        <button class="btn btn-secondary btn-icon" onclick="${backTarget}">←</button>
        <h2 style="font-size:1.125rem; font-weight:700; flex:1;">File Manager ${adminMode?'<span class="owner-badge" style="margin-left:0.5rem;">👑 Owner</span>':''}</h2>
        <button class="btn btn-secondary btn-sm" onclick="showUploadModal(${projectId}, ${adminMode})">📤 Upload</button>
        <button class="btn btn-primary btn-sm" onclick="showCreateFileModal(${projectId}, ${adminMode})">+ New</button>
      </div>

      <div class="card" style="padding:0.75rem;">
        <div style="display:flex; gap:0.5rem;">
          <input type="text" id="file-search" placeholder="Search files..." class="form-input" style="flex:1; padding:0.625rem 0.875rem;" oninput="filterFiles(this.value)">
          <button class="btn btn-secondary btn-sm" onclick="renderFileManager(${projectId}, {adminMode:${adminMode}})">🔄</button>
        </div>
      </div>

      ${files.length===0 ? `
        <div class="empty-state card">
          <div class="empty-icon">📁</div>
          <div class="empty-title">No files</div>
          <div class="empty-desc">This project has no files yet</div>
          <button class="btn btn-primary btn-sm" onclick="showCreateFileModal(${projectId}, ${adminMode})">Create File</button>
        </div>
      ` : `
        <div class="file-list" id="file-list">
          ${files.map(f=>`
            <div class="file-item" data-path="${escapeHtml(f.path)}" onclick="handleFileClick(${projectId}, '${escapeHtml(f.path)}', ${f.is_text}, ${adminMode})">
              <div class="file-icon ${f.extension.replace('.','')}">${getFileIcon(f.extension)}</div>
              <div class="file-info">
                <div class="file-name">${escapeHtml(f.path)}</div>
                <div class="file-meta">${formatFileSize(f.size)} • ${escapeHtml(f.extension||'file')} • ${getLanguageFromExt(f.extension)} • ${timeAgo(f.modified)}</div>
              </div>
              <div class="file-actions">
                <button class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); showRenameModal(${projectId}, '${escapeHtml(f.path)}', ${adminMode})">✏️</button>
                <button class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); ${adminMode ? `navigateTo('owner-editor', {projectId: ${projectId}, path: '${escapeHtml(f.path)}'})` : `navigateTo('editor', {projectId: ${projectId}, path: '${escapeHtml(f.path)}'})`}" ${!f.is_text?'disabled':''}>📝</button>
                <button class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); deleteFile(${projectId}, '${escapeHtml(f.path)}', ${adminMode})">🗑️</button>
              </div>
            </div>
          `).join('')}
        </div>
      `}
    `;
  } catch(err) {
    content.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">❌</div>
        <div class="empty-title">Failed to load files</div>
        <div class="empty-desc">${escapeHtml(err.message)}</div>
        <button class="btn btn-secondary" onclick="${backTarget}">Back</button>
      </div>
    `;
  }
}

async function renderEditor(projectId, filePath, opts={adminMode:false}) {
  const adminMode = !!opts.adminMode;
  state.adminViewing = adminMode;
  const content = document.getElementById('app-content');
  const backTarget = adminMode ? `navigateTo('owner-files', {id: ${projectId}})` : `navigateTo('files', {id: ${projectId}})`;
  content.innerHTML = `
    <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:1rem;">
      <button class="btn btn-secondary btn-icon" onclick="${backTarget}">←</button>
      <h2 style="font-size:1rem; font-weight:600; flex:1;" class="truncate">${escapeHtml(filePath)} ${adminMode?'<span class="owner-badge">OWNER</span>':''}</h2>
      <button class="btn btn-secondary btn-sm" onclick="renderEditor(${projectId}, '${escapeHtml(filePath)}', {adminMode:${adminMode}})">🔄</button>
    </div>
    <div class="editor-container">
      <div class="editor-header">
        <div class="editor-filename">
          <span>${getFileIcon(filePath.split('.').pop())}</span>
          ${escapeHtml(filePath)}
          <span style="font-size:0.7rem; color: var(--text-tertiary); margin-left:0.5rem;">${getLanguageFromExt(filePath.split('.').pop())}</span>
        </div>
        <div class="editor-actions">
          <button class="btn btn-primary btn-sm" id="save-btn" onclick="saveFile(${projectId}, '${escapeHtml(filePath)}', ${adminMode})">💾 Save</button>
        </div>
      </div>
      <textarea class="code-editor" id="code-editor" placeholder="Loading..."></textarea>
    </div>
    <div class="text-xs text-tertiary" style="margin-top:0.75rem; text-align:center;">
      ${adminMode ? '👑 Owner edit mode • ' : ''}File: ${escapeHtml(filePath)} • Language: ${getLanguageFromExt(filePath.split('.').pop())} • Press Ctrl+S to save
    </div>
  `;
  try {
    const url = adminMode ? `/api/admin/projects/${projectId}/files/${encodeURIComponent(filePath)}` : `/api/projects/${projectId}/files/${encodeURIComponent(filePath)}`;
    const data = await apiRequest(url);
    const editor = document.getElementById('code-editor');
    editor.value = data.content || '';
    state.editingFile = { projectId, path: filePath, original: data.content, adminMode };

    editor.addEventListener('input', () => {
      const saveBtn = document.getElementById('save-btn');
      if (editor.value !== state.editingFile.original) {
        saveBtn.textContent = '💾 Save*';
      } else {
        saveBtn.textContent = '💾 Save';
      }
    });
    editor.addEventListener('keydown', (e) => {
      if ((e.ctrlKey||e.metaKey) && e.key==='s') {
        e.preventDefault();
        saveFile(projectId, filePath, adminMode);
      }
      if (e.key==='Tab') {
        e.preventDefault();
        const start = editor.selectionStart;
        const end = editor.selectionEnd;
        editor.value = editor.value.substring(0,start)+'  '+editor.value.substring(end);
        editor.selectionStart = editor.selectionEnd = start+2;
      }
    });
  } catch(err) {
    showToast(`Failed to load file: ${err.message}`, 'error');
    const ed = document.getElementById('code-editor');
    if (ed) ed.value = `Error: ${err.message}`;
  }
}

async function renderLogs(projectId, adminMode=false) {
  state.adminViewing = !!adminMode;
  const content = document.getElementById('app-content');
  const backTarget = adminMode ? `navigateTo('owner-project', {id: ${projectId}})` : `navigateTo('project', {id: ${projectId}})`;
  content.innerHTML = `
    <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:1.25rem;">
      <button class="btn btn-secondary btn-icon" onclick="${backTarget}">←</button>
      <h2 style="font-size:1.125rem; font-weight:700; flex:1;">Live Logs ${adminMode?'<span class="owner-badge">OWNER</span>':''}</h2>
      <button class="btn btn-secondary btn-sm" onclick="clearLogs(${projectId}, ${adminMode})">🧹 Clear</button>
      <button class="btn btn-secondary btn-sm" onclick="copyLogs()">📋 Copy</button>
    </div>

    <div class="terminal">
      <div class="terminal-header">
        <div class="terminal-title">
          <div class="terminal-dots"><div class="terminal-dot red"></div><div class="terminal-dot yellow"></div><div class="terminal-dot green"></div></div>
          <span>console • ${projectId}</span>
          <span id="log-status" class="project-status status-stopped" style="margin-left:0.5rem; font-size:0.625rem;">CONNECTING</span>
        </div>
        <div style="display:flex; gap:0.375rem;">
          <button class="btn btn-secondary btn-sm" onclick="toggleAutoScroll()" id="autoscroll-btn">⬇️ Auto</button>
        </div>
      </div>
      <div class="terminal-content" id="terminal-content"><div class="text-secondary">Connecting to log stream...</div></div>
    </div>

    <div class="card" style="margin-top:1rem;">
      <div class="card-header"><div class="card-title">Log Controls</div></div>
      <div style="display:grid; grid-template-columns: repeat(2,1fr); gap:0.5rem;">
        <button class="btn btn-secondary btn-sm" onclick="refreshLogs(${projectId}, ${adminMode})">🔄 Refresh</button>
        <button class="btn btn-secondary btn-sm" onclick="downloadLogs(${projectId})">💾 Download</button>
      </div>
    </div>
  `;

  let autoScroll = true;
  const terminalContent = document.getElementById('terminal-content');
  const statusEl = document.getElementById('log-status');

  async function fetchLogs() {
    try {
      const url = adminMode ? `/api/admin/projects/${projectId}/logs?lines=200` : `/api/projects/${projectId}/logs?lines=200`;
      const data = await apiRequest(url);
      const lines = data.lines || [];
      statusEl.textContent = (data.status||'unknown').toUpperCase();
      statusEl.className = `project-status ${data.status==='running'?'status-running':'status-stopped'}`;
      statusEl.style.fontSize='0.625rem';
      statusEl.style.marginLeft='0.5rem';
      if (lines.length===0) {
        terminalContent.innerHTML = '<div class="text-tertiary">No logs yet. Start the project to see output.</div>';
      } else {
        terminalContent.innerHTML = lines.map(line=>{
          let cls='';
          if (line.toLowerCase().includes('error')||line.toLowerCase().includes('exception')) cls='error';
          else if (line.toLowerCase().includes('success')||line.includes('✅')) cls='success';
          else if (line.toLowerCase().includes('warning')||line.includes('⚠️')) cls='warning';
          return `<div class="terminal-line ${cls}">${escapeHtml(line)}</div>`;
        }).join('');
        if (autoScroll) terminalContent.scrollTop = terminalContent.scrollHeight;
      }
    } catch(err) {
      terminalContent.innerHTML = `<div class="terminal-line error">Failed to fetch logs: ${escapeHtml(err.message)}</div>`;
    }
  }
  await fetchLogs();
  state.logsInterval = setInterval(fetchLogs, 2000);

  window.toggleAutoScroll = () => {
    autoScroll = !autoScroll;
    const btn = document.getElementById('autoscroll-btn');
    if (btn) {
      btn.textContent = autoScroll ? '⬇️ Auto' : '⏸️ Manual';
      btn.classList.toggle('btn-primary', autoScroll);
    }
    if (autoScroll) terminalContent.scrollTop = terminalContent.scrollHeight;
  };
  window.refreshLogs = fetchLogs;
  window.copyLogs = () => {
    const text = terminalContent.innerText;
    navigator.clipboard.writeText(text).then(()=>showToast('Logs copied','success')).catch(()=>showToast('Failed to copy','error'));
  };
  window.downloadLogs = () => {
    const text = terminalContent.innerText;
    const blob = new Blob([text], {type:'text/plain'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `logs-${projectId}-${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };
  window.clearLogs = async (pid, isAdmin) => {
    try {
      const url = isAdmin ? `/api/admin/projects/${pid}/logs` : `/api/projects/${pid}/logs`;
      await apiRequest(url, {method:'DELETE'});
      showToast('Logs cleared','success');
      fetchLogs();
    } catch(err) {
      showToast(`Failed to clear logs: ${err.message}`,'error');
    }
  };
}

// CREATE PROJECT
function renderCreateProject() {
  const content = document.getElementById('app-content');
  content.innerHTML = `
    <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:1.25rem;">
      <button class="btn btn-secondary btn-icon" onclick="navigateTo('home')">←</button>
      <h2 style="font-size:1.25rem; font-weight:700;">Create Project</h2>
    </div>

    <div class="card">
      <div class="form-group">
        <label class="form-label">Project Name *</label>
        <input type="text" id="project-name" class="form-input" placeholder="my-awesome-bot" maxlength="64">
        <div class="form-hint">Use lowercase, no spaces. Eg: my-telegram-bot</div>
      </div>
      <div class="form-group">
        <label class="form-label">Runtime</label>
        <select id="project-runtime" class="form-select">
          <option value="python">🐍 Python (recommended for Telegram bots)</option>
          <option value="node">🟢 Node.js (JavaScript/TypeScript)</option>
          <option value="python+node">🔀 Python + Node.js (hybrid)</option>
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Description (optional)</label>
        <textarea id="project-desc" class="form-textarea" placeholder="What does your bot do?" rows="3"></textarea>
      </div>
    </div>

    <div class="card">
      <div class="card-header"><div class="card-title">Upload Files</div><div class="card-subtitle">ZIP or single file (optional)</div></div>
      <div class="upload-zone" id="upload-zone" onclick="document.getElementById('file-input').click()">
        <div class="upload-icon">📤</div>
        <div class="upload-text">Tap to upload or drag & drop</div>
        <div class="upload-hint">Supports .py, .js, .zip, .json, .txt (max 25MB)</div>
        <input type="file" id="file-input" style="display:none;" accept=".py,.js,.json,.txt,.zip,.env,.md" onchange="handleFileSelect(this.files)">
        <div id="upload-preview" class="hidden" style="margin-top:1rem; text-align:left;">
          <div class="file-item" style="background: var(--bg-tertiary); border-radius: var(--radius-md);">
            <div class="file-icon">📄</div>
            <div class="file-info"><div class="file-name" id="upload-filename">file.py</div><div class="file-meta" id="upload-filesize">0 KB</div></div>
            <button class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); clearUpload()">✕</button>
          </div>
        </div>
      </div>
      <div class="form-hint" style="margin-top:0.75rem;">💡 Tip: If you upload a ZIP, we'll auto-detect your main file</div>
    </div>

    <div style="display:flex; gap:0.75rem; margin-top:1.5rem;">
      <button class="btn btn-secondary" style="flex:1;" onclick="navigateTo('home')">Cancel</button>
      <button class="btn btn-primary" style="flex:2;" onclick="createProject()" id="create-btn">🚀 Create Project</button>
    </div>
  `;
  const zone = document.getElementById('upload-zone');
  if (zone) {
    zone.addEventListener('dragover', e=>{e.preventDefault(); zone.classList.add('dragover');});
    zone.addEventListener('dragleave', ()=>zone.classList.remove('dragover'));
    zone.addEventListener('drop', e=>{e.preventDefault(); zone.classList.remove('dragover'); handleFileSelect(e.dataTransfer.files);});
  }
}

async function renderActivity() {
  const content = document.getElementById('app-content');
  content.innerHTML = `<h2 style="font-size:1.25rem; font-weight:700; margin-bottom:1.25rem;">Activity ${state.is_owner?'<span class="owner-badge">Global</span>':''}</h2>${renderSkeleton()}`;
  await loadActivity();
  if (state.activity.length===0) {
    content.innerHTML = `<h2 style="font-size:1.25rem; font-weight:700; margin-bottom:1.25rem;">Activity</h2><div class="empty-state card"><div class="empty-icon">📊</div><div class="empty-title">No activity yet</div><div class="empty-desc">Your project actions will appear here</div></div>`;
    return;
  }
  content.innerHTML = `
    <h2 style="font-size:1.25rem; font-weight:700; margin-bottom:1.25rem;">${state.is_owner?'Global Activity':'Recent Activity'} ${state.is_owner?'<span class="owner-badge">👑 Owner View</span>':''}</h2>
    <div class="activity-list">
      ${state.activity.map(a=>`
        <div class="activity-item">
          <div class="activity-icon">${getActivityIcon(a.action)}</div>
          <div class="activity-content">
            <div class="activity-title">${formatActivity(a)}</div>
            <div class="activity-meta">${timeAgo(a.created_at)} • ${escapeHtml(a.details||a.action)} ${a.project_id?`• Project #${a.project_id}`:''}</div>
          </div>
        </div>
      `).join('')}
    </div>
    <button class="btn btn-secondary btn-block" style="margin-top:1rem;" onclick="loadActivity().then(()=>renderActivity())">🔄 Refresh</button>
  `;
}

// SETTINGS / PROFILE - ONLY @username + photo per spec
function renderSettings() {
  const user = state.user || {};
  const displayUsername = user.display_username || '@username_unavailable';
  const photoUrl = user.photo_url;
  const stats = user.stats || {total:0, running:0, stopped:0};

  document.getElementById('app-content').innerHTML = `
    <h2 style="font-size:1.25rem; font-weight:700; margin-bottom:1.25rem;">Profile ${state.is_owner?'<span class="owner-badge">👑 Owner</span>':''}</h2>

    <div class="profile-hero">
      ${renderProfileAvatar(photoUrl, displayUsername, true)}
      <div class="profile-username">${escapeHtml(displayUsername)}</div>
      <div class="profile-subtitle">${state.is_owner ? '👑 Owner • Premium Hosting • SNUKED HOSTER' : 'Premium Hosting • SNUKED HOSTER'}</div>
    </div>

    <div class="stats-grid" style="grid-template-columns: repeat(3,1fr);">
      <div class="stat-card"><div class="stat-value">${stats.total||0}</div><div class="stat-label">Projects</div></div>
      <div class="stat-card"><div class="stat-value" style="color: var(--accent-success)">${stats.running||0}</div><div class="stat-label">Running</div></div>
      <div class="stat-card"><div class="stat-value">${stats.stopped||0}</div><div class="stat-label">Stopped</div></div>
    </div>

    <div class="settings-section">
      <div class="settings-title">Account</div>
      <div class="settings-card">
        <div class="settings-item">
          <div class="settings-item-info">
            <div class="settings-item-label">Telegram Username</div>
            <div class="settings-item-desc">${escapeHtml(displayUsername)}</div>
          </div>
          ${photoUrl ? `<img src="${escapeHtml(photoUrl)}" style="width:36px;height:36px;border-radius:50%;object-fit:cover;">` : `<div class="user-card-avatar" style="width:36px;height:36px;">${(displayUsername.replace('@','')[0]||'U').toUpperCase()}</div>`}
        </div>
        <div class="settings-item">
          <div class="settings-item-info">
            <div class="settings-item-label">Role</div>
            <div class="settings-item-desc">${state.is_owner ? 'Owner - Full Access to All Projects' : 'User - Own Projects Only'}</div>
          </div>
          <span class="text-xs">${state.is_owner?'👑 Owner':'👤 User'}</span>
        </div>
      </div>
    </div>

    <div class="settings-section">
      <div class="settings-title">Preferences</div>
      <div class="settings-card">
        <div class="settings-item">
          <div class="settings-item-info"><div class="settings-item-label">Haptic Feedback</div><div class="settings-item-desc">Vibration on actions</div></div>
          <div class="toggle active" onclick="this.classList.toggle('active')"><div class="toggle-thumb"></div></div>
        </div>
        <div class="settings-item">
          <div class="settings-item-info"><div class="settings-item-label">Auto-scroll Logs</div><div class="settings-item-desc">Follow new log lines</div></div>
          <div class="toggle active" onclick="this.classList.toggle('active')"><div class="toggle-thumb"></div></div>
        </div>
        <div class="settings-item">
          <div class="settings-item-info"><div class="settings-item-label">Theme</div><div class="settings-item-desc">Dark • Telegram native</div></div>
          <span class="text-xs text-secondary">🌙 Dark</span>
        </div>
      </div>
    </div>

    <div class="settings-section">
      <div class="settings-title">About</div>
      <div class="settings-card">
        <div class="settings-item">
          <div class="settings-item-info"><div class="settings-item-label">SNUKED HOSTER Version</div><div class="settings-item-desc">Premium Mini App Edition</div></div>
          <span class="text-xs text-tertiary">v2.0.0</span>
        </div>
        <div class="settings-item">
          <div class="settings-item-info"><div class="settings-item-label">Backend Status</div><div class="settings-item-desc" id="backend-status">Checking...</div></div>
          <div class="status-dot" style="width:8px;height:8px;background:var(--accent-success);border-radius:50%;"></div>
        </div>
      </div>
    </div>

    <div style="margin-top:2rem; display:flex; flex-direction:column; gap:0.75rem;">
      <button class="btn btn-secondary btn-block" onclick="tg.openLink('https://github.com/allancaustroo75-art/Web-app-hosting-bot-hai-')">📖 Documentation</button>
      <button class="btn btn-secondary btn-block" onclick="logout()">🚪 Logout / Reset Session</button>
      <div class="text-xs text-center text-tertiary" style="margin-top:1rem;">
        Made with ❤️ for Telegram • Secure • Fast • Premium<br>
        Backend: ${escapeHtml(window.location.hostname)} • Only @username + photo displayed per privacy
      </div>
    </div>
  `;

  fetch('/health').then(r=>r.json()).then(data=>{
    const el=document.getElementById('backend-status');
    if (el) el.textContent = data.status==='ok' ? `✅ Online • Bot ${data.telegram_configured?'connected':'offline'}` : '❌ Offline';
  }).catch(()=>{
    const el=document.getElementById('backend-status');
    if (el) el.textContent='❌ Unreachable';
  });
}

// OWNER PANEL
async function renderOwnerPanel() {
  if (!state.is_owner) {
    document.getElementById('app-content').innerHTML = `
      <div class="empty-state card">
        <div class="empty-icon">🔒</div>
        <div class="empty-title">Access Denied</div>
        <div class="empty-desc">Owner panel is only visible to the owner</div>
        <button class="btn btn-secondary" onclick="navigateTo('home')">Back Home</button>
      </div>
    `;
    return;
  }
  const content = document.getElementById('app-content');
  content.innerHTML = `
    <h2 style="font-size:1.25rem; font-weight:700; margin-bottom:1.25rem; display:flex; align-items:center; gap:0.5rem;">👑 Owner Panel <span class="owner-badge">ADMIN</span></h2>
    ${renderSkeleton()}
  `;
  try {
    const stats = await apiRequest('/api/admin/stats');
    state.adminStats = stats;
    const usersData = await apiRequest('/api/admin/users');
    const users = usersData.users || [];
    state.adminUsers = users;

    content.innerHTML = `
      <div class="owner-panel-header">
        <div class="owner-icon">👑</div>
        <div>
          <div style="font-weight:700; font-size:1rem;">Owner Global Access</div>
          <div style="font-size:0.8rem; color: var(--text-secondary);">Manage every user's hosted project • Server-side authorized</div>
        </div>
      </div>

      <div class="stats-grid" style="grid-template-columns: repeat(2,1fr);">
        <div class="stat-card"><div class="stat-value">${stats.total_users}</div><div class="stat-label">Total Users</div><div class="stat-change positive">● Registered</div></div>
        <div class="stat-card"><div class="stat-value">${stats.total_projects}</div><div class="stat-label">Total Projects</div><div class="stat-change positive">● All time</div></div>
        <div class="stat-card"><div class="stat-value" style="color: var(--accent-success)">${stats.running_projects}</div><div class="stat-label">Running</div><div class="stat-change positive">● Active now</div></div>
        <div class="stat-card"><div class="stat-value">${stats.stopped_projects}</div><div class="stat-label">Stopped</div><div class="stat-change">○ Idle</div></div>
      </div>

      <div style="display:grid; grid-template-columns: repeat(2,1fr); gap:0.75rem; margin-bottom:1.5rem;">
        <button class="btn btn-primary" onclick="navigateTo('owner-users')">👥 View Users (${stats.total_users})</button>
        <button class="btn btn-secondary" onclick="navigateTo('owner-all-projects')">📦 All Projects (${stats.total_projects})</button>
      </div>

      <div class="section">
        <div class="flex items-center justify-between mb-4">
          <h3 style="font-size:1rem; font-weight:600;">Recent Users</h3>
          <button class="btn btn-secondary btn-sm" onclick="navigateTo('owner-users')">View All</button>
        </div>
        ${users.slice(0,5).map(u=>renderUserCard(u)).join('') || '<div class="text-sm text-secondary card" style="padding:1rem; text-align:center;">No users yet</div>'}
      </div>

      <div class="card" style="margin-top:1.5rem; background: rgba(245,158,11,0.05); border-color: rgba(245,158,11,0.2);">
        <div style="display:flex; gap:0.75rem;">
          <div style="font-size:1.25rem;">🛡️</div>
          <div>
            <div class="text-sm" style="font-weight:600; margin-bottom:0.25rem;">Security Note</div>
            <div class="text-xs text-secondary" style="line-height:1.5;">
              All owner actions are server-side authorized via OWNER_USER_ID. Client flags are never trusted. Path traversal and IDOR protections active.
            </div>
          </div>
        </div>
      </div>
    `;
  } catch(err) {
    content.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">❌</div>
        <div class="empty-title">Failed to load owner panel</div>
        <div class="empty-desc">${escapeHtml(err.message)}</div>
        <button class="btn btn-primary" onclick="renderOwnerPanel()">Retry</button>
      </div>
    `;
  }
}

function renderUserCard(user) {
  const username = user.display_username || '@username_unavailable';
  const photo = user.photo_url;
  return `
    <div class="user-card" onclick="navigateTo('owner-user-projects', {userId: ${user.user_id}, username: '${escapeHtml(username)}', photo_url: '${escapeHtml(photo||'')}'})">
      ${photo ? `<div class="user-card-avatar"><img src="${escapeHtml(photo)}" alt="${escapeHtml(username)}" onerror="this.style.display='none'; this.parentElement.textContent='${(username.replace('@','')[0]||'U').toUpperCase()}'"></div>` : `<div class="user-card-avatar">${(username.replace('@','')[0]||'U').toUpperCase()}</div>`}
      <div class="user-card-info">
        <div class="user-card-username">${escapeHtml(username)}</div>
        <div class="user-card-meta">${user.project_count||0} projects • ${user.running_count||0} running • Joined ${timeAgo(user.created_at)}</div>
      </div>
      <div style="color: var(--text-tertiary);">›</div>
    </div>
  `;
}

async function renderOwnerUsers() {
  if (!state.is_owner) {
    document.getElementById('app-content').innerHTML = `<div class="empty-state card"><div class="empty-icon">🔒</div><div class="empty-title">Access Denied</div></div>`;
    return;
  }
  const content = document.getElementById('app-content');
  content.innerHTML = `
    <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:1.25rem;">
      <button class="btn btn-secondary btn-icon" onclick="navigateTo('owner')">←</button>
      <h2 style="font-size:1.25rem; font-weight:700; flex:1;">All Users <span class="owner-badge">${state.adminUsers.length||''}</span></h2>
      <button class="btn btn-secondary btn-sm" onclick="renderOwnerUsers()">🔄</button>
    </div>
    ${renderSkeleton()}
  `;
  try {
    const data = await apiRequest('/api/admin/users');
    const users = data.users || [];
    state.adminUsers = users;

    content.innerHTML = `
      <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:1.25rem;">
        <button class="btn btn-secondary btn-icon" onclick="navigateTo('owner')">←</button>
        <h2 style="font-size:1.25rem; font-weight:700; flex:1;">All Users (${users.length})</h2>
        <button class="btn btn-secondary btn-sm" onclick="renderOwnerUsers()">🔄</button>
      </div>

      <div class="card" style="padding:0.75rem;">
        <input type="text" id="user-search" placeholder="Search @username..." class="form-input" style="padding:0.625rem 0.875rem;" oninput="filterUserCards(this.value)">
      </div>

      <div id="user-list">
        ${users.length===0 ? `
          <div class="empty-state card"><div class="empty-icon">👥</div><div class="empty-title">No users yet</div></div>
        ` : users.map(u=>renderUserCard(u)).join('')}
      </div>
    `;
  } catch(err) {
    content.innerHTML = `<div class="empty-state"><div class="empty-icon">❌</div><div class="empty-title">Failed to load users</div><div class="empty-desc">${escapeHtml(err.message)}</div><button class="btn btn-secondary" onclick="navigateTo('owner')">Back</button></div>`;
  }
}

async function renderOwnerUserProjects(userId, username, photo_url) {
  if (!state.is_owner) return;
  state.currentAdminUserId = userId;
  state.currentAdminUsername = username;
  state.currentAdminPhoto = photo_url;
  const content = document.getElementById('app-content');
  content.innerHTML = `
    <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:1.25rem;">
      <button class="btn btn-secondary btn-icon" onclick="navigateTo('owner-users')">←</button>
      <h2 style="font-size:1.125rem; font-weight:700; flex:1;">${escapeHtml(username||'@user')}'s Projects</h2>
      <button class="btn btn-secondary btn-sm" onclick="renderOwnerUserProjects(${userId}, '${escapeHtml(username||'')}', '${escapeHtml(photo_url||'')}')">🔄</button>
    </div>
    ${renderSkeleton()}
  `;
  try {
    const data = await apiRequest(`/api/admin/users/${userId}/projects`);
    const projects = data.projects || [];
    const userInfo = data.user || { display_username: username, photo_url: photo_url };

    content.innerHTML = `
      <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:1.25rem;">
        <button class="btn btn-secondary btn-icon" onclick="navigateTo('owner-users')">←</button>
        <h2 style="font-size:1.125rem; font-weight:700; flex:1;" class="truncate">${escapeHtml(userInfo.display_username||username||'@user')} Projects</h2>
        <button class="btn btn-secondary btn-sm" onclick="renderOwnerUserProjects(${userId}, '${escapeHtml(username||'')}', '${escapeHtml(photo_url||'')}')">🔄</button>
      </div>

      <div class="card" style="display:flex; align-items:center; gap:0.875rem;">
        ${userInfo.photo_url ? `<div class="user-card-avatar"><img src="${escapeHtml(userInfo.photo_url)}" onerror="this.style.display='none'"></div>` : renderAvatar(null, userInfo.display_username||username)}
        <div>
          <div style="font-weight:600;">${escapeHtml(userInfo.display_username||username||'@username_unavailable')}</div>
          <div style="font-size:0.75rem; color: var(--text-secondary);">${projects.length} projects • ${projects.filter(p=>p.runtime_status==='running').length} running</div>
        </div>
      </div>

      ${projects.length===0 ? `
        <div class="empty-state card"><div class="empty-icon">📦</div><div class="empty-title">No projects</div><div class="empty-desc">This user has no projects yet</div></div>
      ` : projects.map(p=>renderProjectCard(p,true)).join('')}
    `;
  } catch(err) {
    content.innerHTML = `<div class="empty-state"><div class="empty-icon">❌</div><div class="empty-title">Failed to load projects</div><div class="empty-desc">${escapeHtml(err.message)}</div><button class="btn btn-secondary" onclick="navigateTo('owner-users')">Back</button></div>`;
  }
}

async function renderOwnerAllProjects() {
  if (!state.is_owner) return;
  const content = document.getElementById('app-content');
  content.innerHTML = `
    <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:1.25rem;">
      <button class="btn btn-secondary btn-icon" onclick="navigateTo('owner')">←</button>
      <h2 style="font-size:1.25rem; font-weight:700; flex:1;">All Projects</h2>
      <button class="btn btn-secondary btn-sm" onclick="renderOwnerAllProjects()">🔄</button>
    </div>
    ${renderSkeleton()}
  `;
  try {
    const data = await apiRequest('/api/admin/projects');
    const projects = data.projects || [];
    content.innerHTML = `
      <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:1.25rem;">
        <button class="btn btn-secondary btn-icon" onclick="navigateTo('owner')">←</button>
        <h2 style="font-size:1.25rem; font-weight:700; flex:1;">All Projects (${projects.length}) <span class="owner-badge">Global</span></h2>
        <button class="btn btn-secondary btn-sm" onclick="renderOwnerAllProjects()">🔄</button>
      </div>

      <div class="card" style="padding:0.75rem;">
        <input type="text" id="project-search" placeholder="Search projects or @username..." class="form-input" style="padding:0.625rem 0.875rem;" oninput="filterProjectCards(this.value)">
      </div>

      <div id="all-project-list">
        ${projects.length===0 ? `<div class="empty-state card"><div class="empty-icon">📦</div><div class="empty-title">No projects</div></div>` : projects.map(p=>renderProjectCard(p,true)).join('')}
      </div>
    `;
  } catch(err) {
    content.innerHTML = `<div class="empty-state"><div class="empty-icon">❌</div><div class="empty-title">Failed to load</div><div class="empty-desc">${escapeHtml(err.message)}</div><button class="btn btn-secondary" onclick="navigateTo('owner')">Back</button></div>`;
  }
}

// ACTIONS
let pendingUploadFile = null;
function handleFileSelect(files) {
  if (!files||files.length===0) return;
  const file = files[0];
  if (file.size > 25*1024*1024) { showToast('File too large (max 25MB)','error'); return; }
  pendingUploadFile = file;
  const preview = document.getElementById('upload-preview');
  if (preview) {
    preview.classList.remove('hidden');
    document.getElementById('upload-filename').textContent = file.name;
    document.getElementById('upload-filesize').textContent = formatFileSize(file.size);
  }
  tg.haptic('success');
}
function clearUpload() {
  pendingUploadFile = null;
  const preview = document.getElementById('upload-preview');
  if (preview) preview.classList.add('hidden');
  const inp = document.getElementById('file-input');
  if (inp) inp.value='';
}
async function createProject() {
  const nameEl = document.getElementById('project-name');
  const runtimeEl = document.getElementById('project-runtime');
  const descEl = document.getElementById('project-desc');
  const btn = document.getElementById('create-btn');
  const name = nameEl.value.trim();
  if (!name) { showToast('Project name required','error'); nameEl.focus(); tg.haptic('error'); return; }
  if (name.length<3) { showToast('Project name too short','error'); return; }
  btn.disabled=true; btn.textContent='⏳ Creating...';
  try {
    const formData = new FormData();
    formData.append('name', name);
    formData.append('runtime', runtimeEl.value);
    formData.append('description', descEl.value);
    if (pendingUploadFile) formData.append('file', pendingUploadFile);
    const project = await apiRequest('/api/projects', {method:'POST', body: formData});
    showToast(`Project "${name}" created!`,'success');
    tg.haptic('success');
    navigateTo('project', {id: project.id});
  } catch(err) {
    showToast(`Failed to create: ${err.message}`,'error');
    btn.disabled=false; btn.textContent='🚀 Create Project';
  }
}

async function startProject(id, adminMode=false) {
  try {
    showToast('Starting project...','info');
    const url = adminMode ? `/api/admin/projects/${id}/start` : `/api/projects/${id}/start`;
    await apiRequest(url, {method:'POST'});
    showToast('Project started!','success');
    if (state.currentPage.includes('project')) renderProjectDetail(id, {adminMode});
    else if (state.currentPage==='home') renderHome();
    else if (state.currentPage==='projects') renderProjects();
    else if (state.currentPage==='owner-all-projects') renderOwnerAllProjects();
    else if (state.currentPage==='owner-user-projects') renderOwnerUserProjects(state.currentAdminUserId, state.currentAdminUsername, state.currentAdminPhoto);
  } catch(err) { showToast(`Start failed: ${err.message}`,'error'); }
}
async function stopProject(id, adminMode=false) {
  try {
    showToast('Stopping project...','info');
    const url = adminMode ? `/api/admin/projects/${id}/stop` : `/api/projects/${id}/stop`;
    await apiRequest(url, {method:'POST'});
    showToast('Project stopped','success');
    if (state.currentPage.includes('project')) renderProjectDetail(id, {adminMode});
    else if (state.currentPage==='home') renderHome();
    else if (state.currentPage==='projects') renderProjects();
    else if (state.currentPage==='owner-all-projects') renderOwnerAllProjects();
    else if (state.currentPage==='owner-user-projects') renderOwnerUserProjects(state.currentAdminUserId, state.currentAdminUsername, state.currentAdminPhoto);
  } catch(err) { showToast(`Stop failed: ${err.message}`,'error'); }
}
async function restartProject(id, adminMode=false) {
  try {
    showToast('Restarting...','info');
    const url = adminMode ? `/api/admin/projects/${id}/restart` : `/api/projects/${id}/restart`;
    await apiRequest(url, {method:'POST'});
    showToast('Project restarted!','success');
    if (state.currentPage.includes('project')) renderProjectDetail(id, {adminMode});
  } catch(err) { showToast(`Restart failed: ${err.message}`,'error'); }
}
async function deleteProject(id, adminMode=false) {
  const project = state.projects.find(p=>p.id===id) || state.currentProject;
  const name = project?.name || `Project #${id}`;
  showConfirmModal('Delete Project', `Are you sure you want to delete "${escapeHtml(name)}"? This cannot be undone and all files will be lost.`, async ()=>{
    try {
      const url = adminMode ? `/api/admin/projects/${id}` : `/api/projects/${id}`;
      await apiRequest(url, {method:'DELETE'});
      showToast('Project deleted','success');
      if (adminMode) {
        if (state.currentAdminUserId) navigateTo('owner-user-projects', {userId: state.currentAdminUserId});
        else navigateTo('owner-all-projects');
      } else navigateTo('projects');
    } catch(err) { showToast(`Delete failed: ${err.message}`,'error'); }
  }, 'Delete', 'Cancel', true);
}

async function saveFile(projectId, filePath, adminMode=false) {
  const editor = document.getElementById('code-editor');
  const btn = document.getElementById('save-btn');
  const content = editor.value;
  btn.disabled=true; btn.textContent='⏳ Saving...';
  try {
    const url = adminMode ? `/api/admin/projects/${projectId}/files/${encodeURIComponent(filePath)}` : `/api/projects/${projectId}/files/${encodeURIComponent(filePath)}`;
    await apiRequest(url, {method:'PUT', body: JSON.stringify({content})});
    showToast('File saved!','success');
    if (state.editingFile) state.editingFile.original = content;
    btn.textContent='💾 Save';
    tg.haptic('success');
  } catch(err) {
    showToast(`Save failed: ${err.message}`,'error');
    btn.textContent='💾 Save*';
  } finally { btn.disabled=false; }
}
async function deleteFile(projectId, filePath, adminMode=false) {
  showConfirmModal('Delete File', `Delete "${escapeHtml(filePath)}"? This cannot be undone.`, async ()=>{
    try {
      const url = adminMode ? `/api/admin/projects/${projectId}/files/${encodeURIComponent(filePath)}` : `/api/projects/${projectId}/files/${encodeURIComponent(filePath)}`;
      await apiRequest(url, {method:'DELETE'});
      showToast('File deleted','success');
      renderFileManager(projectId, {adminMode});
    } catch(err) { showToast(`Delete failed: ${err.message}`,'error'); }
  }, 'Delete', 'Cancel', true);
}
function handleFileClick(projectId, path, isText, adminMode=false) {
  if (isText) {
    if (adminMode) navigateTo('owner-editor', {projectId, path});
    else navigateTo('editor', {projectId, path});
  } else showToast('Binary file cannot be edited','warning');
}
function showCreateFileModal(projectId, adminMode=false) {
  const content = `
    <div class="modal-header"><div class="modal-title">Create New File ${adminMode?'<span class="owner-badge">OWNER</span>':''}</div><button class="modal-close" onclick="closeModal()">✕</button></div>
    <div class="modal-body">
      <div class="form-group"><label class="form-label">File Path</label><input type="text" id="new-file-path" class="form-input" placeholder="bot.py or folder/file.js"><div class="form-hint">Include extension. Eg: main.py, index.js, config.json</div></div>
      <div class="form-group"><label class="form-label">Initial Content (optional)</label><textarea id="new-file-content" class="form-textarea" placeholder="# Your code here..." rows="6"></textarea></div>
    </div>
    <div class="modal-footer"><button class="btn btn-secondary" onclick="closeModal()">Cancel</button><button class="btn btn-primary" onclick="createNewFile(${projectId}, ${adminMode})">Create</button></div>
  `;
  showModal(content);
}
async function createNewFile(projectId, adminMode=false) {
  const pathEl=document.getElementById('new-file-path');
  const contentEl=document.getElementById('new-file-content');
  const path=pathEl.value.trim();
  if (!path) { showToast('File path required','error'); return; }
  try {
    const url = adminMode ? `/api/admin/projects/${projectId}/files` : `/api/projects/${projectId}/files`;
    await apiRequest(url, {method:'POST', body: JSON.stringify({path, content: contentEl.value})});
    showToast('File created!','success');
    closeModal();
    renderFileManager(projectId, {adminMode});
  } catch(err) { showToast(`Failed to create file: ${err.message}`,'error'); }
}
function showRenameModal(projectId, oldPath, adminMode=false) {
  const content = `
    <div class="modal-header"><div class="modal-title">Rename File ${adminMode?'<span class="owner-badge">OWNER</span>':''}</div><button class="modal-close" onclick="closeModal()">✕</button></div>
    <div class="modal-body">
      <div class="form-group"><label class="form-label">Current Path</label><input type="text" class="form-input" value="${escapeHtml(oldPath)}" disabled></div>
      <div class="form-group"><label class="form-label">New Path *</label><input type="text" id="rename-new-path" class="form-input" placeholder="new_name.py" value="${escapeHtml(oldPath)}"><div class="form-hint">Enter new file name or path. Prevent ../ traversal.</div></div>
    </div>
    <div class="modal-footer"><button class="btn btn-secondary" onclick="closeModal()">Cancel</button><button class="btn btn-primary" onclick="renameFile(${projectId}, '${escapeHtml(oldPath)}', ${adminMode})">Rename</button></div>
  `;
  showModal(content);
}
async function renameFile(projectId, oldPath, adminMode=false) {
  const newPathEl=document.getElementById('rename-new-path');
  const newPath=newPathEl.value.trim();
  if (!newPath) { showToast('New path required','error'); return; }
  if (newPath===oldPath) { showToast('New path same as old','warning'); return; }
  try {
    const url = adminMode ? `/api/admin/projects/${projectId}/files/${encodeURIComponent(oldPath)}/rename` : `/api/projects/${projectId}/files/${encodeURIComponent(oldPath)}/rename`;
    await apiRequest(url, {method:'POST', body: JSON.stringify({new_path: newPath})});
    showToast(`Renamed to ${newPath}`,'success');
    closeModal();
    renderFileManager(projectId, {adminMode});
  } catch(err) { showToast(`Rename failed: ${err.message}`,'error'); }
}
function showUploadModal(projectId, adminMode=false) {
  const content = `
    <div class="modal-header"><div class="modal-title">Upload File ${adminMode?'<span class="owner-badge">OWNER</span>':''}</div><button class="modal-close" onclick="closeModal()">✕</button></div>
    <div class="modal-body">
      <div class="upload-zone" onclick="document.getElementById('modal-file-input').click()">
        <div class="upload-icon">📤</div><div class="upload-text">Tap to select file</div><div class="upload-hint">Max 25MB • .py, .js, .json, .txt, .zip</div>
        <input type="file" id="modal-file-input" style="display:none;" onchange="handleModalFileSelect(this.files, ${projectId})">
      </div>
      <div id="modal-upload-preview" class="hidden" style="margin-top:1rem;">
        <div class="file-item" style="background: var(--bg-tertiary); border-radius: var(--radius-md);"><div class="file-icon">📄</div><div class="file-info"><div class="file-name" id="modal-upload-name">file.py</div><div class="file-meta" id="modal-upload-size">0 KB</div></div></div>
      </div>
    </div>
    <div class="modal-footer"><button class="btn btn-secondary" onclick="closeModal()">Cancel</button><button class="btn btn-primary" id="modal-upload-btn" onclick="uploadFileToProject(${projectId}, ${adminMode})" disabled>Upload</button></div>
  `;
  showModal(content);
}
let modalUploadFile=null;
function handleModalFileSelect(files, projectId) {
  if (!files||files.length===0) return;
  modalUploadFile=files[0];
  const preview=document.getElementById('modal-upload-preview');
  if (preview) preview.classList.remove('hidden');
  document.getElementById('modal-upload-name').textContent=modalUploadFile.name;
  document.getElementById('modal-upload-size').textContent=formatFileSize(modalUploadFile.size);
  document.getElementById('modal-upload-btn').disabled=false;
}
async function uploadFileToProject(projectId, adminMode=false) {
  if (!modalUploadFile) return;
  const btn=document.getElementById('modal-upload-btn');
  btn.disabled=true; btn.textContent='⏳ Uploading...';
  try {
    const formData=new FormData();
    formData.append('file', modalUploadFile);
    formData.append('path', modalUploadFile.name);
    const url = adminMode ? `/api/admin/projects/${projectId}/files` : `/api/projects/${projectId}/files`;
    await apiRequest(url, {method:'POST', body: formData});
    showToast('File uploaded!','success');
    closeModal();
    renderFileManager(projectId, {adminMode});
  } catch(err) {
    showToast(`Upload failed: ${err.message}`,'error');
    btn.disabled=false; btn.textContent='Upload';
  }
}
function filterFiles(query) {
  const items=document.querySelectorAll('#file-list .file-item');
  const q=query.toLowerCase();
  items.forEach(item=>{
    const path=item.dataset.path.toLowerCase();
    item.style.display=path.includes(q)?'':'none';
  });
}
function filterUserCards(query) {
  const q=query.toLowerCase();
  const items=document.querySelectorAll('#user-list .user-card');
  items.forEach(item=>{
    const text=item.innerText.toLowerCase();
    item.style.display=text.includes(q)?'':'none';
  });
}
function filterProjectCards(query) {
  const q=query.toLowerCase();
  const items=document.querySelectorAll('#all-project-list .project-card');
  items.forEach(item=>{
    const text=item.innerText.toLowerCase();
    item.style.display=text.includes(q)?'':'none';
  });
}
async function loadFileManager(projectId, adminMode=false) { renderFileManager(projectId, {adminMode}); }
async function loadFileContent(projectId, path, adminMode=false) { renderEditor(projectId, path, {adminMode}); }

function showProjectMenu(projectId, adminMode=false) {
  const content = `
    <div class="modal-header"><div class="modal-title">Project Actions ${adminMode?'<span class="owner-badge">OWNER</span>':''}</div><button class="modal-close" onclick="closeModal()">✕</button></div>
    <div class="modal-body" style="display:flex; flex-direction:column; gap:0.5rem;">
      <button class="btn btn-secondary btn-block" onclick="closeModal(); ${adminMode?`navigateTo('owner-files', {id: ${projectId}})`:`navigateTo('files', {id: ${projectId}})`}">📁 File Manager</button>
      <button class="btn btn-secondary btn-block" onclick="closeModal(); ${adminMode?`navigateTo('owner-logs', {id: ${projectId}})`:`navigateTo('logs', {id: ${projectId}})`}">📋 View Logs</button>
      <button class="btn btn-secondary btn-block" onclick="closeModal(); startProject(${projectId}, ${adminMode})">▶️ Start Project</button>
      <button class="btn btn-secondary btn-block" onclick="closeModal(); stopProject(${projectId}, ${adminMode})">⏹ Stop Project</button>
      <button class="btn btn-secondary btn-block" onclick="closeModal(); restartProject(${projectId}, ${adminMode})">🔄 Restart</button>
      <button class="btn btn-danger btn-block" onclick="closeModal(); deleteProject(${projectId}, ${adminMode})">🗑️ Delete Project</button>
    </div>
  `;
  showModal(content);
}

async function logout() {
  showConfirmModal('Logout', 'Reset your session? You will need to reopen from Telegram.', async ()=>{
    try { await apiRequest('/api/auth/logout', {method:'POST'}); } catch {}
    showToast('Logged out','info');
    setTimeout(()=>location.reload(),1000);
  }, 'Logout', 'Cancel');
}

// Expose globally
window.navigateTo=navigateTo;
window.startProject=startProject;
window.stopProject=stopProject;
window.restartProject=restartProject;
window.deleteProject=deleteProject;
window.saveFile=saveFile;
window.deleteFile=deleteFile;
window.handleFileClick=handleFileClick;
window.showCreateFileModal=showCreateFileModal;
window.createNewFile=createNewFile;
window.showUploadModal=showUploadModal;
window.handleModalFileSelect=handleModalFileSelect;
window.uploadFileToProject=uploadFileToProject;
window.filterFiles=filterFiles;
window.filterUserCards=filterUserCards;
window.filterProjectCards=filterProjectCards;
window.loadFileManager=loadFileManager;
window.loadFileContent=loadFileContent;
window.showProjectMenu=showProjectMenu;
window.handleFileSelect=handleFileSelect;
window.clearUpload=clearUpload;
window.createProject=createProject;
window.closeModal=closeModal;
window.logout=logout;
window.showRenameModal=showRenameModal;
window.renameFile=renameFile;
window.renderOwnerUserProjects=renderOwnerUserProjects;

async function initApp() {
  const loadingScreen=document.getElementById('loading-screen');
  const mainApp=document.getElementById('main-app');
  const authError=document.getElementById('auth-error');
  tg.init();
  await new Promise(r=>setTimeout(r,600));
  const authed=await authenticate();
  loadingScreen.style.opacity='0';
  setTimeout(()=>{
    loadingScreen.classList.add('hidden');
    if (!authed) {
      authError.classList.remove('hidden');
    } else {
      mainApp.classList.remove('hidden');
      const user=state.user||{};
      const displayUsername=user.display_username || '@username_unavailable';
      const photoUrl=user.photo_url;
      const avatar=document.getElementById('user-avatar');
      const nameEl=document.getElementById('header-user-name');
      if (nameEl) nameEl.textContent=displayUsername;
      if (avatar) {
        if (photoUrl) {
          avatar.innerHTML=`<img src="${escapeHtml(photoUrl)}" style="width:100%;height:100%;object-fit:cover;border-radius:50%;" onerror="this.style.display='none'; this.parentElement.textContent='${(displayUsername.replace('@','')[0]||'U').toUpperCase()}'">`;
        } else {
          avatar.textContent=(displayUsername.replace('@','')[0]||'U').toUpperCase();
        }
      }
      // Show owner nav if owner
      const ownerNav=document.getElementById('nav-owner');
      if (ownerNav) {
        if (state.is_owner) ownerNav.classList.remove('hidden');
        else ownerNav.classList.add('hidden');
      }
      navigateTo('home');
      window.addEventListener('offline', ()=>showToast('You are offline','warning'));
      window.addEventListener('online', ()=>showToast('Back online!','success'));
    }
  },300);
}

if (document.readyState==='loading') document.addEventListener('DOMContentLoaded', initApp);
else initApp();
