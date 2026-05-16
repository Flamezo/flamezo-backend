# Server Commands - FastAPI Proxy

## ✅ Service Status

Your service is **ACTIVE and RUNNING**! 

Status shows:
```
Active: active (running)
Main PID: 693146 (gunicorn)
```

## 🔍 Check Service Health

### 1. Check Service Status
```bash
systemctl status fastapi-proxy
```

### 2. Check Service Logs
```bash
journalctl -u fastapi-proxy -f
# Press Ctrl+C to exit
```

### 3. Check Last 50 Lines of Logs
```bash
journalctl -u fastapi-proxy -n 50 --no-pager
```

### 4. Test Health Endpoint
```bash
curl http://localhost:8001/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "flamezo_backend-fastapi-proxy",
  "version": "1.0.0"
}
```

### 5. Test Root Endpoint
```bash
curl http://localhost:8001/
```

## 🛠️ Service Management Commands

### Start Service
```bash
systemctl start fastapi-proxy
```

### Stop Service
```bash
systemctl stop fastapi-proxy
```

### Restart Service
```bash
systemctl restart fastapi-proxy
```

### Enable Service (Start on Boot)
```bash
systemctl enable fastapi-proxy
```

### Disable Service
```bash
systemctl disable fastapi-proxy
```

### View Real-time Logs
```bash
journalctl -u fastapi-proxy -f
```

## 🐛 Troubleshooting

### If Service Fails to Start

1. **Check Logs**:
```bash
journalctl -u fastapi-proxy -n 100 --no-pager
```

2. **Check Configuration**:
```bash
cd /home/frappe/frappe-bench/apps/flamezo_backend/fastapi_proxy
source venv/bin/activate
python -c "from config import settings; print('Config OK')"
```

3. **Check .env File**:
```bash
ls -la /home/frappe/frappe-bench/apps/flamezo_backend/fastapi_proxy/.env
cat /home/frappe/frappe-bench/apps/flamezo_backend/fastapi_proxy/.env | grep -v SECRET
```

4. **Test Manual Start**:
```bash
cd /home/frappe/frappe-bench/apps/flamezo_backend/fastapi_proxy
source venv/bin/activate
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:8001
```

### If Health Endpoint Doesn't Respond

1. **Check if Port is Listening**:
```bash
netstat -tlnp | grep 8001
# or
ss -tlnp | grep 8001
```

2. **Check Firewall**:
```bash
sudo ufw status
```

3. **Check if Process is Running**:
```bash
ps aux | grep gunicorn
```

## 📊 Monitor Service

### View Resource Usage
```bash
systemctl status fastapi-proxy
# Shows CPU and Memory usage
```

### View All Logs Since Boot
```bash
journalctl -u fastapi-proxy --since "1 hour ago"
```

### View Logs for Specific Date
```bash
journalctl -u fastapi-proxy --since "2026-01-13 17:00:00"
```

## ✅ Verification Checklist

- [ ] Service is active: `systemctl status fastapi-proxy`
- [ ] Health endpoint responds: `curl http://localhost:8001/health`
- [ ] Port is listening: `netstat -tlnp | grep 8001`
- [ ] No errors in logs: `journalctl -u fastapi-proxy -n 50`
- [ ] Service enabled on boot: `systemctl is-enabled fastapi-proxy`

## 🎯 Next Steps

1. **Test API Endpoints** (once routes are implemented)
2. **Configure Nginx** (if using reverse proxy)
3. **Set up monitoring** (optional)
4. **Complete route implementation** (5 remaining route files)
