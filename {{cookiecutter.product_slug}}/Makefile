.PHONY: install format lint test coverage run build package ci clean docker-build docker-up docker-down docker-logs

IMAGE_NAME := {{cookiecutter.product_slug}}
IMAGE_TAG := latest
CONTAINER_NAME := {{cookiecutter.product_slug}}
HOST_PORT := 8000

# Install dependencies using uv
install:
	uv sync --all-groups

# Format code using Ruff
format:
	uv run ruff format src tests

# Lint code using Ruff
lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

# Run tests
test:
	uv run pytest

# Run tests with code coverage
coverage:
	uv run pytest --cov=src --cov-report=term-missing --cov-report=html

# Run the development server
run:
	uv run uvicorn src.server:app --host 0.0.0.0 --port 8000 --reload --no-access-log

# Build Docker container image
docker-build:
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .

build: docker-build

# Start the container in the background (rebuilds the image first)
docker-up: docker-build
	-docker rm -f $(CONTAINER_NAME)
	docker run -d --name $(CONTAINER_NAME) -p $(HOST_PORT):8000 $(IMAGE_NAME):$(IMAGE_TAG)

# Stop and remove the container
docker-down:
	-docker stop $(CONTAINER_NAME)
	-docker rm $(CONTAINER_NAME)

# Follow container logs
docker-logs:
	docker logs -f $(CONTAINER_NAME)

# Build sdist and wheel
package:
	uv build

# Clean artifacts, reinstall, lint, test, and build a fresh package
ci: clean install lint test coverage package

# Clean up build artifacts and cache directories
clean:
	rm -rf .venv dist build *.egg-info .pytest_cache .ruff_cache htmlcov .coverage coverage.xml
	find . -type f -name '*.pyc' -delete
	find . -type d -name '__pycache__' -delete
