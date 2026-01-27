"""
Gunicorn configuration file for production deployment
"""
import multiprocessing
import os

# Server socket
bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")
backlog = int(os.getenv("GUNICORN_BACKLOG", "2048"))

# Worker processes
# Formula: (2 x CPU cores) + 1
workers = int(os.getenv("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
worker_class = os.getenv("GUNICORN_WORKER_CLASS", "uvicorn.workers.UvicornWorker")
worker_connections = int(os.getenv("GUNICORN_WORKER_CONNECTIONS", "1000"))
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))

# Logging
accesslog = os.getenv("GUNICORN_ACCESS_LOG", "-")  # "-" means stdout
errorlog = os.getenv("GUNICORN_ERROR_LOG", "-")
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "dentc_backend"

# Server mechanics
daemon = False
pidfile = os.getenv("GUNICORN_PIDFILE", "/tmp/gunicorn.pid")
umask = 0
user = None
group = None
tmp_upload_dir = None

# SSL (if needed)
# keyfile = "/path/to/keyfile"
# certfile = "/path/to/certfile"

# Performance tuning
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "1000"))  # Restart worker after N requests
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "50"))  # Add randomness to prevent thundering herd
preload_app = os.getenv("GUNICORN_PRELOAD_APP", "true").lower() == "true"  # Load app before forking workers

# Graceful timeout for worker shutdown
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))

# Worker class specific settings
worker_tmp_dir = os.getenv("GUNICORN_WORKER_TMP_DIR", "/dev/shm")  # Use shared memory for worker temp files (faster)

def when_ready(server):
    """Called just after the server is started."""
    server.log.info("DentC Backend server is ready. Spawning workers")

def on_starting(server):
    """Called just before the master process is initialized."""
    server.log.info("Starting DentC Backend server")

def on_reload(server):
    """Called to recycle workers during a reload via SIGHUP."""
    server.log.info("Reloading DentC Backend server")

def worker_int(worker):
    """Called just after a worker has been forked."""
    worker.log.info("Worker spawned (pid: %s)", worker.pid)

def pre_fork(server, worker):
    """Called just before a worker is forked."""
    pass

def post_fork(server, worker):
    """Called just after a worker has been forked."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def post_worker_init(worker):
    """Called just after a worker has initialized the application."""
    worker.log.info("Worker initialized (pid: %s)", worker.pid)

def worker_abort(worker):
    """Called when a worker receives the SIGABRT signal."""
    worker.log.info("Worker received SIGABRT")

def pre_exec(server):
    """Called just before a new master process is forked."""
    server.log.info("Forking new master process")

def when_ready(server):
    """Called just after the server is started."""
    server.log.info("Server is ready. Spawning workers")

def on_exit(server):
    """Called just before exiting."""
    server.log.info("Shutting down: Master")

def worker_exit(server, worker):
    """Called just after a worker has been exited."""
    server.log.info("Worker exited (pid: %s)", worker.pid)
