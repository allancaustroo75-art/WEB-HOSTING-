# SNUKED HOSTER — Telegram Mini App Hosting Platform

> Premium bot hosting directly inside Telegram. No external website needed.

Upload your Python or Node.js bots via Telegram and manage them through a modern premium dashboard that opens **inside Telegram** as a Mini App (Web App).

```
Telegram Bot ──> 🚀 Open Hosting Panel ──> Telegram Mini App
                                          │
                                          ├──> Backend API (FastAPI)
                                          │         │
                                          │         ├──> Process Manager (isolated venv per project)
                                          │         │         └──> Your Bot (subprocess)
                                          │         │
                                          │         └──> SQLite (metadata, logs, ownership)
                                          │
                                          └──> File Manager / Code Editor / Live Logs
```

## ✨ Features

### 🤖 Telegram Integration
- **Mini App button** — `🚀 Open Hosting Panel` opens premium dashboard inside Telegram
- **Secure auth** — Validates Telegram WebApp `initData` using official HMAC-SHA256 method
- **Never trusts frontend** — User ID verified server-side, session signed with `SECRET_KEY`
- **Bot commands** — `/start`, `/panel`, `/myfiles`, `/status`, `/dashboard` + admin commands

### 📦 Hosting
- **Python & Node.js** support (auto-detects runtime)
- **Per-project isolated venv** — dependencies don't clash
- **Auto-install** — `requirements.txt` and `package.json` handled automatically
- **Process management** — Start / Stop / Restart with resource limits (CPU, Memory)
- **Live logs** — Real-time stdout/stderr tail, clear, copy, download

### 💎 Premium Mini App UI
- **Dark theme** — Black / charcoal / silver, subtle gradients, rounded corners
- **Telegram-native** — Uses `Telegram.WebApp` theme variables, adapts to Telegram theme
- **Mobile-first** — Optimized for Android WebView, responsive on desktop Telegram
- **Pages:**
  - **Home** — Welcome, stats (total/running/stopped/memory), recent activity, recent projects
  - **Projects** — List with status, runtime, actions
  - **Project Detail** — Info, resource usage, quick actions, file preview
  - **File Manager** — Browse, upload, create, rename, delete, search
  - **Code Editor** — Mobile-friendly, syntax-aware, save, Ctrl+S, tab handling
  - **Console/Logs** — Live auto-scroll, clear, copy, download
  - **Create Project** — Name, runtime selection, ZIP upload with drag & drop
  - **Settings** — Telegram profile, stats, preferences, backend status
- **UX** — Bottom nav (Home | Projects | Activity | Settings), FAB create button, toasts, skeletons, confirm modals, empty states, offline handling

## 🔐 Security — IMPORTANT

- **Never trust `initDataUnsafe`** — We only use `initData` (raw query string) and validate its hash server-side
- **Validation:** `secret_key = HMAC-SHA256("WebAppData", BOT_TOKEN)`, `hash = HMAC-SHA256(secret_key, data_check_string)` — compare with received hash
- **Session:** After validation, we create `HttpOnly`, `SameSite=Lax`, HMAC-signed cookie (`SECRET_KEY`) — no BOT_TOKEN in frontend
- **Ownership:** Projects are bound to verified Telegram user ID; users can only access own projects
- **Secrets:** All secrets server-side in env vars, never in frontend JS
- **CORS:** Configure `CORS_ORIGINS` to your exact Mini App URL(s), never `*` with credentials in production
- **Uploads:** Extension & size checks, path traversal guards, sanitized filenames

## 🚀 Quick Start (Local)

```bash
cp .env.example .env
# Edit .env: set BOT_TOKEN, OWNER_USER_ID, SECRET_KEY, MINI_APP_URL=http://localhost:8000

./start.sh
```

Open `http://localhost:8000` — it serves the Mini App. For Telegram testing, you need HTTPS (use ngrok or Railway).

Message your bot `/start` on Telegram — you should see `🚀 Open Hosting Panel` button.

