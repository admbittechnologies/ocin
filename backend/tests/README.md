# Approval Workflow Tests

This directory contains comprehensive tests for the OCIN approval workflow system.

## Test Structure

- `conftest.py` - Shared fixtures and test configuration
- `test_approval_model.py` - Unit tests for Approval model
- `test_approval_service.py` - Service layer tests
- `test_approval_api.py` - API endpoint tests  
- `test_approval_workflow_e2e.py` - End-to-end integration tests

## Running Tests

### Run All Tests
```bash
pytest
```

### Run Specific Test Files
```bash
pytest tests/test_approval_model.py
pytest tests/test_approval_service.py
pytest tests/test_approval_api.py
pytest tests/test_approval_workflow_e2e.py
```

### Run by Test Type
```bash
# Only unit tests
pytest -m unit

# Only integration tests
pytest -m integration

# Only end-to-end tests
pytest -m e2e

# Exclude slow tests
pytest -m "not slow"
```

### Run with Coverage
```bash
pytest --cov=app --cov-report=html --cov-report=term
```

### Run in Parallel (faster)
```bash
pytest -n auto
```

### Run Specific Tests
```bash
# Run specific test function
pytest tests/test_approval_service.py::TestCreateApproval::test_create_approval_minimal

# Run specific test class
pytest tests/test_approval_service.py::TestCreateApproval
```

## Test Coverage Goals

- **Minimum coverage: 80%**
- **Target coverage: 90%+**
- **Critical code: 100%**

## Test Categories

### Unit Tests (`@pytest.mark.unit`)
- Model properties and constraints
- Database relationships
- Status validation
- JSON payload handling
- Timestamp behavior

### Integration Tests (`@pytest.mark.integration`)  
- API endpoint functionality
- Authentication and authorization
- Request/response validation
- Error handling
- Status transitions

### End-to-End Tests (`@pytest.mark.e2e`)
- Complete approval workflows
- Multi-step processes
- Run and approval integration
- Schedule-based approvals
- Concurrent operations

## Test Fixtures

### Fixtures Available in conftest.py

- `db_session` - Clean database session for each test
- `client` - HTTP client for API testing
- `test_user` - Test user account
- `test_agent` - Test agent configuration
- `test_run` - Test agent run
- `test_approval` - Test approval request
- `auth_token` - JWT authentication token
- `auth_headers` - Authorization headers
- `authenticated_client` - Pre-authenticated HTTP client

## Approval Workflow Test Scenarios

### 1. Basic Approval Flow
- Create approval request
- List pending approvals
- View approval details
- Approve/reject approval
- Verify status change

### 2. Approval with Run Integration
- Agent run requests approval
- User approves request
- Child run is created
- Parent run is linked

### 3. Multiple Approvals
- Create multiple approvals
- Filter by status (pending/approved/rejected)
- Paginate results
- Count pending approvals

### 4. Approval Expiration
- Set expiration time
- Check expired approvals
- Prevent approval of expired requests

### 5. Complex Payloads
- Nested JSON payloads
- Large payloads
- Special characters
- Binary data handling

### 6. Security & Authorization
- Users cannot see others' approvals
- Authentication required
- Authorization checks per endpoint
- Invalid token handling

### 7. Error Handling
- Invalid approval IDs
- Status transitions validation
- Database constraint violations
- Network errors

## Prerequisites

Before running tests:

1. **Start Database**
```bash
docker-compose up -d db
```

2. **Create Test Database**
```bash
docker-compose exec db psql -U ocin -c "CREATE DATABASE ocin_test;"
```

3. **Run Migrations**
```bash
alembic upgrade head
```

4. **Install Test Dependencies**
```bash
pip install -r requirements.txt
```

## Troubleshooting

### Tests fail with "Database not found"
```bash
# Ensure test database exists
docker-compose exec db psql -U ocin -c "\l"
# If ocin_test doesn't exist:
docker-compose exec db psql -U ocin -c "CREATE DATABASE ocin_test;"
```

### Tests fail with "Import error"
```bash
# Install dependencies
pip install -r requirements.txt
```

### Tests are slow
```bash
# Run in parallel
pytest -n auto

# Or run specific test category
pytest -m unit
```

### Coverage not generating
```bash
# Install pytest-cov
pip install pytest-cov

# Run with coverage flag
pytest --cov=app --cov-report=html
```

## Continuous Integration

These tests are designed to run in CI/CD pipelines:

```yaml
# Example GitHub Actions
- name: Run tests
  run: |
    pytest --cov=app --cov-report=xml --cov-report=term

- name: Upload coverage
  uses: codecov/codecov-action@v3
  with:
    files: ./coverage.xml
```

## Test Data

Tests use isolated, temporary databases. No test data persists between test runs. Each test gets:
- Fresh database session
- Clean state
- Independent test data

## Contributing

When adding new approval features:

1. **Add unit tests** for models and services
2. **Add integration tests** for new API endpoints
3. **Add e2e tests** for complete workflows
4. **Update fixtures** if new test data is needed
5. **Maintain 80%+ coverage**
6. **Run full test suite** before committing