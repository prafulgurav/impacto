FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml README.md ./
COPY src/ src/
COPY knowledge/ knowledge/
COPY data/ data/
COPY ui/ ui/
# The migrations have to be in the image: the container runs `alembic upgrade
# head` on start, and alembic needs both its config and the revision scripts.
COPY alembic.ini ./
COPY migrations/ migrations/
RUN pip install --no-cache-dir -e .

COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh

ENV PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import httpx,os,sys; sys.exit(0 if httpx.get(f\"http://127.0.0.1:{os.environ.get('PORT','8000')}/health\").status_code==200 else 1)"

# No CMD: the entrypoint starts uvicorn on $PORT when given no arguments, so the
# image runs unchanged on Cloud Run and friends, which choose the port for you.
# Pass a command to override (the compose file passes none).
ENTRYPOINT ["/app/docker-entrypoint.sh"]
