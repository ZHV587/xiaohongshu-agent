#!/bin/bash
set -e

# Ensure correct permissions on the PGDATA volume
chmod 700 /var/lib/postgresql/data

if [ ! -s "/var/lib/postgresql/data/PG_VERSION" ]; then
  echo "=== Standby Database not initialized ==="
  echo "Starting pg_basebackup from primary host 'pg'..."
  until pg_basebackup -h pg -U replication_user -D /var/lib/postgresql/data -Fp -Xs -P -R; do
    echo "Primary host 'pg' is not ready yet. Retrying in 2 seconds..."
    sleep 2
  done
  echo "=== Streaming replication backup completed successfully ==="
fi

echo "=== Starting standby PostgreSQL in hot_standby mode ==="
exec docker-entrypoint.sh postgres -c hot_standby=on
