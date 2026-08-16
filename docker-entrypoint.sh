#!/bin/sh
# Bring the schema up to date, then hand off to the real command.
#
# Migrations run here rather than at build time so the image stays
# environment-agnostic and a rollback does not need a rebuild.
#
# Set IMPACTO_RUN_MIGRATIONS=false on every replica beyond the first. Two
# containers racing `alembic upgrade head` against the same database is the same
# class of mistake as two schedulers, and the fix is the same: exactly one owner.
set -e

if [ "${IMPACTO_RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "impacto: running alembic upgrade head"
  alembic upgrade head
else
  echo "impacto: IMPACTO_RUN_MIGRATIONS=false, skipping migrations"
fi

# Cloud Run, App Engine and Heroku all inject the port to listen on rather than
# letting the image pick one. Honouring it here means the same image runs
# unmodified on those and on plain Docker, where 8000 is the default.
if [ $# -eq 0 ]; then
  exec uvicorn impacto.api:app --host 0.0.0.0 --port "${PORT:-8000}"
fi

exec "$@"
