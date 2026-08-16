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

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import httpx,sys; sys.exit(0 if httpx.get('http://127.0.0.1:8000/health').status_code==200 else 1)"

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "impacto.api:app", "--host", "0.0.0.0", "--port", "8000"]
