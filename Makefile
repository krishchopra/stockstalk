.PHONY: help install test format lint run configure server clean docker-build docker-run

help:
	@echo "StockStalk - Available Commands"
	@echo "================================"
	@echo "install      - Install dependencies using UV"
	@echo "test         - Run tests with coverage"
	@echo "format       - Format code with Black"
	@echo "lint         - Check code formatting"
	@echo "run          - Run continuous monitoring"
	@echo "configure    - Run configuration UI"
	@echo "server       - Run API server"
	@echo "once         - Run analysis once and exit"
	@echo "clean        - Remove generated files"
	@echo "docker-build - Build Docker image"
	@echo "docker-run   - Run with docker-compose"

install:
	pip install uv
	uv pip install -e ".[dev]"

test:
	pytest --cov=stockstalk --cov-report=term-missing

format:
	black stockstalk/ tests/

lint:
	black --check stockstalk/ tests/
	mypy stockstalk/

run:
	python -m stockstalk

configure:
	python -m stockstalk --configure

server:
	python -m stockstalk --server

once:
	python -m stockstalk --once

clean:
	rm -rf .pytest_cache
	rm -rf .coverage
	rm -rf htmlcov
	rm -rf dist
	rm -rf build
	rm -rf *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete

docker-build:
	docker build -t stockstalk .

docker-run:
	docker-compose up -d

docker-stop:
	docker-compose down
