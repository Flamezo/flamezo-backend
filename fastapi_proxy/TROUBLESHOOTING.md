# Troubleshooting FastAPI Proxy

## Issue: Gateway Response Instead of FastAPI

If you see:
```json
{"detail":"Not found","gateway":"flamezo_backend-backend"}
```

This means a gateway/proxy (Nginx, etc.) is intercepting the request.

## Commands to Run on Server

### 1. Check Service Logs
```bash
journalctl -u fastapi-proxy -n 100 --no-pager
```

Look for:
- Startup errors
- Import errors
- Configuration errors
- Connection errors

### 2. Check if App Started Successfully
```bash
journalctl -u fastapi-proxy --since "5 minutes ago" | grep -i "error\|exception\|traceback"
```

### 3. Test Direct Connection (Bypass Gateway)
```bash
# Test directly on localhost
curl http://127.0.0.1:8001/health

# Test with verbose output
curl -v http://127.0.0.1:8001/health
```

### 4. Check if Port is Listening
```bash
netstat -tlnp | grep 8001
# or
ss -tlnp | grep 8001
```

Should show:
```
tcp  0  0  0.0.0.0:8001  0.0.0.0:*  LISTEN  693146/python3
```

### 5. Check Process is Running
```bash
ps aux | grep gunicorn | grep -v grep
```

### 6. Test Manual Start (Stop Service First)
```bash
# Stop service
systemctl stop fastapi-proxy

# Start manually to see errors
cd /home/frappe/frappe-bench/apps/flamezo_backend/fastapi_proxy
source venv/bin/activate
gunicorn -w 1 -k uvicorn.workers.UvicornWorker main:app --bind 127.0.0.1:8001 --log-level debug
```

Press `Ctrl+C` to stop, then restart service.

### 7. Check Configuration
```bash
cd /home/frappe/frappe-bench/apps/flamezo_backend/fastapi_proxy
source venv/bin/activate
python -c "from config import settings; print('ERPNext URL:', settings.erpnext_base_url)"
```

### 8. Check .env File
```bash
cd /home/frappe/frappe-bench/apps/flamezo_backend/fastapi_proxy
cat .env | grep -v SECRET | grep -v KEY
```

## Common Issues

### Issue: App Not Starting
**Check logs for**:
- Import errors
- Configuration errors
- Missing dependencies

**Solution**:
```bash
journalctl -u fastapi-proxy -n 50
```

### Issue: Port Already in Use
**Check**:
```bash
lsof -i :8001
```

**Solution**: Kill the process or change port in .env

### Issue: Configuration Error
**Test**:
```bash
cd /home/frappe/frappe-bench/apps/flamezo_backend/fastapi_proxy
source venv/bin/activate
python -c "from config import settings; print('OK')"
```

### Issue: Gateway Intercepting
**Check Nginx config** (if using):
```bash
sudo nginx -t
sudo cat /etc/nginx/sites-enabled/* | grep -A 10 "8001\|fastapi"
```

## Quick Diagnostic Script

Run this on server:

```bash
echo "=== Service Status ==="
systemctl status fastapi-proxy --no-pager -l

echo -e "\n=== Recent Logs ==="
journalctl -u fastapi-proxy -n 20 --no-pager

echo -e "\n=== Port Check ==="
netstat -tlnp | grep 8001

echo -e "\n=== Process Check ==="
ps aux | grep gunicorn | grep -v grep

echo -e "\n=== Direct Test ==="
curl -v http://127.0.0.1:8001/health 2>&1 | head -20
```
