# Systemd Service Setup for FastAPI Proxy

## 🔐 Password Issue

When you see:
```
Authentication is required to start 'fastapi-proxy.service'.
Password:
```

It's asking for the **system user password** (frappe user's password on the server).

## ✅ Solutions

### Option 1: Use sudo (Recommended)

```bash
# Use sudo instead
sudo systemctl start fastapi-proxy
sudo systemctl status fastapi-proxy
sudo systemctl restart fastapi-proxy
sudo systemctl stop fastapi-proxy
```

### Option 2: Create Service File First

If the service file doesn't exist, create it:

```bash
# Create the service file
sudo nano /etc/systemd/system/fastapi-proxy.service
```

Paste this content:

```ini
[Unit]
Description=Flamezo FastAPI Proxy
After=network.target

[Service]
Type=simple
User=frappe
Group=frappe
WorkingDirectory=/home/frappe/frappe-bench/apps/flamezo_backend/fastapi_proxy
Environment="PATH=/home/frappe/frappe-bench/apps/flamezo_backend/fastapi_proxy/venv/bin"
ExecStart=/home/frappe/frappe-bench/apps/flamezo_backend/fastapi_proxy/venv/bin/gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:8001
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable fastapi-proxy

# Start service
sudo systemctl start fastapi-proxy

# Check status
sudo systemctl status fastapi-proxy
```

### Option 3: Run Without Systemd (For Testing)

If you don't have sudo access or want to test first:

```bash
cd /home/frappe/frappe-bench/apps/flamezo_backend/fastapi_proxy
source venv/bin/activate

# Run directly (for testing)
python -m main

# Or with gunicorn
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:8001
```

Press `Ctrl+C` to stop.

### Option 4: Run in Background (No Systemd)

```bash
cd /home/frappe/frappe-bench/apps/flamezo_backend/fastapi_proxy
source venv/bin/activate

# Run in background
nohup gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:8001 > fastapi.log 2>&1 &

# Check if running
ps aux | grep gunicorn

# View logs
tail -f fastapi.log

# Stop (find PID first)
ps aux | grep gunicorn
kill <PID>
```

## 🔍 Verify Service Status

```bash
# Check if service exists
sudo systemctl list-unit-files | grep fastapi

# Check service status
sudo systemctl status fastapi-proxy

# View logs
sudo journalctl -u fastapi-proxy -f

# View last 50 lines
sudo journalctl -u fastapi-proxy -n 50
```

## 🚨 Common Issues

### Issue: "Unit fastapi-proxy.service not found"
**Solution**: Service file doesn't exist. Create it using Option 2 above.

### Issue: "Permission denied"
**Solution**: Use `sudo` for all systemctl commands.

### Issue: "Failed to start"
**Solution**: 
1. Check logs: `sudo journalctl -u fastapi-proxy -n 50`
2. Verify paths in service file are correct
3. Check .env file exists and has correct permissions
4. Test manually: `python -m main`

### Issue: "ModuleNotFoundError"
**Solution**: 
```bash
cd /home/frappe/frappe-bench/apps/flamezo_backend/fastapi_proxy
source venv/bin/activate
pip install -r requirements.txt
```

## 📋 Quick Setup Checklist

- [ ] Service file created at `/etc/systemd/system/fastapi-proxy.service`
- [ ] Service file has correct paths
- [ ] `.env` file exists and configured
- [ ] Virtual environment has all dependencies
- [ ] Service enabled: `sudo systemctl enable fastapi-proxy`
- [ ] Service started: `sudo systemctl start fastapi-proxy`
- [ ] Service running: `sudo systemctl status fastapi-proxy`
- [ ] Health check works: `curl http://localhost:8001/health`

## 💡 Recommended: Use sudo

Always use `sudo` for systemctl commands:

```bash
sudo systemctl start fastapi-proxy
sudo systemctl stop fastapi-proxy
sudo systemctl restart fastapi-proxy
sudo systemctl status fastapi-proxy
sudo systemctl enable fastapi-proxy
sudo systemctl disable fastapi-proxy
```

This avoids password prompts if your user has sudo access configured.
