#!/bin/sh
set -e

MAX_RETRIES=10
RETRY_DELAY=3
attempt=1

echo "Waiting for database to be ready..."
while [ $attempt -le $MAX_RETRIES ]; do
    if alembic upgrade head 2>/dev/null; then
        echo "Database migrations applied successfully."
        break
    fi
    echo "Migration attempt $attempt/$MAX_RETRIES failed. Retrying in ${RETRY_DELAY}s..."
    sleep $RETRY_DELAY
    attempt=$((attempt + 1))
done

if [ $attempt -gt $MAX_RETRIES ]; then
    echo "WARNING: Could not apply migrations after $MAX_RETRIES attempts. Starting app anyway."
fi

exec streamlit run ui/app.py --server.port=${PORT:-8501} --server.address=0.0.0.0
