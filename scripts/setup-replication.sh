#!/bin/bash
# 幂等配置主库复制(可对**既有**数据卷运行,可重复执行)。
#
# 为什么不用 init-replication.sh:那个脚本挂在 /docker-entrypoint-initdb.d/,只在 initdb
# (数据目录为空)时运行;而 pgdata 是 external 既有卷,initdb 从不触发 → 复制用户从未创建、
# pg_hba 从未加规则 → standby 的 pg_basebackup 无限重试、热备实为空壳。
#
# 用法(对运行中的主库执行一次,改密码或网段后可再次执行,幂等):
#   XHS_PG_REPLICATION_PASSWORD=<pw> docker compose exec -T -e XHS_PG_REPLICATION_PASSWORD pg \
#       bash /usr/local/bin/setup-replication.sh
set -euo pipefail

PG_USER="${POSTGRES_USER:?POSTGRES_USER required}"
PG_DB="${POSTGRES_DB:?POSTGRES_DB required}"
REPL_PW="${XHS_PG_REPLICATION_PASSWORD:?XHS_PG_REPLICATION_PASSWORD required}"
HBA_DIR="${PGDATA:-/var/lib/postgresql/data}"

echo "=== Ensuring replication role (idempotent) ==="
# psql 变量 :'pw' 只在普通 SQL(非 dollar-quote)里插值,故先用 set_config 把口令写进会话级
# GUC my.pw,再在 DO 块里 current_setting 读取 —— 避免口令出现在 argv/进程列表,也躲开
# dollar-quote 内不插值的坑。set_config(...,false)=会话级(非事务局部),DO 块同会话可读。
psql -v ON_ERROR_STOP=1 --username "$PG_USER" --dbname "$PG_DB" \
  -v pw="$REPL_PW" <<-'EOSQL'
	SELECT set_config('my.pw', :'pw', false);
	DO $$
	BEGIN
	  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'replication_user') THEN
	    EXECUTE format('CREATE ROLE replication_user WITH REPLICATION LOGIN PASSWORD %L', current_setting('my.pw'));
	  ELSE
	    EXECUTE format('ALTER ROLE replication_user WITH REPLICATION LOGIN PASSWORD %L', current_setting('my.pw'));
	  END IF;
	END
	$$;
EOSQL

echo "=== Ensuring pg_hba replication rule (samenet, not 0.0.0.0/0) ==="
# 网段收窄:samenet = 与主库同子网(即 xhs-net 这张有界 bridge 网),不再对任意 IP 开放复制。
# 幂等:已存在等价规则则不重复追加。
HBA_LINE="host replication replication_user samenet scram-sha-256"
if ! grep -qF "$HBA_LINE" "$HBA_DIR/pg_hba.conf"; then
  echo "$HBA_LINE" >> "$HBA_DIR/pg_hba.conf"
  echo "Appended replication rule to pg_hba.conf"
else
  echo "Replication rule already present, skipping"
fi

echo "=== Reloading PostgreSQL config (pg_hba 改动需 reload)==="
psql -v ON_ERROR_STOP=1 --username "$PG_USER" --dbname "$PG_DB" -c "SELECT pg_reload_conf();"
echo "=== Replication setup complete ==="
