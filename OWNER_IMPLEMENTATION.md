# SNUKED HOSTER - Owner/Admin Global Access Implementation

## Summary
Implemented OWNER/ADMIN global access system preserving all existing functionality. Owner can manage every user's hosted project from Telegram Mini App.

## Backend Changes

### 1. Database (`backend/database/db.py`)
- Added `photo_url TEXT DEFAULT ''` column to `telegram_users` with safe migration `_migrate()`
- `upsert_telegram_user()` now handles `photo_url`
- New methods:
  - `list_all_users_with_stats()` - returns users with project counts, only username+photo internally, first_name stored but not displayed per spec
  - `list_all_projects()` - all projects
  - `count_all_projects()`
  - `get_global_stats()` - total users, projects, running, stopped
  - `list_projects_by_user(user_id)` wrapper

### 2. Telegram Auth (`backend/services/telegram_auth.py`)
- Extracts `photo_url` from validated initData user object
- Added `is_owner_user(user_id, owner_id, admin_ids)` helper - server-side owner check, never trust client

### 3. Auth API (`backend/api/auth.py`)
- `_check_owner()` uses server-side OWNER_USER_ID + admin_user_ids, never client flag
- Session now includes `is_owner` + `tg_photo_url`
- `/api/auth/telegram` stores photo_url
- `/api/auth/me` and `/api/me` return only:
  - `username`
  - `display_username` (@username or @username_unavailable fallback)
  - `photo_url`
  - `is_owner`
  - `stats` (for /api/me)
  - No first_name, last_name, full name exposed per requirements
- Added `require_owner()` helper - raises 403 if not owner

### 4. Projects API (`backend/api/projects.py`)
- `_owned_project()` allows owner bypass: if `session.is_owner` return any project, else strict owner_id match (IDOR protection)
- Added rename endpoint `POST /api/projects/{id}/files/{path}/rename`
- Updated `/api/me` to return only @username+photo+is_owner
- `/api/activity` returns global activity for owner, own only for normal users

### 5. New Admin API (`backend/api/admin.py`)
Owner-only routes, all protected by `require_owner()` server-side:
- `GET /api/admin/stats` - Total Users, Total Projects, Running, Stopped (live count from ProcessManager)
- `GET /api/admin/users` - List all users, returns only photo+username+counts (no first_name/last_name)
- `GET /api/admin/users/{user_id}/projects` - User's projects
- `GET /api/admin/projects` - All projects with owner username
- `GET /api/admin/projects/{id}` - Single project with owner info
- `DELETE /api/admin/projects/{id}` - Delete any project
- `POST /api/admin/projects/{id}/start|stop|restart` - Controls
- `GET /api/admin/projects/{id}/files` - List files
- `GET /api/admin/projects/{id}/files/{path}` - Read file with language detection
- `PUT /api/admin/projects/{id}/files/{path}` - Write file
- `POST /api/admin/projects/{id}/files` - Create/upload file (JSON or multipart)
- `DELETE /api/admin/projects/{id}/files/{path}` - Delete file
- `POST /api/admin/projects/{id}/files/{path}/rename` - Rename file with destination exists check
- `GET /api/admin/projects/{id}/logs` - View logs
- `DELETE /api/admin/projects/{id}/logs` - Clear logs

### 6. Process Manager (`backend/process/manager.py`)
- Added `rename_file(old_path, new_path)` with:
  - Safe path validation (prevents ../ traversal)
  - Destination exists check (ValueError)
  - Source not found raises FileNotFoundError

### 7. Terminal WebSocket (`backend/api/terminal.py`)
- Updated to allow owner to view any project's logs via owner check

### 8. App Registration (`backend/app.py`)
- Registered AdminAPI router

## Frontend Changes

### 1. `frontend/index.html`
- Added OWNER bottom nav item with `id="nav-owner"` hidden by default (`class="hidden"`)
- Only visible when `is_owner` true

### 2. `frontend/css/styles.css`
- Added owner-specific styles:
  - `.owner-badge` gradient badge
  - `.owner-panel-header` with orange-red gradient
  - `.user-card` - only photo + @username + counts, hover effects
  - `.profile-hero` - centered photo + @username only
  - `.profile-avatar-large` - 96px avatar
  - `.file-rename-input`

### 3. `frontend/js/app.js` (Complete Rewrite - 1583 lines)
**Security & Auth:**
- `apiRequest()` includes `X-Telegram-Init-Data` header via `tg.getAuthHeaders()`
- `authenticate()` validates initData server-side, then `/api/me`
- `state.is_owner` from server response, never client flag
- Owner nav visibility controlled by `is_owner`

**Profile Page (Settings):**
- Shows ONLY:
  - Telegram profile picture (or initial fallback)
  - @username (fallback @username_unavailable)
  - Projects X Running X Stopped counts
- NO first_name, last_name, full name, numeric ID per spec
- Header also shows @username + photo only

**Owner Panel (`owner`):**
- Stats cards: Total Users, Total Projects, Running, Stopped
- Buttons: View Users, View All Projects
- Recent users list (photo+@username only)
- Security note about server-side auth

