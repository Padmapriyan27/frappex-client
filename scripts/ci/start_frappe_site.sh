#!/usr/bin/env bash
# Create a throwaway Frappe site and serve it for the integration tests.
#
# Usage: start_frappe_site.sh <frappe-branch> <work-directory>
#
# Needs MariaDB on 127.0.0.1:3306 (root/root) and Redis on 127.0.0.1:6379.
# Exports FRAPPEX_TEST_* through $GITHUB_ENV when that variable is set,
# otherwise prints the file to source.
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
branch="$1"
work="$2"
site="frappex.test"
port=8000

mkdir -p "$work/apps" "$work/sites" "$work/logs"
git clone --quiet --depth 1 --branch "$branch" https://github.com/frappe/frappe "$work/apps/frappe"

python -m venv "$work/env"
"$work/env/bin/pip" install --quiet --upgrade pip
"$work/env/bin/pip" install --quiet --editable "$work/apps/frappe"

echo frappe > "$work/sites/apps.txt"
cat > "$work/sites/common_site_config.json" <<JSON
{
 "db_host": "127.0.0.1",
 "db_port": 3306,
 "redis_cache": "redis://127.0.0.1:6379",
 "redis_queue": "redis://127.0.0.1:6379",
 "redis_socketio": "redis://127.0.0.1:6379"
}
JSON

# Frappe requires utf8mb4 on the database server.
"$work/env/bin/python" - <<'PY'
import pymysql

connection = pymysql.connect(host="127.0.0.1", port=3306, user="root", password="root")
with connection.cursor() as cursor:
    cursor.execute("SET GLOBAL character_set_server = 'utf8mb4'")
    cursor.execute("SET GLOBAL collation_server = 'utf8mb4_unicode_ci'")
connection.close()
PY

frappe() {
    (cd "$work/sites" && "$work/env/bin/python" -m frappe.utils.bench_helper frappe "$@")
}

admin_password="$("$work/env/bin/python" -c 'import secrets; print(secrets.token_urlsafe(18))')"

# The database runs in a container, so the site user must be allowed to
# connect from any host. The option was renamed after version-14.
if frappe new-site --help | grep -q -- "--mariadb-user-host-login-scope"; then
    host_scope=(--mariadb-user-host-login-scope=%)
else
    host_scope=(--no-mariadb-socket)
fi

frappe new-site "$site" \
    --db-root-username root --db-root-password root \
    --admin-password "$admin_password" "${host_scope[@]}" > "$work/logs/new-site.log" 2>&1 \
    || { tail -n 60 "$work/logs/new-site.log"; exit 1; }

env_file="$work/test.env"
(cd "$work/sites" && "$work/env/bin/python" "$script_dir/provision_site.py" "$site" "$port" "$env_file")
echo "FRAPPEX_TEST_PASSWORD=$admin_password" >> "$env_file"

(cd "$work/sites" && nohup "$work/env/bin/python" -m frappe.utils.bench_helper frappe \
    --site "$site" serve --port "$port" --noreload > "$work/logs/serve.log" 2>&1 &)

for _ in $(seq 1 60); do
    if curl --silent --fail --header "Host: $site" "http://127.0.0.1:$port/api/method/ping" > /dev/null; then
        ready=1
        break
    fi
    sleep 1
done
[ "${ready:-0}" = 1 ] || { echo "Frappe did not start"; tail -n 60 "$work/logs/serve.log"; exit 1; }

if [ -n "${GITHUB_ENV:-}" ]; then
    while IFS='=' read -r name value; do
        case "$name" in *SECRET | *PASSWORD) echo "::add-mask::$value" ;; esac
    done < "$env_file"
    cat "$env_file" >> "$GITHUB_ENV"
else
    echo "Frappe $branch is serving $site on port $port. Settings: $env_file"
fi
