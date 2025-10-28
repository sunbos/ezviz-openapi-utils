# Contributing to EZVIZ OpenAPI Utils

Thank you for your interest in contributing to the EZVIZ OpenAPI Utils library! This document provides guidelines and instructions for setting up your development environment, running tests, and submitting contributions.

## Development Setup

### Prerequisites

- Python 3.7 or higher
- Git
- Valid `app_key` and `app_secret` from EZVIZ Open Platform (obtained from Account Settings → Appkey management → Appkey management)

### Environment Setup

1. Fork the repository on GitHub

2. Clone your fork locally:

   ```bash
   git clone https://github.com/your-username/ezviz-openapi-utils.git
   cd ezviz-openapi-utils
   ```

3. Create a virtual environment (recommended):

   ```bash
   python -m venv venv
   # On Windows
   venv\Scripts\activate
   # On macOS/Linux
   source venv/bin/activate
   ```

4. Install the package in development mode with test dependencies:

   ```bash
   pip install -e .[dev]
   ```

### Configuration

Create a `.env` file in the repository root with your EZVIZ API credentials:

```env
EZVIZ_APP_KEY=your_app_key_here
EZVIZ_APP_SECRET=your_app_secret_here
```

**Important**: Never commit your `.env` file or credentials to version control. The `.gitignore` file already excludes `.env` files.

## Running Tests

### Test Structure

- `tests/test_client.py`: Tests for the Client class (authentication, token management)
- `tests/test_api.py`: Tests for the EZVIZOpenAPI class (API methods)
- `tests/test_oauth.py`: Tests for OAuth token handling

### Test Execution

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_client.py

# Run tests with verbose output
pytest -v

# Run tests and show coverage (if coverage is installed)
pytest --cov=src/ezviz_openapi_utils
```

**Note**: Integration tests that require API credentials will automatically skip if the `.env` file is not configured or credentials are missing.

## Code Style and Quality

### Formatting

- Follow PEP 8 style guidelines
- Use consistent indentation (4 spaces)
- Keep line length under 88 characters when possible

### Type Hints

- Use type hints for all function parameters and return types
- Leverage `TypedDict` for API response structures (as seen in the existing codebase)

### Documentation

- Add docstrings to all public functions and classes using Google style
- Update README.md and README.zh-CN.md when adding new features
- Keep comments clear and concise

## Making Changes

### Branching

1. Create a new branch for your feature or bug fix:

   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/your-bug-fix
   ```

### Commit Messages

- Use descriptive commit messages
- Follow conventional commit format when appropriate:
  - `feat: add new API method for device control`
  - `fix: handle token expiration in Client class`
  - `docs: update README with new examples`
  - `test: add integration tests for device management`

### Code Changes

- Ensure your changes don't break existing functionality
- Add tests for new features or bug fixes
- Update type hints and documentation as needed

## Submitting Pull Requests

1. **Before submitting**:

   - Run all tests to ensure they pass
   - Verify your code follows the style guidelines
   - Update documentation if necessary

2. **Create the PR**:

   - Go to your fork on GitHub
   - Click "Compare & pull request"
   - Fill out the PR template with:
     - A clear description of the changes
     - The problem being solved (if applicable)
     - Any breaking changes
     - Related issues (if any)

3. **PR Requirements**:

   - All tests must pass
   - Code review approval from maintainers
   - Clear and descriptive commit history

## API Method Implementation Guidelines

If you're adding new API methods to the `EZVIZOpenAPI` class:

1. **Method Structure**:

   ```python
   def your_api_method(self, param1: str, param2: Optional[int] = None) -> YourResponseType:
       """Brief description of what the method does.

       Args:
           param1: Description of param1
           param2: Description of param2 (optional)

       Returns:
           YourResponseType: Description of return value

       Raises:
           EZVIZAPIError: If the API returns an error
       """
       # Implementation here
   ```

2. **Error Handling**:

   - Always check the API response code
   - Raise appropriate `EZVIZAPIError` exceptions for non-200 responses
   - Include the error code and message from the API response

3. **Type Safety**:

   - Define `TypedDict` structures for complex API responses
   - Use appropriate type hints for parameters and return values

## Reporting Issues

If you find a bug or have a feature request:

1. Check if the issue already exists in the [issue tracker](https://github.com/sunbos/ezviz-openapi-utils/issues)

2. If not, [open a new issue](https://github.com/sunbos/ezviz-openapi-utils/issues/new)

3. Include:

   - Clear description of the problem or feature request
   - Steps to reproduce (for bugs)
   - Expected vs actual behavior (for bugs)
   - Your environment details (Python version, OS, etc.)

## License

By contributing to this project, you agree that your contributions will be licensed under the [MIT License](LICENSE).