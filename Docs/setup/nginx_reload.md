# Nginx reload (macOS Homebrew)

If nginx was started with `sudo` (or by the system), you must use `sudo` to reload it:

```bash
sudo nginx -t && sudo nginx -s reload
```

- `nginx -t` — test config (sudo often needed to read all included files).
- `nginx -s reload` — send reload to the master process; if that process is owned by root, only root can signal it.

**If you prefer not to use sudo for reload:** run nginx as your user so you can reload without sudo:

```bash
# Stop the root-owned nginx first (if running)
sudo nginx -s stop

# Start as your user (from your shell)
nginx
# Then reload with:
nginx -s reload
```

Note: When nginx runs as your user, it may not listen on privileged ports (e.g. 80) unless you grant the binary extra capabilities.
