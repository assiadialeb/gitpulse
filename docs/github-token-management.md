# GitHub Token Management - Unified Service

## Overview

This document explains the unified GitHub token management system that handles different types of tokens based on required scopes and operations.

## Problem Statement

Previously, the application had issues with GitHub token usage:
- Tasks and services failed due to incorrect token usage
- The `/applications/<appID>/add-repositories/` page didn't work properly
- No clear distinction between OAuth App tokens and user OAuth tokens
- Inconsistent token selection based on operation requirements

## Solution: Unified Token Service

The new `GitHubTokenService` provides a unified interface for managing GitHub tokens based on required scopes:

### Token Types

1. **OAuth App Token** (client_secret)
   - Used for basic operations (public repos, user info)
   - No special scopes required
   - Limited to public repository access

2. **User OAuth Token** (user's OAuth token)
   - Used for repository access (private repos, commits)
   - Requires specific scopes: `repo`, `user:email`, `read:org`
   - Full access to user's repositories

### Operation Types

The service defines different operation types with their required scopes:

```python
SCOPES = {
    'basic': [],  # No special scopes needed
    'public_repos': ['public_repo'],  # Access to public repositories
    'private_repos': ['repo'],  # Access to private repositories
    'user_info': ['user:email'],  # Access to user email
    'org_access': ['read:org'],  # Access to organization membership
    'full_access': ['repo', 'user:email', 'read:org']  # Full access
}
```

## Usage Examples

### Basic Operations (OAuth App Token)

```python
from analytics.github_token_service import GitHubTokenService

# Get token for basic operations
token = GitHubTokenService.get_token_for_operation('basic')
```

### Repository Access (User Token)

```python
# Get token for repository access
token = GitHubTokenService.get_token_for_repository_access(user_id, repo_full_name)

# Or for specific operation
token = GitHubTokenService.get_token_for_operation('private_repos', user_id)
```

### API Endpoint Access

```python
# Get appropriate token for specific API endpoint
token = GitHubTokenService.get_token_for_api_call(user_id, '/user/repos')
```

## Service Methods

### Core Methods

1. **`get_token_for_operation(operation_type, user_id=None)`**
   - Returns appropriate token based on operation type
   - Falls back to OAuth App token if user token unavailable

2. **`get_token_for_repository_access(user_id, repo_full_name)`**
   - Returns token for specific repository access
   - Handles public vs private repository logic

3. **`get_token_for_api_call(user_id, api_endpoint)`**
   - Returns token for specific GitHub API endpoint
   - Determines required scopes based on endpoint

### Validation Methods

1. **`validate_token_access(token, required_scopes=None)`**
   - Validates token access and returns detailed information
   - Checks scopes, rate limits, and user info

## Migration Guide

### For Services

Replace direct token calls with the new service:

```python
# Old way
from analytics.github_utils import get_github_token_for_user
token = get_github_token_for_user(user_id)

# New way
from analytics.github_token_service import GitHubTokenService
token = GitHubTokenService.get_token_for_operation('private_repos', user_id)
```

### For Views

Update views to use appropriate operation types:

```python
# For repository access
token = GitHubTokenService.get_token_for_operation('private_repos', request.user.id)

# For basic operations
token = GitHubTokenService.get_token_for_operation('basic')
```

### For Tasks

Update background tasks to use the new service:

```python
# In tasks.py
from analytics.github_token_service import GitHubTokenService

def some_task(user_id):
    token = GitHubTokenService.get_token_for_operation('private_repos', user_id)
    # Use token for GitHub operations
```

## Testing and Diagnostics

### Command Line Testing

Use the management command to test token access:

```bash
# Test all users
python manage.py test_github_tokens --validate

# Test specific user
python manage.py test_github_tokens --user-id 1 --operation private_repos --validate
```

### Web Interface

Access the debug page to diagnose token issues:

```
/applications/debug/github/
```

This page shows:
- OAuth App token status
- User token status
- Token validation results
- Missing scopes
- Recommendations for fixing issues

## Configuration Requirements

### OAuth App Setup

1. Create GitHub OAuth App
2. Configure in Django admin (`/github/admin/`)
3. Set client_id and client_secret

### User Scopes

Users need to connect their GitHub account with proper scopes:
- `repo` - Access to repositories
- `user:email` - Access to user email
- `read:org` - Read organization membership

### Settings Configuration

Ensure proper settings in `settings.py`:

```python
SOCIALACCOUNT_PROVIDERS = {
    'github': {
        'SCOPE': [
            'user:email',
            'repo',
            'read:org'
        ]
    }
}
```

## Error Handling

The service provides graceful fallbacks:

1. **No User Token**: Falls back to OAuth App token
2. **Missing Scopes**: Logs warning and uses available token
3. **Expired Token**: Handles token expiration gracefully
4. **Invalid Token**: Returns None and logs error

## Benefits

1. **Unified Interface**: Single service for all token operations
2. **Scope-Based Selection**: Automatically selects appropriate token
3. **Graceful Fallbacks**: Handles missing tokens gracefully
4. **Better Diagnostics**: Clear error messages and validation
5. **Consistent Behavior**: Same logic across all services

## Troubleshooting

### Common Issues

1. **"No suitable token found"**
   - Check OAuth App configuration
   - Verify user has connected GitHub account

2. **"Missing scopes"**
   - User needs to reconnect with proper scopes
   - Use `/github/force-reauth/` to force reconnection

3. **"Token expired"**
   - User needs to reconnect their GitHub account
   - Check token expiration in admin

### Debug Steps

1. Run token test command
2. Check debug page
3. Verify OAuth App configuration
4. Test user GitHub connection
5. Check scopes in GitHub account settings

## Future Enhancements

1. **Token Refresh**: Automatic token refresh for expired tokens
2. **Scope Management**: Dynamic scope checking and updates
3. **Rate Limit Handling**: Better integration with rate limit service
4. **Caching**: Token caching for performance
5. **Monitoring**: Token usage monitoring and alerts 