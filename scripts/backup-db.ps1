# PowerShell PostgreSQL Database Backup Script
$ContainerName = "xhs-pg"
$DbUser = "xhs_user"
$DbName = "xhs_agent"
$BackupDir = "./backups"

# Ensure backup directory exists
if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir | Out-Null
}

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Filename = "xhs_backup_${Timestamp}.sql"
$BackupPath = Join-Path $BackupDir $Filename

Write-Host "=== Starting database backup for '${DbName}' ==="

# Execute pg_dump inside docker and output to host
docker exec -i $ContainerName pg_dump -U $DbUser -d $DbName > $BackupPath

if ($LASTEXITCODE -ne 0) {
    Write-Error "Error: Database backup failed!"
    Exit 1
}

Write-Host "=== Backup completed successfully ==="
Write-Host "File location: ${BackupPath}"
