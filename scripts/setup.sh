#!/usr/bin/env bash
# Prepara o ambiente de desenvolvimento local do SADIF:
#   1. escolhe um Python suportado (3.10–3.12) e instala as dependências com Poetry
#   2. instala os hooks do pre-commit
#   3. cria o .env a partir do .env.example (gerando o THEHIVE_SECRET)
set -euo pipefail

cd "$(dirname "$0")/.."

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mErro:\033[0m %s\n' "$*" >&2; exit 1; }

command -v poetry >/dev/null 2>&1 || die "Poetry não encontrado. Instale com: pipx install poetry"

python_bin="${SADIF_PYTHON:-}"
if [[ -z "$python_bin" ]]; then
    for candidate in python3.12 python3.11 python3.10; do
        if command -v "$candidate" >/dev/null 2>&1; then
            python_bin="$candidate"
            break
        fi
    done
fi
[[ -n "$python_bin" ]] || die "Python 3.10, 3.11 ou 3.12 é necessário (o poetry.lock atual não suporta 3.13)."

log "Usando $("$python_bin" --version)"
poetry env use "$python_bin" >/dev/null

log "Instalando dependências (main + test)"
poetry install --with test --no-interaction

if [[ -d .git ]]; then
    log "Instalando hooks do pre-commit"
    poetry run pre-commit install --install-hooks || log "Aviso: falha ao instalar hooks do pre-commit (seguindo)"
fi

if [[ ! -f .env ]]; then
    log "Criando .env a partir do .env.example"
    cp .env.example .env
    if command -v openssl >/dev/null 2>&1; then
        secret="$(openssl rand -hex 32)"
    else
        secret="$("$python_bin" -c 'import secrets; print(secrets.token_hex(32))')"
    fi
    sed -i.bak "s/^THEHIVE_SECRET=.*/THEHIVE_SECRET=${secret}/" .env && rm -f .env.bak
else
    log ".env já existe — mantido"
fi

log "Pronto. Próximos passos: 'make infra-up' e 'make test'"
