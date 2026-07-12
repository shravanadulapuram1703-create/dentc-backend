FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Cloud Run injects PORT (defaults to 8080). Bind gunicorn to it.
ENV PORT=8080
EXPOSE 8080

# FastAPI app object is app.main:app, served by gunicorn + uvicorn workers.
# --forwarded-allow-ips="*" trusts X-Forwarded-* from Cloud Run's front end (which
# terminates TLS and forwards as http). Without it uvicorn ignores
# X-Forwarded-Proto: https, so trailing-slash 307 redirects and any generated URLs
# come back as http:// — and preflighted cross-origin requests can't follow an
# http redirect, which fails the call. Cloud Run has no direct ingress, so "*" is safe.
CMD exec gunicorn app.main:app \
    -k uvicorn.workers.UvicornWorker \
    -b 0.0.0.0:${PORT} \
    --workers ${GUNICORN_WORKERS:-2} \
    --timeout 120 \
    --forwarded-allow-ips="*" \
    --access-logfile - \
    --error-logfile -
