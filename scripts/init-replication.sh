#!/bin/bash
set -e

echo "=== Initializing Replication User & Authentication ==="
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE USER replication_user REPLICATION PASSWORD 'replication_password';
EOSQL

echo "host replication replication_user 0.0.0.0/0 scram-sha-256" >> "$PGDATA/pg_hba.conf"
echo "=== Replication configuration applied successfully ==="