## 🌐 Deployment (Railway / Linux)

### Railway

1. **Create project** from GitHub repo
2. **Set env vars** in Railway dashboard:

```
BOT_TOKEN=123456:AAH...
OWNER_USER_ID=111111111
ADMIN_USER_IDS=111111111,222222222  # optional, leave empty for open hosting
SECRET_KEY=long-random-string-at-least-32-chars
MINI_APP_URL=https://your-app.up.railway.app
DASHBOARD_BASE_URL=https://your-app.up.railway.app
DATABASE_PATH=./data/bothost.db
PROJECTS_DIR=./projects
CORS_ORIGINS=https://your-app.up.railway.app,https://web.telegram.org
PORT=8000
HOST=0.0.0.0
COOKIE_SECURE=true
```

3. **Deploy** — Railway will run `start.sh` (or set start command: `bash start.sh`)
4. **Set Mini App URL in BotFather:**
   - Open @BotFather → `/mybots` → your bot → Bot Settings → Menu Button → Set menu button URL to `https://your-app.up.railway.app`
   - Or the bot will send inline WebApp button automatically using `MINI_APP_URL`

### Linux (systemd)

```bash
git clone <repo>
cd project
cp .env.example .env
nano .env

./start.sh
# Or with systemd:
# Create /etc/systemd/system/bothost.service with ExecStart=/path/to/start.sh
```

Backend listens on `PORT` env var (default 8000).

## 🤖 BotFather Setup for Mini App

1. Talk to @BotFather:
   ```
   /mybots → Select bot → Bot Settings → Menu Button
   → Edit menu button URL → https://your-app.up.railway.app
   ```

2. Optional: Set commands:
   ```
   /setcommands → Select bot →
   start - Welcome & open panel
   panel - Open hosting panel
   myfiles - List projects
   status - Show status
   dashboard - Legacy dashboard link
   ```

3. Ensure your bot has a **short description** and **description** that mentions Mini App hosting.

## 🔧 Environment Variables

| Var | Required | Description | Example |
|-----|----------|-------------|---------|
| `BOT_TOKEN` | ✅ | Telegram Bot Token from BotFather | `123456:AAH...` |
| `OWNER_USER_ID` | ✅ | Owner Telegram ID (can add/remove admins) | `111111111` |
| `ADMIN_USER_IDS` | ❌ | Comma-separated allowed user IDs. Empty = open to all Telegram users via Mini App | `111111111,222222222` |
| `SECRET_KEY` | ✅ | Random string for signing sessions | `openssl rand -hex 32` |
| `MINI_APP_URL` | ✅ | Public HTTPS URL of frontend (for WebApp button) | `https://app.example.com` |
| `DASHBOARD_BASE_URL` | ❌ | Legacy fallback, defaults to MINI_APP_URL | `https://app.example.com` |
| `DATABASE_PATH` | ❌ | SQLite path | `./data/bothost.db` |
| `PROJECTS_DIR` | ❌ | Where projects stored | `./projects` |
| `CORS_ORIGINS` | ❌ | Allowed origins, comma-separated | `https://app.example.com` |
| `MAX_PROJECTS_PER_USER` | ❌ | Limit per user | `10` |
| `MAX_UPLOAD_BYTES` | ❌ | Max upload size | `26214400` |
| `COOKIE_SECURE` | ❌ | Set true if HTTPS | `true` |
| `PORT` | ❌ | Server port | `8000` |

See `.env.example` for all.

## 📡 API Endpoints

All require Telegram auth (initData header or session cookie):

