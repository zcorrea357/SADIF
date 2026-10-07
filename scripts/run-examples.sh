#!/usr/bin/env bash
# Roda os exemplos de example/ e exemplo/ na ordem de dependência
# (clientes -> regras YARA -> crawler -> TheHive) e mostra um resumo.
# Uso: scripts/run-examples.sh [exemplo.py ...]   (sem argumentos roda todos)
# Pré-requisitos: make infra-up-all && make examples-bootstrap
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
root="$PWD"

[[ -f .env ]] || { echo "Arquivo .env não encontrado. Rode 'make setup'." >&2; exit 1; }
set -a
# shellcheck disable=SC1091
. ./.env
set +a
export NO_PROXY="localhost,127.0.0.1${NO_PROXY:+,$NO_PROXY}"
export no_proxy="$NO_PROXY"

python_bin="$(poetry env info -p)/bin/python"

examples=(
    example/config/__init__.py
    example/template_class/__init__.py
    example/utils/generete_string/markdown_string_generator.py
    example/utils/generete_string/random_string_generator.py
    exemplo/sadif_config/__init__.py
    exemplo/logdemo.py
    exemplo/__init__.py
    exemplo/cliente_manager/add_client_mock.py
    exemplo/cliente_manager/client_manager.py
    exemplo/cliente_manager/add_cliente_real.py
    exemplo/cliente_manager/client_manager_export.py
    exemplo/cliente_manager/client_manager_import.py
    exemplo/yara_demo/yara_import.py
    exemplo/yara_demo/yara_compiler.py
    exemplo/yara_demo/yara_export.py
    exemplo/modules_manager/__init__.py
    exemplo/crawler/crawler_import.py
    exemplo/crawler/crawler_manager.py
    exemplo/crawler/crawler_export.py
    exemplo/crawler/import/ransomwhat/__init__.py
    exemplo/crawler/base_crawler.py
    exemplo/crawler/sadif_crawler.py
    exemplo/demo/data_sample.py
    exemplo/web/__init__.py
    exemplo/webhook/__init__.py
    exemplo/thehive_demo/alert/alert.py
    exemplo/thehive_demo/case/crud/criar.py
    exemplo/thehive_demo/case/crud/listar.py
    exemplo/thehive_demo/case/crud/pegar.py
    exemplo/thehive_demo/case/crud/update.py
    exemplo/thehive_demo/case/crud/deletar.py
    exemplo/thehive_demo/case/crud/full.py
    exemplo/thehive_demo/case/update_chamado.py
    exemplo/thehive_demo/case/case_to_service_now.py
    exemplo/thehive_demo/observable/obs.py
    exemplo/thehive_demo/tasks/tasks.py
    exemplo/thehive_demo/process/__init__.py
    exemplo/integracao/crawler_yara_thehive/__init__.py
)
[[ $# -gt 0 ]] && examples=("$@")

log_dir="$root/reports/examples"
mkdir -p "$log_dir"
failed=0
for example in "${examples[@]}"; do
    log_file="$log_dir/$(echo "$example" | tr / _).log"
    # Cada exemplo roda num diretório temporário: os exports gravam arquivos no diretório atual
    work_dir="$(mktemp -d)"
    (cd "$work_dir" && timeout "${EXAMPLE_TIMEOUT:-300}" "$python_bin" "$root/$example") >"$log_file" 2>&1
    status=$?
    rm -rf "$work_dir"
    if [[ $status -eq 0 ]] && ! grep -q "Traceback" "$log_file"; then
        printf '\033[32mOK\033[0m    %s\n' "$example"
    else
        printf '\033[31mFALHOU\033[0m %s (exit %s, log: %s)\n' "$example" "$status" "${log_file#"$root"/}"
        failed=$((failed + 1))
    fi
done

echo "${#examples[@]} exemplos, ${failed} falha(s). Logs em reports/examples/"
[[ $failed -eq 0 ]]
