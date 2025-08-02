# GitHub Setup Guide

This guide will help you configure GitHub integration for GitPulse, including OAuth setup and repository access.

## 🔐 GitHub OAuth2 Setup

### Step 1: Create a GitHub OAuth App

1. **Go to GitHub Apps settings**
   - Visit [GitHub Apps settings](https://github.com/settings/apps)
   - Click "New GitHub App"

2. **Fill in the app details**
   - **App name**: GitPulse (or your preferred name)
   - **Homepage URL**: `http://localhost:8000` (development) or your domain
   - **Authorization callback URL**: `http://localhost:8000/github/oauth/callback/`

3. **Set permissions**
   - **Repository permissions**: Contents (Read)
   - **User permissions**: Email addresses (Read)
   - **Organization permissions**: Members (Read)

4. **Create the app**
   - Click "Create GitHub App"
   - Note down the Client ID and Client Secret

### Step 2: Configure GitPulse

1. **Add credentials to environment**
   ```env
   GITHUB_CLIENT_ID=your_client_id_here
   GITHUB_CLIENT_SECRET=your_client_secret_here
   ```

2. **Restart the application**
   ```bash
   # Docker
   docker-compose restart web
   
   # Local
   python manage.py runserver
   ```

## 🔑 Token Management

GitPulse uses a unified token management system that handles different types of tokens based on required scopes and operations.

### Token Types

#### 1. OAuth App Token (Client Secret)
- **Use**: Basic operations (public repos, user info)
- **Scopes**: No special scopes required
- **Access**: Limited to public repository access

#### 2. User OAuth Token (User's OAuth Token)
- **Use**: Repository access (private repos, commits)
- **Scopes**: `repo`, `user:email`, `read:org`
- **Access**: Full access to user's repositories

### Operation Types

The system defines different operation types with their required scopes:

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

## 🚀 Usage Examples

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

## 🔧 Service Methods

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

## 📊 Repository Access

### Public Repositories

- **Access**: Available to all users
- **Token**: OAuth App token
- **Scopes**: No special scopes required

### Private Repositories

- **Access**: Requires user authentication
- **Token**: User OAuth token
- **Scopes**: `repo` scope required

### Organization Repositories

- **Access**: Requires organization membership
- **Token**: User OAuth token
- **Scopes**: `read:org` scope required

## 🔍 Rate Limiting

### GitHub API Limits

- **Authenticated requests**: 5,000 requests per hour
- **Unauthenticated requests**: 60 requests per hour
- **OAuth App requests**: 5,000 requests per hour

### Monitoring

GitPulse includes rate limit monitoring:

```python
# Check rate limit status
rate_limit_info = GitHubTokenService.get_rate_limit_info(token)

# Monitor usage
if rate_limit_info['remaining'] < 100:
    # Send warning or switch tokens
    pass
```

## 🛠️ Troubleshooting

### Common Issues

#### 1. "Bad credentials" error
```bash
# Check token validity
python manage.py shell
```
```python
from analytics.github_token_service import GitHubTokenService
token = GitHubTokenService.get_token_for_operation('basic')
print(GitHubTokenService.validate_token_access(token))
```

#### 2. "Not found" for private repositories
- Ensure user has granted `repo` scope
- Check if user has access to the repository
- Verify OAuth token is valid

#### 3. Rate limit exceeded
```python
# Check rate limit
rate_limit = GitHubTokenService.get_rate_limit_info(token)
print(f"Remaining: {rate_limit['remaining']}")
print(f"Reset time: {rate_limit['reset']}")
```

### Debug Commands

```bash
# Test GitHub connection
python manage.py shell
```

```python
from analytics.github_token_service import GitHubTokenService

# Test basic token
token = GitHubTokenService.get_token_for_operation('basic')
print(f"Token: {token[:10]}...")

# Test user token
user_token = GitHubTokenService.get_token_for_operation('full_access', user_id=1)
print(f"User token: {user_token[:10] if user_token else 'None'}...")

# Validate token
validation = GitHubTokenService.validate_token_access(token)
print(f"Valid: {validation['valid']}")
print(f"Scopes: {validation['scopes']}")
```

## 🔐 Security Best Practices

### Token Security

1. **Never commit tokens to version control**
   ```bash
   # Add to .gitignore
   echo "*.env" >> .gitignore
   echo "secrets/" >> .gitignore
   ```

2. **Use environment variables**
   ```env
   GITHUB_CLIENT_ID=your_client_id
   GITHUB_CLIENT_SECRET=your_client_secret
   ```

3. **Rotate tokens regularly**
   - GitHub tokens can be revoked
   - Monitor token usage and validity

### Access Control

1. **Minimize scopes**
   - Only request necessary scopes
   - Use least privilege principle

2. **Monitor usage**
   - Track API calls and rate limits
   - Monitor for unusual activity

3. **Regular audits**
   - Review token access logs
   - Validate token permissions

## 📚 Next Steps

- **[Projects Guide](projects.md)** - Add and manage repositories
- **[Analytics Guide](analytics.md)** - Understand your data
- **[Developers Guide](developers.md)** - Manage team analytics
- **[Configuration Guide](getting-started/configuration.md)** - Advanced configuration 