```
GET    /api/me
GET    /api/projects
POST   /api/projects                    # multipart: name, runtime, file
GET    /api/projects/{id}
POST   /api/projects/{id}/start
POST   /api/projects/{id}/stop
POST   /api/projects/{id}/restart
DELETE /api/projects/{id}
GET    /api/projects/{id}/files         # detailed list
POST   /api/projects/{id}/files         # upload or create
GET    /api/projects/{id}/files/{path}
PUT    /api/projects/{id}/files/{path}
DELETE /api/projects/{id}/files/{path}
GET    /api/projects/{id}/logs?lines=200
DELETE /api/projects/{id}/logs          # clear
GET    /api/activity
POST   /api/auth/telegram               # body: {initData}
GET    /api/auth/me
POST   /api/auth/token-login            # legacy
WS     /ws/projects/{id}/logs?initData=...
GET    /health
```

### Auth Headers

Mini App sends automatically:

```
X-Telegram-Init-Data: <raw initData query string>
Authorization: tma <initData>
Cookie: bh_session=<signed session>
```

Backend validates initData on every request (or uses session cookie).

## 📁 Project Structure

```
project/
├── backend/
│   ├── app.py                 # FastAPI app, CORS, static frontend serving
│   ├── config.py              # Env settings (MINI_APP_URL, etc)
│   ├── __main__.py
│   ├── api/
│   │   ├── auth.py            # Telegram initData validation + session
│   │   ├── projects.py        # All hosting endpoints
│   │   └── terminal.py        # WebSocket logs
│   ├── bot/
│   │   ├── handlers.py        # Bot with Mini App button 🚀 Open Hosting Panel
│   │   └── runner.py
│   ├── database/db.py         # SQLite + migrations (runtime, telegram_users)
│   ├── process/manager.py     # venv + subprocess + resource limits
│   └── services/
│       ├── telegram_auth.py   # Official Telegram WebApp validation
│       ├── security.py        # HMAC session signing
│       └── naming.py          # Sanitization
├── frontend/                  # Telegram Mini App (static)
│   ├── index.html             # SPA entry, Telegram WebApp JS API
│   ├── css/styles.css         # Premium dark theme, Telegram variables
│   └── js/
│       ├── telegram.js        # WebApp helper (theme, haptics, auth)
│       └── app.js             # SPA logic (8 pages, API, toasts, modals)
├── data/                      # SQLite DB (gitignored)
├── projects/                  # User projects (gitignored)
├── .env.example
├── start.sh
├── README.md
└── backend/requirements.txt
```

## 🎨 Frontend Details

- **Single Page App** — No build step, vanilla JS for Railway compatibility
- **Telegram WebApp API Used:**
  - `Telegram.WebApp.ready()` / `expand()`
  - `initData` (for auth, never `initDataUnsafe` for security)
  - `themeParams`, `colorScheme`
  - `MainButton`, `BackButton`
  - `HapticFeedback` (light/medium/success/error)
  - `showAlert`, `showConfirm`
- **Mobile-first:** Tested for Android WebView, iOS, Desktop Telegram
- **No external deps:** Only Telegram WebApp JS + Google Fonts (Inter, JetBrains Mono) — works offline after load

## 🧪 Testing Locally Without Telegram

The backend allows dev mode on `localhost` without Telegram initData (mock user). But for full Mini App test:

1. Use **ngrok**: `ngrok http 8000` → set `MINI_APP_URL` to ngrok HTTPS URL → set in BotFather
2. Open bot in Telegram → `/start` → tap `🚀 Open Hosting Panel`

## ⚠️ Security Notes

- Uploaded code runs as subprocess with your server permissions, limited only by CPU/memory rlimits (Linux). **No full sandbox** — do not open to untrusted users without Docker/gVisor.
- Always set `COOKIE_SECURE=true` and HTTPS in production.
- Set `CORS_ORIGINS` to exact Mini App origin, never `*` with credentials.
- Rotate `SECRET_KEY` and `BOT_TOKEN` regularly.
- Keep `PROJECTS_DIR` outside web root.

## 📜 License

MIT — Original implementation, no branding reuse.

## 🙏 Credits

Built for Telegram Mini Apps — premium hosting panel that lives inside Telegram.

- Backend: FastAPI + python-telegram-bot
- Frontend: Vanilla JS + Telegram WebApp SDK
- Hosting: Railway / Linux compatible
