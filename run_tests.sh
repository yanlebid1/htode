# run_tests.sh
#!/bin/bash

# Set environment variables for testing
export TESTING=1
export REDIS_URL="redis://localhost:6379/1"
export DB_HOST="localhost"
export TELEGRAM_TOKEN="test_token"

# Install test dependencies
pip install -r requirements-test.txt

# Run tests with coverage
pytest --cov=services --cov=common --cov-report=term --cov-report=html:coverage_html tests/

# Optional: Run only unit tests (excluding integration tests)
# pytest -m "not integration" --cov=services --cov=common --cov-report=term tests/