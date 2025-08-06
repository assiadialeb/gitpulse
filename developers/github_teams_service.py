"""
GitHub Teams service for syncing teams and associating developers
"""
import logging
import requests
from typing import Dict, List, Optional
from django.contrib import messages
from allauth.socialaccount.models import SocialToken, SocialApp
from django.utils import timezone

from analytics.models import Developer, DeveloperAlias

logger = logging.getLogger(__name__)


class GitHubTeamsService:
    """Service for syncing GitHub teams and associating developers"""
    
    def __init__(self, user=None):
        self.user = user
        self.token = self._get_github_token()
    
    def _get_github_token(self) -> Optional[str]:
        """Get GitHub token for API access"""
        try:
            github_app = SocialApp.objects.filter(provider='github').first()
            if not github_app:
                logger.error("No GitHub SocialApp found")
                return None
            
            social_token = SocialToken.objects.filter(
                app=github_app
            ).filter(
                expires_at__isnull=True
            ).first() or SocialToken.objects.filter(
                app=github_app,
                expires_at__gt=timezone.now()
            ).first()
            
            if social_token:
                return social_token.token
            return None
        except Exception as e:
            logger.error(f"Error getting GitHub token: {e}")
            return None
    
    def _make_github_request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """Make GitHub API request"""
        if not self.token:
            return None
        
        headers = {
            'Authorization': f'token {self.token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        url = f"https://api.github.com{endpoint}"
        
        try:
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                logger.warning(f"Endpoint not found: {endpoint}")
                return None
            elif response.status_code == 403:
                logger.warning(f"Permission denied for: {endpoint}")
                return None
            else:
                logger.error(f"GitHub API error {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Request failed for {endpoint}: {e}")
            return None
    
    def get_user_organizations(self) -> List[Dict]:
        """Get organizations the user belongs to"""
        orgs = self._make_github_request("/user/orgs")
        return orgs or []
    
    def get_organization_teams(self, org_name: str) -> List[Dict]:
        """Get teams in an organization"""
        teams = self._make_github_request(f"/orgs/{org_name}/teams")
        return teams or []
    
    def get_team_members(self, org_name: str, team_slug: str) -> List[Dict]:
        """Get members of a specific team"""
        members = self._make_github_request(f"/orgs/{org_name}/teams/{team_slug}/members")
        return members or []
    
    def sync_teams_for_developer(self, github_username: str) -> Dict:
        """Sync teams for a specific developer"""
        try:
            logger.info(f"  Starting sync for {github_username}...")
            
            # Find developer in MongoDB first
            developer = self._find_developer_by_github_username(github_username)
            
            if not developer:
                logger.warning(f"  Developer not found for {github_username}")
                return {
                    'success': False,
                    'error': f'Developer not found for GitHub username: {github_username}'
                }
            
            # Get developer's organizations from their commits
            developer_orgs = self._get_developer_organizations_from_commits(developer)
            logger.info(f"  Found organizations for {github_username}: {developer_orgs}")
            
            developer_teams = []
            
            # For each organization the developer belongs to, check their teams
            for org_name in developer_orgs:
                logger.info(f"  Checking teams in organization: {org_name}")
                
                # Get teams in this organization
                teams = self.get_organization_teams(org_name)
                logger.info(f"  Found {len(teams)} teams in {org_name}")
                
                for team in teams:
                    team_slug = team.get('slug')
                    if not team_slug:
                        continue
                    
                    logger.info(f"  Checking team: {team_slug}")
                    
                    # Check if this developer is a member of this team
                    members = self.get_team_members(org_name, team_slug)
                    logger.info(f"  Team {team_slug} has {len(members)} members")
                    
                    for member in members:
                        if member.get('login') == github_username:
                            developer_teams.append(team_slug)
                            logger.info(f"  ✅ {github_username} is member of {team_slug}")
                            break
            
            # Find developer in MongoDB
            developer = self._find_developer_by_github_username(github_username)
            
            if developer:
                # Update developer with team information
                developer.github_teams = developer_teams
                developer.github_organizations = developer_orgs
                
                if developer_teams:
                    developer.primary_team = developer_teams[0]  # First team as primary
                
                developer.save()
                
                return {
                    'success': True,
                    'developer_id': str(developer.id),
                    'teams': developer_teams,
                    'organizations': developer_orgs
                }
            else:
                return {
                    'success': False,
                    'error': f'Developer not found for GitHub username: {github_username}'
                }
                
        except Exception as e:
            logger.error(f"Error syncing teams for {github_username}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _find_developer_by_github_username(self, github_username: str) -> Optional[Developer]:
        """Find developer in MongoDB by GitHub username - IMPROVED VERSION"""
        try:
            # Try exact match first
            aliases = DeveloperAlias.objects.filter(name__iexact=github_username)
            if aliases:
                return aliases.first().developer
            
            # Try searching in email (case-insensitive)
            aliases = DeveloperAlias.objects.filter(email__icontains=github_username.lower())
            if aliases:
                return aliases.first().developer
            
            # Try comprehensive alternative patterns
            alternative_patterns = [
                # Convert patrick.degheil to different formats
                github_username.replace('.', ' ').title(),    # Patrick Degheil
                github_username.replace('.', ' '),            # patrick degheil  
                github_username.replace('.', ''),             # patrickdegheil
                github_username.replace('_', ' ').title(),    # Patrick Degheil (from patrick_degheil)
                github_username.replace('_', ' '),            # patrick degheil
                github_username.replace('-', ' ').title(),    # Patrick Degheil (from patrick-degheil)
                github_username.replace('-', ' '),            # patrick degheil
                github_username.title(),                      # PatrickDegheil (from patrickdegheil)
                github_username.upper(),                      # PATRICK.DEGHEIL
                github_username.lower(),                      # patrick.degheil
            ]
            
            # Add reverse patterns (if name has spaces, try with dots/underscores)
            if ' ' in github_username:
                alternative_patterns.extend([
                    github_username.replace(' ', '.').lower(),   # Patrick Degheil -> patrick.degheil
                    github_username.replace(' ', '_').lower(),   # Patrick Degheil -> patrick_degheil
                    github_username.replace(' ', '-').lower(),   # Patrick Degheil -> patrick-degheil
                    github_username.replace(' ', '').lower(),    # Patrick Degheil -> patrickdegheil
                ])
            
            for pattern in alternative_patterns:
                # Try exact match
                aliases = DeveloperAlias.objects.filter(name__iexact=pattern)
                if aliases:
                    developer = aliases.first().developer
                    if developer:
                        logger.info(f"Found developer {developer.primary_name} using exact pattern '{pattern}' for GitHub username '{github_username}'")
                        return developer
                
                # Try contains match (for partial matches)
                aliases = DeveloperAlias.objects.filter(name__icontains=pattern)
                if aliases:
                    developer = aliases.first().developer
                    if developer:
                        logger.info(f"Found developer {developer.primary_name} using partial pattern '{pattern}' for GitHub username '{github_username}'")
                        return developer
            
            logger.warning(f"No developer found for GitHub username: {github_username}")
            return None
            
        except Exception as e:
            logger.error(f"Error searching for {github_username}: {e}")
            return None
    
    def sync_all_developers_teams(self) -> Dict:
        """Sync teams for all developers - ULTRA OPTIMIZED VERSION"""
        try:
            if not self.token:
                return {
                    'success': False,
                    'error': 'No GitHub token available'
                }
            
            logger.info("Starting ULTRA OPTIMIZED GitHub teams sync...")
            
            # Step 1: Get all developers with organizations from commits (NO API CALLS)
            developers_with_orgs = []
            all_developers = Developer.objects.all()  # Process all developers
            
            logger.info(f"Processing {all_developers.count()} developers...")
            
            for i, developer in enumerate(all_developers):
                try:
                    logger.info(f"Processing developer {i+1}/{all_developers.count()}: {developer.primary_name}")
                    
                    orgs = self._get_developer_organizations_from_commits(developer)
                    logger.info(f"  Found organizations: {orgs}")
                    
                    if orgs:
                        github_usernames = self._get_github_usernames(developer)
                        logger.info(f"  Found GitHub usernames: {github_usernames}")
                        
                        developers_with_orgs.append({
                            'developer': developer,
                            'organizations': orgs,
                            'github_usernames': github_usernames
                        })
                    else:
                        logger.info(f"  No organizations found for {developer.primary_name}")
                        
                except Exception as e:
                    logger.error(f"Error processing developer {developer.primary_name}: {e}")
                    continue
            
            logger.info(f"Found {len(developers_with_orgs)} developers with organizations")
            
            # Step 2: Get unique organizations (from commits, NO API)
            all_orgs = set()
            for dev_data in developers_with_orgs:
                all_orgs.update(dev_data['organizations'])
            
            logger.info(f"Organizations found in commits: {list(all_orgs)}")
            
            # Step 3: For each organization, get teams (1 API call per org)
            team_members_cache = {}  # org -> team -> members
            synced_count = 0
            
            for org_name in all_orgs:
                try:
                    logger.info(f"Getting teams for organization: {org_name}")
                    
                    # 1 API call per organization
                    teams = self.get_organization_teams(org_name)
                    logger.info(f"Found {len(teams)} teams in {org_name}")
                    
                    # 1 API call per team
                    for team in teams:
                        try:
                            team_slug = team.get('slug')
                            if not team_slug:
                                continue
                            
                            logger.info(f"Getting members for team: {team_slug}")
                            members = self.get_team_members(org_name, team_slug)
                            team_members_cache[f"{org_name}/{team_slug}"] = [m.get('login') for m in members]
                        except Exception as e:
                            logger.error(f"Error getting members for team {team_slug}: {e}")
                            continue
                            
                except Exception as e:
                    logger.error(f"Error getting teams for organization {org_name}: {e}")
                    continue
            
            # Step 4: Assign teams to developers (NO API calls)
            for dev_data in developers_with_orgs:
                developer = dev_data['developer']
                github_usernames = dev_data['github_usernames']
                organizations = dev_data['organizations']
                
                developer_teams = []
                
                for org_name in organizations:
                    for team_slug in team_members_cache:
                        if team_slug.startswith(f"{org_name}/"):
                            team_name = team_slug.split('/')[1]
                            members = team_members_cache[team_slug]
                            
                            # Method 1: Check if any of the developer's usernames are in this team
                            found_via_username = False
                            for username in github_usernames:
                                if username in members:
                                    if team_name not in developer_teams:
                                        developer_teams.append(team_name)
                                    logger.info(f"✅ {developer.primary_name} ({username}) is in team {team_name} [via username]")
                                    found_via_username = True
                                    break
                            
                            # Method 2: Check each team member against developer aliases (if not found above)
                            if not found_via_username:
                                for github_member in members:
                                    matching_dev = self._find_developer_by_github_username(github_member)
                                    if matching_dev and matching_dev.id == developer.id:
                                        if team_name not in developer_teams:
                                            developer_teams.append(team_name)
                                        logger.info(f"✅ {developer.primary_name} found in team {team_name} via GitHub member '{github_member}' [via reverse lookup]")
                                        break
                
                # Update developer
                if developer_teams:
                    developer.github_teams = developer_teams
                    developer.github_organizations = organizations
                    developer.primary_team = developer_teams[0]
                    developer.save()
                    synced_count += 1
                    logger.info(f"✅ Updated {developer.primary_name} with teams: {developer_teams}")
                else:
                    developer.github_teams = []
                    developer.github_organizations = organizations
                    developer.primary_team = ""
                    developer.save()
                    logger.info(f"⚠️ {developer.primary_name} has no teams")
            
            logger.info(f"Sync completed. Synced: {synced_count}/{len(developers_with_orgs)}")
            
            return {
                'success': True,
                'synced_count': synced_count,
                'total_developers': len(developers_with_orgs),
                'errors': []
            }
            
        except Exception as e:
            logger.error(f"Error in sync_all_developers_teams: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _extract_github_username(self, alias_name: str) -> Optional[str]:
        """Extract GitHub username from alias name - IMPROVED VERSION"""
        import re
        
        # Clean the input
        cleaned = alias_name.strip()
        
        # Pattern 1: Direct GitHub username (alphanumeric + _ -)
        if re.match(r'^[a-zA-Z0-9_-]+$', cleaned):
            return cleaned
        
        # Pattern 2: Email username part
        email_match = re.match(r'^([a-zA-Z0-9_.-]+)@', cleaned)
        if email_match:
            username = email_match.group(1)
            if re.match(r'^[a-zA-Z0-9_.-]+$', username):
                return username
        
        # Pattern 3: Name with spaces -> firstname.lastname
        space_match = re.match(r'^([a-zA-Z]+)\s+([a-zA-Z]+)$', cleaned)
        if space_match:
            first = space_match.group(1).lower()
            last = space_match.group(2).lower()
            return f"{first}.{last}"
        
        # Pattern 4: Already has dots (patrick.degheil)
        if re.match(r'^[a-zA-Z0-9._-]+$', cleaned) and '.' in cleaned:
            return cleaned.lower()
        
        # Pattern 5: Remove spaces and convert to lowercase
        no_spaces = re.sub(r'\s+', '', cleaned).lower()
        if re.match(r'^[a-zA-Z0-9_-]+$', no_spaces):
            return no_spaces
        
        return None
    
    def _get_github_usernames(self, developer) -> List[str]:
        """Get all GitHub usernames for a developer"""
        usernames = []
        aliases = DeveloperAlias.objects.filter(developer=developer)
        
        for alias in aliases:
            username = self._extract_github_username(alias.name)
            if username:
                usernames.append(username)
        
        return usernames
    
    def _get_developer_organizations_from_commits(self, developer) -> List[str]:
        """Get organizations a developer belongs to based on their commits"""
        from analytics.models import Commit
        
        # Get all commits by this developer (through aliases)
        aliases = DeveloperAlias.objects.filter(developer=developer)
        
        organizations = set()
        
        for alias in aliases:
            # Get commits by this alias (case-insensitive search)
            commits = Commit.objects.filter(
                author_name__iexact=alias.name,
                author_email=alias.email
            )
            
            # If no commits found with email, try without email constraint
            if not commits:
                commits = Commit.objects.filter(author_name__iexact=alias.name)
            
            for commit in commits:
                # Extract organization from repository_full_name
                if commit.repository_full_name and '/' in commit.repository_full_name:
                    org_name = commit.repository_full_name.split('/')[0]
                    organizations.add(org_name)
        
        return list(organizations)
    
    def get_teams_summary(self) -> Dict:
        """Get summary of all teams and their members"""
        try:
            # Get all developers with team information
            developers = Developer.objects.filter(github_teams__exists=True)
            
            teams_summary = {}
            
            for developer in developers:
                for team in developer.github_teams:
                    if team not in teams_summary:
                        teams_summary[team] = []
                    
                    teams_summary[team].append({
                        'id': str(developer.id),
                        'name': developer.primary_name,
                        'email': developer.primary_email,
                        'primary_team': developer.primary_team == team
                    })
            
            # Sort teams alphabetically
            sorted_teams = dict(sorted(teams_summary.items()))
            
            return {
                'success': True,
                'teams': sorted_teams,
                'total_teams': len(sorted_teams),
                'total_developers': len(developers)
            }
            
        except Exception as e:
            logger.error(f"Error getting teams summary: {e}")
            return {
                'success': False,
                'error': str(e)
            } 