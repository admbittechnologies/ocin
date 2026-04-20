#!/bin/bash
# Quick start script for running approval workflow tests

echo "🧪 OCIN Approval Workflow Test Suite"
echo "======================================"
echo ""

# Check if docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker and try again."
    exit 1
fi

echo "✅ Docker is running"
echo ""

# Check if test database exists
echo "🔍 Checking for test database..."
TEST_DB_EXISTS=$(docker-compose exec -T db psql -U ocin -c "SELECT 1 FROM pg_database WHERE datname='ocin_test'" 2>/dev/null | grep -c "1" || echo "0")

if [ "$TEST_DB_EXISTS" -eq 0 ]; then
    echo "📊 Creating test database..."
    docker-compose exec -T db psql -U ocin -c "CREATE DATABASE ocin_test;"
    echo "✅ Test database created"
else
    echo "✅ Test database exists"
fi

echo ""

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo "📦 Installing test dependencies..."
    pip install -r requirements.txt
    echo "✅ Dependencies installed"
fi

echo ""

# Parse arguments
TEST_TYPE="all"
COVERAGE=false
PARALLEL=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --unit)
            TEST_TYPE="unit"
            shift
            ;;
        --integration)
            TEST_TYPE="integration"
            shift
            ;;
        --e2e)
            TEST_TYPE="e2e"
            shift
            ;;
        --coverage)
            COVERAGE=true
            shift
            ;;
        --parallel)
            PARALLEL=true
            shift
            ;;
        --help)
            echo "Usage: ./run_tests.sh [options]"
            echo ""
            echo "Options:"
            echo "  --unit         Run only unit tests"
            echo "  --integration   Run only integration tests"
            echo "  --e2e          Run only end-to-end tests"
            echo "  --coverage     Generate coverage report"
            echo "  --parallel      Run tests in parallel"
            echo "  --help         Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

echo "🚀 Running tests..."
echo ""

# Build pytest command
PYTEST_CMD="pytest"

if [ "$TEST_TYPE" != "all" ]; then
    PYTEST_CMD="$PYTEST_CMD -m $TEST_TYPE"
fi

if [ "$COVERAGE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD --cov=app --cov-report=html --cov-report=term"
fi

if [ "$PARALLEL" = true ]; then
    PYTEST_CMD="$PYTEST_CMD -n auto"
fi

echo "Command: $PYTEST_CMD"
echo ""

# Run tests
eval $PYTEST_CMD

# Check exit code
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ All tests passed!"
    echo ""
    if [ "$COVERAGE" = true ]; then
        echo "📊 Coverage report generated in htmlcov/index.html"
    fi
else
    echo ""
    echo "❌ Some tests failed. Please review the output above."
    exit 1
fi