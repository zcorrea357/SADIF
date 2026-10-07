# Secure Asses Data Insight Framework - SADIF


[![Release](https://img.shields.io/github/v/release/florestleaks/SADIF)](https://img.shields.io/github/v/release/florestleaks/SADIF)
[![Build status](https://img.shields.io/github/actions/workflow/status/florestleaks/SADIF/main.yml?branch=main)](https://github.com/florestleaks/SADIF/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/florestleaks/SADIF/graph/badge.svg?token=IE1G7T0wo0)](https://codecov.io/gh/florestleaks/SADIF)
[![Commit activity](https://img.shields.io/github/commit-activity/m/florestleaks/SADIF)](https://img.shields.io/github/commit-activity/m/florestleaks/SADIF)
[![License](https://img.shields.io/github/license/florestleaks/SADIF)](https://img.shields.io/github/license/florestleaks/SADIF)


- **Github repository**: <https://github.com/florestleaks/SADIF/>
- **Github Documentation** <https://florestleaks.github.io/SADIF/>
- **OFFICIAL Documentation** <https://forestleaks.com/SADIF/>

# install
```bash
pip3 install sadif 
```
# Ambiente de desenvolvimento

Pré-requisitos: Python 3.10–3.12, [Poetry](https://python-poetry.org/), Docker com Compose v2 e `make`.

```bash
make setup         # dependências (Poetry), hooks do pre-commit e .env (gera THEHIVE_SECRET)
make infra-up      # sobe o MongoDB em 127.0.0.1:27017
make test          # testes com cobertura
```

## Infraestrutura (`infra/docker-compose.yml`)

| Serviço        | Comando             | Endereço                         | Observação |
|----------------|---------------------|----------------------------------|------------|
| MongoDB 7      | `make infra-up`     | `mongodb://localhost:27017`      | Cria as coleções do banco `Crawler` na 1ª inicialização |
| mongo-express  | `make infra-up-all` | <http://localhost:8081>          | Login em `MONGO_EXPRESS_USER`/`MONGO_EXPRESS_PASSWORD` |
| TheHive 5      | `make infra-up-all` | <http://localhost:9000>          | Usa Cassandra + Elasticsearch; login inicial `admin@thehive.local` / `secret` (troque) |

Outros comandos: `make infra-ps`, `make infra-logs`, `make infra-down` (mantém os dados) e
`make infra-reset` (apaga os volumes). O stack completo precisa de ~4 GB de RAM livres.

## Exemplos (`example/` e `exemplo/`)

Os exemplos usam o MongoDB e o TheHive locais e os repositórios públicos
[`crawler_monitoring`](https://github.com/florestleaks/crawler_monitoring) e
[`client_monitoring_yara_rules`](https://github.com/florestleaks/client_monitoring_yara_rules)
(clonados automaticamente pelo `GitManager`).

```bash
make infra-up-all        # MongoDB + TheHive
make examples-bootstrap  # cria org/usuário/API key no TheHive e o repositório local de clientes
make examples            # roda todos os exemplos em ordem e mostra um resumo (logs em reports/examples/)
```

O repositório de clientes (`client_monitoring`) é privado. O `make examples-bootstrap` cria um
repositório git local em `.local/client_monitoring` com o cliente `Internal`
(`infra/fixtures/client_monitoring/`), dono das regras `InternalMonitoramento*` do repositório de
regras YARA, e aponta `SADIF_GIT_REPO_CLIENT_MONITORING_URL` para ele. Para rodar um exemplo só:
`./scripts/run-examples.sh exemplo/yara_demo/yara_import.py`.

## Configuração

Os valores padrão ficam em `src/sadif/dataconfig/variables.json`. Qualquer chave pode ser
sobrescrita por variável de ambiente com o prefixo `SADIF_` (valores JSON são interpretados):

```bash
export SADIF_MONGODB_URL=mongodb://localhost:27017
export SADIF_THEHIVE_API_SERVICE=<api-key-do-thehive>
export SADIF_YARA_TYPE_RULES='["Leak", "POC"]'
```

O `Makefile` exporta automaticamente as variáveis do `.env`. Para gerar a API key do TheHive,
crie um usuário de serviço na interface web e coloque a chave em `SADIF_THEHIVE_API_SERVICE`.
