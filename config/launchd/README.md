# LaunchAgent for NewPlatform backend (macOS)

Keeps the backend (uvicorn) running so you don’t have to start it manually.

## Install

1. If your repo is not at `/Users/sanjeev/Sites/NewPlatform`, edit the plist and set `ProgramArguments`[0] to your backend venv uvicorn path and `WorkingDirectory` to your backend directory.

2. Copy the plist and load:

   ```bash
   cp com.newplatform.backend.plist ~/Library/LaunchAgents/
   ```

   ```bash
   launchctl load ~/Library/LaunchAgents/com.newplatform.backend.plist
   ```

3. Check:

   ```bash
   launchctl list | grep newplatform
   curl -s http://127.0.0.1:8889/health
   ```

## Unload (stop)

```bash
launchctl unload ~/Library/LaunchAgents/com.newplatform.backend.plist
```

## Logs

- stdout: `/tmp/newplatform-backend.log`
- stderr: `/tmp/newplatform-backend.err.log`
