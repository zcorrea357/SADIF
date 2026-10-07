COMPOSE := docker compose -f infra/docker-compose.yml --env-file .env

# Exporta o .env para os comandos Python (SADIF_* sobrescreve o variables.json)
ifneq (,$(wildcard .env))
include .env
export
endif

.DEFAULT_GOAL := help

.PHONY: help
help: ## Lista os comandos disponíveis
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

.PHONY: setup
setup: ## Instala dependências, hooks do pre-commit e cria o .env
	./scripts/setup.sh

.PHONY: infra-up
infra-up: .env ## Sobe o MongoDB
	$(COMPOSE) up -d --wait mongodb

.PHONY: infra-up-all
infra-up-all: .env ## Sobe MongoDB, mongo-express e TheHive 5 (Cassandra + Elasticsearch)
	$(COMPOSE) --profile tools --profile thehive up -d --wait

.PHONY: infra-down
infra-down: .env ## Para todos os serviços (mantém os volumes)
	$(COMPOSE) --profile tools --profile thehive down

.PHONY: infra-reset
infra-reset: .env ## Para todos os serviços e APAGA os volumes de dados
	$(COMPOSE) --profile tools --profile thehive down -v

.PHONY: infra-ps
infra-ps: .env ## Mostra o estado dos serviços
	$(COMPOSE) --profile tools --profile thehive ps

.PHONY: infra-logs
infra-logs: .env ## Acompanha os logs dos serviços
	$(COMPOSE) --profile tools --profile thehive logs -f

.PHONY: examples-bootstrap
examples-bootstrap: .env ## Configura o TheHive (API key) e o repositório local de clientes para os exemplos
	./scripts/bootstrap-examples.sh

.PHONY: examples
examples: .env ## Roda todos os exemplos (requer infra-up-all e examples-bootstrap)
	./scripts/run-examples.sh

.PHONY: test
test: ## Roda os testes com cobertura
	poetry run poe test

.PHONY: lint
lint: ## Roda os linters (pre-commit + safety)
	poetry run poe lint

.env:
	@echo "Arquivo .env não encontrado. Rode 'make setup' (ou 'cp .env.example .env')." && exit 1
