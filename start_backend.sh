#!/bin/bash

# Go to project root
cd /var/www/dentc-backend

# Activate venv
source dentc-env/bin/activate

# Export env (optional)
export PYTHONUNBUFFERED=1
export GUNICORN_WORKERS=4
export GUNICORN_BIND=0.0.0.0:8000
export GUNICORN_LOG_LEVEL=info

# Start gunicorn
# exec gunicorn app.main:app -c gunicorn_config.py
exec python -m gunicorn app.main:app -c gunicorn_config.py