**Users List (`owner-users`):**
- Cards show ONLY photo + @username + project count
- Search filter
- Click user -> User Projects

**User Projects (`owner-user-projects`):**
- Header with user photo + @username
- Lists user's projects with owner-aware controls

**All Projects (`owner-all-projects`):**
- Global list with owner @username badge
- Search filter

**Project Detail (admin mode):**
- Banner "Owner Management Mode" + owner photo + @username
- Same capabilities as project owner: view files, editor, logs, start/stop/restart/delete
- Uses admin APIs when `adminMode=true`

**File Manager (admin aware):**
- Uses `/api/admin/projects/{id}/files` when admin
- Shows filename, language, file size
- Rename button + edit + delete
- Search filter
- Create file modal, upload modal

**Editor (admin aware):**
- Shows filename, language, file size info
- Language detection from extension
- Save via admin or normal endpoint
- Ctrl+S shortcut, Tab handling
- Owner badge when in admin mode

**Logs (admin aware):**
- Fetches via admin endpoint when owner viewing other user's project
- Auto-scroll toggle, copy, download, clear

**Actions:**
- `startProject(id, adminMode)`, `stopProject`, `restartProject`, `deleteProject` - choose admin or normal endpoint
- `saveFile`, `deleteFile`, `renameFile`, `createNewFile`, `uploadFileToProject` - admin aware
- Path traversal blocked server-side, frontend passes paths through authenticated APIs only

**UI Identity:**
- Premium dark theme preserved
- Mobile-first Telegram Mini App
- Cards, transitions, bottom nav
- FAB only visible on home/projects
- Back button handling for owner flows

## Security Measures

1. **Server-side Owner Check:** Every admin endpoint uses `require_owner()` which validates session via `is_owner_user()` using `OWNER_USER_ID` config, never client flag
2. **Telegram Auth:** Validates initData via HMAC-SHA256 with BOT_TOKEN server-side, DO NOT trust initDataUnsafe
3. **IDOR Protection:** `_owned_project()` checks owner_id match, owner bypass only if `is_owner` true server-side; modified IDs return 404
4. **Path Traversal:** `_safe_path()` in ProcessManager prevents `../` escapes, admin file APIs use same validation
5. **File Operations:** All via authenticated backend APIs, no direct frontend FS access
6. **No Sensitive Exposure:** BOT_TOKEN, SECRET_KEY never exposed to frontend; telegram_users first_name/last_name stored but not exposed in admin users API (only username+photo)
7. **Numeric ID:** Stored internally for API but UI displays only @username+photo per spec

## Testing Results

### Backend Unit Tests
- ✓ photo_url column migration
- ✓ Owner check (owner, admin, normal user)
- ✓ User creation with photo_url
- ✓ Project creation and ownership filtering
- ✓ list_all_users_with_stats returns only username+photo concept
- ✓ Global stats
- ✓ Path traversal blocked
- ✓ File write/read/rename with dest exists check
- ✓ Owner bypass logic
- ✓ IDOR protection - modified IDs fail

### Admin API Integration Tests (FastAPI TestClient)
- ✓ Owner can access /api/admin/stats (200)
- ✓ Normal user blocked from /api/admin/stats (403)
- ✓ Users list only exposes username+photo, no first_name/last_name
- ✓ Owner can access any project
- ✓ User can access own project
- ✓ User cannot access other's project via IDOR (404)
- ✓ Owner can read file
- ✓ Owner can edit file
- ✓ Owner can rename file
- ✓ Path traversal blocked (400/404)
- ✓ Owner can start/stop project

### Frontend Verification
- ✓ Owner nav hidden for normal users, visible for owner
- ✓ Profile shows only photo + @username + counts, no first/last name, no ID
- ✓ Users list cards show only photo + @username + project count
- ✓ Owner panel stats cards display correctly
- ✓ User→Projects→Files/Editor/Logs/Controls flow works
- ✓ File editor shows filename/language/file size
- ✓ Rename functionality works
- ✓ No BOT_TOKEN or SECRET_KEY in frontend

## Environment Variables (Preserved)
- OWNER_USER_ID - source of truth for owner
- BOT_TOKEN - for Telegram auth validation
- SECRET_KEY - session signing
- MINI_APP_URL - Mini App URL
- DATABASE_PATH - DB path
- PROJECTS_DIR - projects storage
- CORS_ORIGINS - CORS config

## Railway/Linux Compatibility
- All paths use Pathlib, safe migrations
- No hardcoded absolute paths
- Resource limits via _preexec_limits (Linux only, best-effort)
- .venv per project, requirements.txt auto-install

## Remaining Notes
- Frontend uses `tg.getAuthHeaders()` to send `X-Telegram-Init-Data` and `Authorization: tma <initData>` on every request
- Backend validates initData on every request via `require_session()` and `require_owner()`
- Owner identification: `is_owner_user(user_id, owner_user_id, admin_user_ids)` server-side
- Display logic: `@username` if exists else `@username_unavailable`
