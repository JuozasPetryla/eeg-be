PYTHON := .venv/bin/python

.PHONY: test test-cov integration-test

test:
	$(PYTHON) -m pytest -m "not integration"

test-cov:
	$(PYTHON) -m pytest -m "not integration" --cov=app --cov-report=term-missing --cov-report=xml

integration-test:
	@test "$${DATABASE_URL#*test}" != "$$DATABASE_URL" || (echo "Refusing to run integration tests without a test DATABASE_URL"; exit 1)
	@test "$${S3_BUCKET#*test}" != "$$S3_BUCKET" || (echo "Refusing to run integration tests without a test S3_BUCKET"; exit 1)
	$(PYTHON) -m pytest -m integration tests/integration
