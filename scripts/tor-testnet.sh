#!/usr/bin/env bash
# Rede Tor privada e local (Chutney, do Tor Project) para testar o crawling de .onion
# sem acessar a rede Tor pública: 3 autoridades, 4 relays, 1 cliente (SOCKS) e 1 onion
# service que encaminha <endereço>.onion:5858 para 127.0.0.1:4747.
#
#   scripts/tor-testnet.sh start   # sobe a rede e grava SADIF_E2E_TOR_PROXY/ONION_HOST no .env
#   scripts/tor-testnet.sh stop
#
# Requer o binário tor (ex.: apt-get install tor) e python3.
set -euo pipefail

cd "$(dirname "$0")/.."
root="$PWD"
chutney_dir="$root/.local/chutney"
data_dir="$root/.local/tor-testnet"
venv="$root/.local/chutney-venv"

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mErro:\033[0m %s\n' "$*" >&2; exit 1; }

command -v tor >/dev/null 2>&1 || die "tor não encontrado. Instale com: apt-get install tor"
command -v tor-gencert >/dev/null 2>&1 || die "tor-gencert não encontrado (vem no pacote tor)"

set_env() {
    local key="$1" value="$2"
    [[ -f .env ]] || return 0
    if grep -q "^${key}=" .env; then
        sed -i.bak "s|^${key}=.*|${key}=${value}|" .env && rm -f .env.bak
    else
        printf '%s=%s\n' "$key" "$value" >> .env
    fi
}

chutney() { "$venv/bin/chutney" --data-dir "$data_dir" "$@"; }

start() {
    if [[ ! -d "$chutney_dir" ]]; then
        log "Baixando o Chutney"
        git clone -q --depth 1 https://gitlab.torproject.org/tpo/core/chutney.git "$chutney_dir"
    fi
    if [[ ! -x "$venv/bin/chutney" ]]; then
        log "Instalando o Chutney em $venv"
        python3 -m venv "$venv"
        "$venv/bin/pip" install -q -e "$chutney_dir"
    fi
    cat > "$chutney_dir/networks/sadif-hs" <<'NET'
Authority = Node(tag="a", authority=1, relay=1)
Relay = Node(tag="r", relay=1)
Client = Node(tag="c", client=1, launch_phase=2)
HS = Node(tag="h", hs=1, launch_phase=2)
NODES = Authority.getN(3) + Relay.getN(4) + Client.getN(1) + HS.getN(1)
ConfigureNodes(NODES)
NET
    stop >/dev/null 2>&1 || true
    rm -rf "$data_dir"
    mkdir -p "$data_dir"
    log "Configurando a rede Tor privada"
    (cd "$chutney_dir" && chutney init --net sadif-hs --dns-conf /dev/null --disable-ipv6 1 >/dev/null)
    (cd "$chutney_dir" && chutney configure >/dev/null)
    log "Iniciando autoridades e relays"
    (cd "$chutney_dir" && chutney start >/dev/null && chutney wait_for_bootstrap >/dev/null)
    log "Iniciando cliente e onion service"
    (cd "$chutney_dir" && chutney start --launch-phase 2 >/dev/null && chutney wait_for_bootstrap >/dev/null)

    local socks onion
    socks="$(grep -h '^SocksPort' "$data_dir"/nodes/*c/torrc | head -1 | awk '{print $2}')"
    onion="$(cat "$data_dir"/nodes/*h/hidden_service/hostname)"
    set_env SADIF_E2E_TOR_PROXY "socks5h://${socks}"
    set_env SADIF_E2E_ONION_HOST "$onion"
    log "Pronto: proxy socks5h://${socks}, onion service http://${onion}:5858 -> 127.0.0.1:4747"
}

stop() {
    if [[ -d "$data_dir/nodes" ]]; then
        (cd "$chutney_dir" && chutney stop >/dev/null) || true
    fi
    log "Rede Tor privada parada"
}

case "${1:-start}" in
    start) start ;;
    stop) stop ;;
    *) die "uso: $0 [start|stop]" ;;
esac
