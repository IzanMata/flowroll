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
	$(MANAGE) test

format:
	$(VENV)/bin/black .
	$(VENV)/bin/isort .

lint:
	$(VENV)/bin/flake8 --exclude=venv,migrations --ignore=E501 .

clean:
	find . -name '*.pyc' -delete
	find . -name '__pycache__' -delete
