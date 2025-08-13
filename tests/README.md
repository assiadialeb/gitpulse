# GitPulse Tests

This directory contains all unit and integration tests for the GitPulse project.

## Structure

```
tests/
├── __init__.py                 # Tests package
├── conftest.py                 # Pytest configuration and common fixtures
├── pytest.ini                 # Pytest configuration
├── README.md                  # This file
├── analytics/                 # Tests for analytics module
│   ├── __init__.py
│   ├── test_commit_indexing_service.py
│   ├── test_intelligent_indexing_service.py
│   └── ...
├── repositories/              # Tests for repositories module
│   ├── __init__.py
│   └── ...
├── projects/                  # Tests for projects module
│   ├── __init__.py
│   └── ...
├── developers/                # Tests for developers module
│   ├── __init__.py
│   └── ...
├── users/                     # Tests for users module
│   ├── __init__.py
│   └── ...
├── management/                # Tests for management commands
│   ├── __init__.py
│   └── ...
└── integration/               # Integration tests
    ├── __init__.py
    └── ...
```

## Organization

### By Django Module
Each Django module has its own test directory:
- `analytics/` : Tests for analytics services, indexing, metrics
- `repositories/` : Tests for repository management
- `projects/` : Tests for project management
- `developers/` : Tests for developer management
- `users/` : Tests for user management
- `management/` : Tests for Django management commands

### Test Types
- **Unit tests** : Test isolated functions/methods
- **Integration tests** : Test component interactions
- **Fixture tests** : Use common test data

## Running Tests

### All Tests
```bash
pytest
```

### Tests for a Specific Module
```bash
pytest tests/analytics/
```

### Tests with Markers
```bash
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests only
pytest -m "not slow"    # Exclude slow tests
```

### Tests with Coverage
```bash
pytest --cov=analytics --cov-report=html
```

### Tests in Verbose Mode
```bash
pytest -v
```

### Tests with Stop on First Failure
```bash
pytest -x
```

## Common Fixtures

The `conftest.py` file contains common fixtures:

- `mock_github_api` : Mock for GitHub API
- `mock_ollama_api` : Mock for Ollama API
- `sample_commit_data` : Test data for commits
- `sample_repository` : Test data for repositories
- `mock_github_token` : Test GitHub token
- `BaseTestCase` : Base class with common utilities

## Naming Conventions

- **Test files** : `test_*.py`
- **Test classes** : `Test*`
- **Test methods** : `test_*`
- **Fixtures** : `*_fixture` or descriptive

## Examples

### Simple Unit Test
```python
def test_commit_processing():
    """Test processing of commit data"""
    service = CommitIndexingService()
    result = service.process_commits(sample_data, 'test/repo')
    assert result['commits_new'] == 1
```

### Test with Mock
```python
@patch('analytics.github_service.requests.get')
def test_github_api_call(mock_get):
    """Test GitHub API call with mock"""
    mock_get.return_value.status_code = 200
    # ... test logic
```

### Integration Test
```python
@pytest.mark.integration
def test_full_indexing_workflow():
    """Test complete indexing workflow"""
    # ... test complete workflow
```

## Best Practices

1. **Isolation** : Each test should be independent
2. **Mocks** : Use mocks for external APIs
3. **Fixtures** : Reuse common fixtures
4. **Descriptive names** : Test names should be explicit
5. **Documentation** : Document complex tests
6. **Consistency** : Follow established conventions

## Dependencies

- `pytest` : Test framework
- `pytest-django` : Django support for pytest
- `pytest-cov` : Code coverage
- `pytest-mock` : Mock support

## Configuration

Pytest configuration is in `pytest.ini`:
- Database reuse
- No migrations during tests
- Warning management
- Custom markers
