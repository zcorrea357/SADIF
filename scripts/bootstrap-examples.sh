#!/usr/bin/env bash
# Prepara o que os exemplos (example/ e exemplo/) precisam, com a infra já no ar
# (make infra-up-all):
#   1. TheHive: cria a organização SADIF, o usuário de serviço e grava a API key
#      em SADIF_THEHIVE_API_SERVICE no .env
#   2. Cria um repositório git local com os clientes de exemplo, que substitui o
#      repositório privado client_monitoring (SADIF_GIT_REPO_CLIENT_MONITORING_URL)
set -euo pipefail

cd "$(dirname "$0")/.."

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mErro:\033[0m %s\n' "$*" >&2; exit 1; }

[[ -f .env ]] || die "Arquivo .env não encontrado. Rode 'make setup'."
set -a
# shellcheck disable=SC1091
. ./.env
set +a

# Grava (ou substitui) uma variável no .env
set_env() {
    local key="$1" value="$2"
    if grep -q "^${key}=" .env; then
        sed -i.bak "s|^${key}=.*|${key}=${value}|" .env && rm -f .env.bak
    else
        printf '%s=%s\n' "$key" "$value" >> .env
    fi
}

thehive="http://127.0.0.1:${THEHIVE_PORT:-9000}/api/v1"
admin_user="${THEHIVE_ADMIN_USER:-admin@thehive.local}"
admin_password="${THEHIVE_ADMIN_PASSWORD:-secret}"
service_user="${THEHIVE_SERVICE_USER:-sadif@thehive.local}"

hive() {
    curl -fsS --noproxy '*' -u "${admin_user}:${admin_password}" \
        -H 'Content-Type: application/json' "$@"
}

curl -fsS --noproxy '*' "${thehive%/v1}/status" >/dev/null \
    || die "TheHive não responde em ${thehive%/v1}. Rode 'make infra-up-all' primeiro."

if [[ -z "${SADIF_THEHIVE_API_SERVICE:-}" ]]; then
    log "TheHive: criando organização SADIF e usuário ${service_user}"
    hive "$thehive/organisation/SADIF" >/dev/null 2>&1 \
        || hive -X POST "$thehive/organisation" -d '{"name":"SADIF","description":"SADIF"}' >/dev/null
    hive "$thehive/user/${service_user}" >/dev/null 2>&1 \
        || hive -X POST "$thehive/user" \
            -d "{\"login\":\"${service_user}\",\"name\":\"SADIF Service\",\"organisation\":\"SADIF\",\"profile\":\"org-admin\"}" >/dev/null
    api_key="$(hive -X POST "$thehive/user/${service_user}/key/renew")"
    set_env SADIF_THEHIVE_API_SERVICE "$api_key"
    log "TheHive: API key gravada em SADIF_THEHIVE_API_SERVICE"
else
    log "TheHive: SADIF_THEHIVE_API_SERVICE já definido — mantido"
fi

repo_dir="${SADIF_LOCAL_CLIENT_MONITORING:-$PWD/.local/client_monitoring}"
if [[ ! -d "$repo_dir/.git" ]]; then
    log "Criando repositório local de clientes em ${repo_dir}"
    mkdir -p "$repo_dir"
    cp infra/fixtures/client_monitoring/*.json "$repo_dir/"
    git -C "$repo_dir" init -q -b main
    git -C "$repo_dir" add -A
    git -C "$repo_dir" -c user.name=sadif -c user.email=sadif@localhost commit -qm "Clientes de exemplo"
fi
set_env SADIF_GIT_REPO_CLIENT_MONITORING_URL "$repo_dir"

log "Pronto. Rode os exemplos com 'make examples'"
