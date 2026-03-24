VENV = venv
PYTHON = $(VENV)/bin/python
PIP = $(VENV)/bin/pip
MANAGE = $(PYTHON) manage.py

include .env

install:
	test -d $(VENV) || python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

migrate:
	$(MANAGE) makemigrations
	$(MANAGE) migrate

load_fixtures:
	$(MANAGE) loaddata belts.json
	$(MANAGE) loaddata categories.json
	$(MANAGE) loaddata techniques.json
	$(MANAGE) loaddata flows.json
	$(MANAGE) loaddata variations.json

run:
	$(MANAGE) runserver 127.0.0.1:8000

shell:
	$(MANAGE) shell

createsuperuser:
	$(MANAGE) createsuperuser

test:
	$(VENV)/bin/pytest

pytest-cov:
	$(VENV)/bin/pytest --cov=. --cov-report=term-missing

format:
	$(VENV)/bin/black .
	$(VENV)/bin/isort .

lint:
	$(VENV)/bin/flake8 --exclude=venv,migrations --ignore=E501 .

clean:
	find . -name '*.pyc' -delete
	find . -name '__pycache__' -delete

# ─── Docker/Podman Commands ─────────────────────────────────────────────

# Variables para Docker
COMPOSE_PROVIDER = ~/.local/bin/docker-compose-v2
DOCKER_HOST_VAR = unix:///run/user/$(shell id -u)/podman/podman.sock
COMPOSE_CMD = PODMAN_COMPOSE_PROVIDER=$(COMPOSE_PROVIDER) DOCKER_HOST=$(DOCKER_HOST_VAR) podman compose

.PHONY: docker-help docker-up docker-down docker-restart docker-build docker-status docker-logs docker-clean docker-seed

# Ayuda para comandos Docker
docker-help:
	@echo "🐳 FlowRoll - Comandos Docker/Podman disponibles:"
	@echo ""
	@echo "  make docker-up       - Levantar servicios con Docker/Podman"
	@echo "  make docker-down     - Parar servicios"
	@echo "  make docker-restart  - Reiniciar servicios"
	@echo "  make docker-build    - Reconstruir y levantar"
	@echo "  make docker-status   - Ver estado de servicios"
	@echo "  make docker-logs     - Ver logs en tiempo real"
	@echo "  make docker-clean    - Limpiar contenedores y redes"
	@echo "  make docker-seed     - Cargar datos de prueba en container"
	@echo ""
	@echo "🌐 URLs cuando estén activos:"
	@echo "  App:      http://localhost:8080"
	@echo "  API docs: http://localhost:8080/api/docs/"

# Asegurar socket de Podman
docker-ensure-socket:
	@mkdir -p /run/user/$(shell id -u)/podman
	@if ! pgrep -f "podman system service" > /dev/null; then \
		echo "🔧 Iniciando socket de Podman..."; \
		podman system service --time=0 unix:///run/user/$(shell id -u)/podman/podman.sock & \
		sleep 2; \
	fi

# Levantar servicios
docker-up: docker-ensure-socket
	@echo "🚀 Levantando servicios FlowRoll..."
	@$(COMPOSE_CMD) up -d
	@$(MAKE) docker-status

# Parar servicios
docker-down:
	@echo "🛑 Parando servicios FlowRoll..."
	@$(COMPOSE_CMD) down

# Reiniciar servicios
docker-restart: docker-down docker-up

# Reconstruir y levantar
docker-build: docker-ensure-socket
	@echo "🔨 Reconstruyendo y levantando servicios..."
	@$(COMPOSE_CMD) up -d --build
	@$(MAKE) docker-status

# Ver estado
docker-status:
	@echo "📊 Estado de servicios:"
	@DOCKER_HOST=$(DOCKER_HOST_VAR) podman ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" || echo "❌ No hay servicios ejecutándose"

# Ver logs
docker-logs:
	@$(COMPOSE_CMD) logs -f

# Limpiar todo
docker-clean: docker-down
	@echo "🧹 Limpiando contenedores y redes..."
	@DOCKER_HOST=$(DOCKER_HOST_VAR) podman system prune -f

# Cargar datos en container
docker-seed: docker-ensure-socket
	@echo "🌱 Cargando datos de prueba en container..."
	@$(COMPOSE_CMD) exec web python manage.py seed_db --env dev
