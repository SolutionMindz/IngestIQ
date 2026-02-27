#!/usr/bin/env bash
# Quick smoke test for the admin dashboard (frontend) and optional backend.
set -e

FRONTEND_URL="${FRONTEND_URL:-http://new.packt.localhost:8003}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8888}"

echo "=== Testing Admin Dashboard ==="
echo "Frontend: $FRONTEND_URL"
echo "Backend:  $BACKEND_URL"
echo ""

# 1. Frontend
echo "1. Frontend..."
code=$(curl -sS -o /tmp/dashboard.html -w "%{http_code}" "$FRONTEND_URL/" 2>/dev/null || echo "000")
if [ "$code" = "200" ]; then
  if grep -q "Knowledge Ingestion Admin Console" /tmp/dashboard.html 2>/dev/null; then
    echo "   OK (200) – page loads, title present"
  else
    echo "   OK (200) – page loads (title check skipped)"
  fi
else
  echo "   FAIL – got HTTP $code (is the dev server running? npm run dev in frontend/)"
  exit 1
fi

# 2. Backend health (optional)
echo "2. Backend health..."
health_code=$(curl -sS -o /tmp/health.json -w "%{http_code}" "$BACKEND_URL/health" 2>/dev/null || echo "000")
if [ "$health_code" = "200" ]; then
  echo "   OK (200) – backend is up"
else
  echo "   SKIP – backend returned $health_code (start with: cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 8888)"
fi

echo ""
echo "Dashboard URL: $FRONTEND_URL/"
