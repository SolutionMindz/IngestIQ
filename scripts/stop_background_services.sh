#!/bin/bash
# Stop irrelevant background services to free memory. Run with sudo for nginx.
set -e
echo "Stopping nginx (requires sudo)..."
sudo brew services stop nginx 2>/dev/null || true
sudo pkill -f "nginx: master" 2>/dev/null || true
echo "Stopping other uvicorn backends (not IngestIQ on 8889)..."
pkill -f "uvicorn core.main" 2>/dev/null || true
echo "Done. MySQL and PostgreSQL were not stopped (uncomment below if needed)."
# sudo launchctl unload /Library/LaunchDaemons/com.mysql.mysqld.plist 2>/dev/null || true
# brew services stop postgresql@17  # only if you don't need DB for extraction
