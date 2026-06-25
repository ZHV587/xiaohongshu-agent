#!/bin/bash
set -e

# Configuration
CONTAINER_NAME="xhs-pg"
DB_USER="xhs_user"
DB_NAME="xhs_agent"
BACKUP_DIR="./backups"

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"

# Generate backup filename with timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILENAME="xhs_backup_${TIMESTAMP}.sql.gz"
BACKUP_PATH="${BACKUP_DIR}/${FILENAME}"

echo "=== Starting database backup for '${DB_NAME}' ==="

# Trigger pg_dump inside the docker container and compress on host
if ! docker exec -i "$CONTAINER_NAME" pg_dump -U "$DB_USER" -d "$DB_NAME" | gzip > "$BACKUP_PATH"; then
  echo "Error: Database backup failed!"
  exit 1
fi

echo "=== Backup completed successfully ==="
echo "File location: ${BACKUP_PATH}"
echo "File size: $(du -sh "$BACKUP_PATH" | cut -f1)"
