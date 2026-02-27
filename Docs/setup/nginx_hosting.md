# Host the app with Nginx (always on, no manual start)

This setup lets you use **http://new.packt.localhost:8004/** without running `npm run dev` or starting the backend by hand. Nginx serves the built frontend and proxies the API to the backend.

---

## 1. Why the app “stops”

- **Frontend:** Running `npm run dev` (Vite) in a terminal stops when you close the terminal or stop the process.
- **Backend:** Running `uvicorn` in a terminal stops the same way.

So the app is “stopped” whenever those processes aren’t running. Nginx + a persistent backend process fix that.

---

## 2. What this setup does

| Component    | Role |
|-------------|------|
| **Nginx**   | Listens on port 8004 for `new.packt.localhost`, serves the built frontend (static files) and proxies `/api/` and `/health` to the backend. |
| **Backend** | Runs as a long-lived process (e.g. launchd on macOS) on port 8889. Nginx sends API requests to it. |
| **Frontend**| Built once (`npm run build`). Nginx serves the `frontend/dist` folder; no Node/Vite needed at runtime. |

---

## 3. Prerequisites

- **Nginx** installed (e.g. `brew install nginx` on macOS).
- **Hosts:** `new.packt.localhost` must resolve to `127.0.0.1`. Add to `/etc/hosts` if needed:
  ```text
  127.0.0.1   new.packt.localhost
  ```

---

## 4. One-time setup

### 4.1 Build the frontend (production)

From the repo root:

```bash
cd frontend
# .env.production sets VITE_API_BASE= so API calls go to same origin (nginx will proxy)
npm run build
```

This creates `frontend/dist`. Nginx will use this as `root`.

### 4.2 Install the Nginx config

- Config file: **`config/nginx/new.packt.localhost.conf`**
- It uses `root /Users/sanjeev/Sites/NewPlatform/frontend/dist`. If your repo path is different, edit the `root` line in the config.

**macOS (Homebrew nginx):**

```bash
# Create servers dir if it doesn't exist
mkdir -p /opt/homebrew/etc/nginx/servers   # Apple Silicon
# or
mkdir -p /usr/local/etc/nginx/servers      # Intel

# Copy (adjust path to your repo)
cp /Users/sanjeev/Sites/NewPlatform/config/nginx/new.packt.localhost.conf /opt/homebrew/etc/nginx/servers/

# Include in main nginx.conf (if not already):
# In http { } add: include servers/*.conf;
# Then reload
nginx -t && nginx -s reload
```

**Linux (e.g. Ubuntu):**

```bash
sudo cp /path/to/NewPlatform/config/nginx/new.packt.localhost.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/new.packt.localhost.conf /etc/nginx/sites-enabled/
# Edit root path in the config if needed, then:
sudo nginx -t && sudo systemctl reload nginx
```

### 4.3 Run the backend so it stays up

The backend must listen on **127.0.0.1:8889**. Two options:

**Option A – launchd (macOS, recommended)**

Create **`~/Library/LaunchAgents/com.newplatform.backend.plist`**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.newplatform.backend</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/sanjeev/Sites/NewPlatform/backend/.venv/bin/uvicorn</string>
    <string>app.main:app</string>
    <string>--host</string>
    <string>127.0.0.1</string>
    <string>--port</string>
    <string>8889</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/Users/sanjeev/Sites/NewPlatform/backend</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/tmp/newplatform-backend.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/newplatform-backend.err.log</string>
</dict>
</plist>
```

Load and start:

```bash
launchctl load ~/Library/LaunchAgents/com.newplatform.backend.plist
# Check
launchctl list | grep newplatform
curl -s http://127.0.0.1:8889/health
```

**Option B – Run in background (simpler, but stops on reboot)**

```bash
cd /Users/sanjeev/Sites/NewPlatform/backend
./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8889 &
```

---

## 5. Daily use

1. **Nginx** – Usually already running (started at boot or by your OS). If not:
   - macOS: `brew services start nginx`
   - Linux: `sudo systemctl start nginx`
2. **Backend** – If you use launchd, it starts at login and restarts if it crashes. No need to run uvicorn by hand.
3. Open **http://new.packt.localhost:8004/** in the browser.

No need to run `npm run dev` or start the backend manually each time.

---

## 6. After code changes

- **Frontend:** Run `cd frontend && npm run build` and reload nginx if you want (`nginx -s reload`). No need to restart the backend for frontend-only changes.
- **Backend:** Restart the backend process (e.g. `launchctl kickstart -k gui/$(id -u)/com.newplatform.backend` or restart the terminal process if you used Option B).

---

## 7. Troubleshooting

| Issue | Check |
|-------|--------|
| “Connection refused” at 8004 | Nginx running? `nginx -t` and `brew services list` or `systemctl status nginx`. |
| Page loads but API fails | Backend running? `curl http://127.0.0.1:8889/health`. Start backend (launchd or uvicorn). |
| 502 Bad Gateway | Nginx can’t reach backend. Confirm uvicorn is listening on 127.0.0.1:8889. |
| Wrong path / 404 | `root` in nginx config must point to `frontend/dist` (absolute path). Re-run `npm run build`. |
