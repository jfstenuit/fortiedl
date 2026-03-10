#!/usr/bin/env bash
# ============================================================
# run-tests.sh — start an ephemeral PostgreSQL container,
#                install dependencies, run pytest, tear down.
# ============================================================
# Requires: sudo docker, python3.12, pip
#
# Usage:
#   bash run-tests.sh            # run all tests
#   bash run-tests.sh -k expiry  # run tests matching "expiry"
# ============================================================

set -euo pipefail

PG_CONTAINER="blocklist-test-db"
PG_PORT="15432"
PG_USER="postgres"
PG_PASS="postgres"
PG_DB="test_blocklist"
IMAGE="postgres:16-alpine"

cleanup() {
    echo ""
    echo "── Stopping test database ──────────────────────────"
    sudo docker rm -f "$PG_CONTAINER" 2>/dev/null || true
}
trap cleanup EXIT

echo "── Starting PostgreSQL container ───────────────────"
sudo docker run -d \
    --name  "$PG_CONTAINER" \
    -p      "${PG_PORT}:5432" \
    -e      POSTGRES_USER="$PG_USER" \
    -e      POSTGRES_PASSWORD="$PG_PASS" \
    -e      POSTGRES_DB="$PG_DB" \
    "$IMAGE"

# Wait for PostgreSQL to accept connections
echo -n "── Waiting for PostgreSQL"
for i in $(seq 1 20); do
    if sudo docker exec "$PG_CONTAINER" \
       pg_isready -U "$PG_USER" -d postgres -q 2>/dev/null; then
        echo " ready."
        break
    fi
    echo -n "."
    sleep 1
    if [ "$i" -eq 20 ]; then
        echo " TIMEOUT"; exit 1
    fi
done

echo "── Installing Python dependencies ──────────────────"
source .venv/bin/activate
pip install -q -r requirements-test.txt

echo "── Running pytest ──────────────────────────────────"
export TEST_DB_HOST="localhost"
export TEST_DB_PORT="$PG_PORT"
export TEST_DB_NAME="$PG_DB"
export TEST_DB_USER="$PG_USER"
export TEST_DB_PASSWORD="$PG_PASS"

python -m pytest tests/ -v "$@"
