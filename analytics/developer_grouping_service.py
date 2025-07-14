"""
Developer grouping service for automatic and manual grouping of developers
"""
import re
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from difflib import SequenceMatcher
from collections import defaultdict

from .models import Developer, DeveloperAlias, Commit


class DeveloperGroupingService:
    """Service for automatic and manual grouping of developers with multiple usernames/emails"""
    
    def __init__(self, application_id: int = None):
        # application_id is kept for backward compatibility but not used for grouping
        self.application_id = application_id
    
    def auto_group_developers(self) -> Dict:
        """
        Automatically group developers based on:
        1. Same email address
        2. Same developer name (case-insensitive)
        3. Same GitHub ID
        
        Returns:
            Dictionary with grouping results
        """
        try:
            # Get all existing aliases (not commits)
            all_aliases = DeveloperAlias.objects.all()
            
            if not all_aliases:
                return {
                    'success': False,
                    'error': 'No aliases found to group'
                }
            
            # Convert aliases to developer data format
            all_developers = []
            for alias in all_aliases:
                if not alias.developer:  # Only process ungrouped aliases
                    all_developers.append({
                        'name': alias.name,
                        'email': alias.email,
                        'first_seen': alias.first_seen,
                        'last_seen': alias.last_seen,
                        'commit_count': alias.commit_count,
                        'alias_id': str(alias.id)
                    })
            
            if not all_developers:
                return {
                    'success': True,
                    'developers_created': 0,
                    'developers': [],
                    'message': 'All aliases are already grouped'
                }
            
            # Track which developers have been processed
            processed_developers = set()
            developers_to_create = []
            created_developers = []
            
            # Step 1: Group by exact email match (highest priority)
            email_groups = defaultdict(list)
            for dev in all_developers:
                email_groups[dev['email'].lower()].append(dev)
            
            for email, developers in email_groups.items():
                if len(developers) > 1:
                    # Check if any of these developers are already in existing developers
                    existing_developer = self._find_existing_developer_for_developers(developers)
                    
                    if existing_developer:
                        # Add to existing developer
                        added_count = self._add_developers_to_developer(existing_developer, developers)
                        created_developers.append({
                            'developer_id': str(existing_developer.id),
                            'primary_name': existing_developer.primary_name,
                            'primary_email': existing_developer.primary_email,
                            'type': 'email',
                            'key': email,
                            'added_count': added_count,
                            'action': 'added_to_existing'
                        })
                    else:
                        # Create new developer
                        developers_to_create.append({
                            'type': 'email',
                            'key': email,
                            'developers': developers,
                            'primary_name': developers[0]['name'],
                            'primary_email': email
                        })
                    
                    for dev in developers:
                        processed_developers.add(dev['name'] + '|' + dev['email'])
            
            # Step 2: Group by name similarity (only unprocessed developers)
            name_groups = defaultdict(list)
            for dev in all_developers:
                dev_key = dev['name'] + '|' + dev['email']
                if dev_key not in processed_developers:
                    normalized_name = self._normalize_name(dev['name'])
                    name_groups[normalized_name].append(dev)
            
            for normalized_name, developers in name_groups.items():
                if len(developers) > 1:
                    # Use the most common name as the primary name
                    name_counts = defaultdict(int)
                    for dev in developers:
                        name_counts[dev['name']] += 1
                    
                    # Use the name with the most occurrences, or the longest if tied
                    primary_name = max(name_counts.items(), key=lambda x: (x[1], len(x[0])))[0]
                    
                    developers_to_create.append({
                        'type': 'name',
                        'key': normalized_name,
                        'developers': developers,
                        'primary_name': primary_name,
                        'primary_email': developers[0]['email']
                    })
                    for dev in developers:
                        processed_developers.add(dev['name'] + '|' + dev['email'])
            
            # Step 3: Group by GitHub ID (only unprocessed developers)
            github_groups = defaultdict(list)
            for dev in all_developers:
                dev_key = dev['name'] + '|' + dev['email']
                if dev_key not in processed_developers:
                    github_id = self._extract_github_id(dev['email'])
                    if github_id:
                        github_groups[github_id].append(dev)
            
            for github_id, developers in github_groups.items():
                if len(developers) > 1:
                    developers_to_create.append({
                        'type': 'github_id',
                        'key': github_id,
                        'developers': developers,
                        'primary_name': developers[0]['name'],
                        'primary_email': developers[0]['email']
                    })
                    for dev in developers:
                        processed_developers.add(dev['name'] + '|' + dev['email'])
            
            # Create the developers
            for developer_data in developers_to_create:
                # Check if any of these developers are already in existing developers
                existing_developer = self._find_existing_developer_for_developers(developer_data['developers'])
                
                if existing_developer:
                    # Add to existing developer
                    added_count = self._add_developers_to_developer(existing_developer, developer_data['developers'])
                    created_developers.append({
                        'developer_id': str(existing_developer.id),
                        'primary_name': existing_developer.primary_name,
                        'primary_email': existing_developer.primary_email,
                        'type': developer_data['type'],
                        'key': developer_data['key'],
                        'added_count': added_count,
                        'action': 'added_to_existing'
                    })
                else:
                    # Create new developer
                    developer = Developer(
                        application_id=None,  # Global developer
                        primary_name=developer_data['primary_name'],
                        primary_email=developer_data['primary_email'],
                        is_auto_grouped=True,
                        confidence_score=self._calculate_confidence_score(developer_data['type'])
                    )
                    developer.save()
                    
                    # Link existing aliases to this developer
                    for dev in developer_data['developers']:
                        alias = DeveloperAlias.objects(id=dev['alias_id']).first()
                        if alias and not alias.developer:
                            alias.developer = developer
                            alias.save()
                    
                    created_developers.append({
                        'developer_id': str(developer.id),
                        'primary_name': developer.primary_name,
                        'primary_email': developer.primary_email,
                        'type': developer_data['type'],
                        'key': developer_data['key'],
                        'added_count': len(developer_data['developers']),
                        'action': 'created_new'
                    })
            
            # Create individual developers for ungrouped aliases
            ungrouped_count = 0
            for dev in all_developers:
                dev_key = dev['name'] + '|' + dev['email']
                if dev_key not in processed_developers:
                    # Create individual developer for this alias
                    developer = Developer(
                        application_id=None,
                        primary_name=dev['name'],
                        primary_email=dev['email'],
                        is_auto_grouped=True,
                        confidence_score=100
                    )
                    developer.save()
                    
                    # Link the alias to this developer
                    alias = DeveloperAlias.objects(id=dev['alias_id']).first()
                    if alias and not alias.developer:
                        alias.developer = developer
                        alias.save()
                        ungrouped_count += 1
            
            return {
                'success': True,
                'developers_created': len(created_developers) + ungrouped_count,
                'developers': created_developers,
                'ungrouped_individuals': ungrouped_count
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Error in auto-grouping: {str(e)}'
            }
    
    def _normalize_name(self, name: str) -> str:
        """Normalize a name for comparison (lowercase, remove extra spaces)"""
        return ' '.join(name.lower().split())
    
    def _names_are_similar(self, name1: str, name2: str) -> bool:
        """Check if two names are similar (one contains the other or vice versa)"""
        norm1 = self._normalize_name(name1)
        norm2 = self._normalize_name(name2)
        
        # Exact match
        if norm1 == norm2:
            return True
        
        # One name contains the other
        if norm1 in norm2 or norm2 in norm1:
            return True
        
        # Check if they share significant words (for cases like "John Doe" vs "Doe")
        words1 = set(norm1.split())
        words2 = set(norm2.split())
        
        # If they share at least one significant word (3+ characters)
        significant_words1 = {w for w in words1 if len(w) >= 3}
        significant_words2 = {w for w in words2 if len(w) >= 3}
        
        if significant_words1 & significant_words2:
            return True
        
        return False
    
    def _extract_github_id(self, email: str) -> Optional[str]:
        """Extract GitHub ID from email if it's a GitHub noreply email"""
        # GitHub noreply emails: 123456789+username@users.noreply.github.com
        noreply_match = re.match(r'(\d+)\+([^@]+)@users\.noreply\.github\.com', email)
        if noreply_match:
            return noreply_match.group(2)
        
        # Regular GitHub emails: username@users.noreply.github.com
        github_match = re.match(r'([^@]+)@users\.noreply\.github\.com', email)
        if github_match:
            return github_match.group(1)
        
        return None
    
    def _calculate_confidence_score(self, developer_type: str) -> int:
        """Calculate confidence score based on grouping type"""
        if developer_type == 'email':
            return 100  # Exact email match
        elif developer_type == 'name':
            return 80   # Name match (could be different people with same name)
        elif developer_type == 'github_id':
            return 90   # GitHub ID match
        else:
            return 50
    
    def _find_existing_developer_for_developers(self, developers: List[Dict]) -> Optional[Developer]:
        """Find if any of these developers are already in an existing developer"""
        # Check if any developer email is already in any existing developer
        for dev in developers:
            # Chercher dans TOUS les developers existants par email
            existing_alias = DeveloperAlias.objects.filter(
                email=dev['email']  # Chercher par email seulement
            ).first()
            
            if existing_alias:
                return existing_alias.developer
        
        # Si aucun developer trouvé par email, chercher par nom similaire
        if developers:
            # Use the first developer's name as reference
            primary_name = developers[0]['name']
            existing_developer = Developer.objects.filter(primary_name=primary_name).first()
            if existing_developer:
                return existing_developer
        
        return None
    
    def _add_developers_to_developer(self, developer: Developer, developers: List[Dict]) -> int:
        """Add developers to an existing developer, return number of new aliases added"""
        added_count = 0
        
        for dev in developers:
            # Check if this alias already exists in the developer
            existing_alias = DeveloperAlias.objects.filter(
                developer=developer,
                email=dev['email'],
                name=dev['name']
            ).first()
            
            if not existing_alias:
                alias = DeveloperAlias(
                    developer=developer,
                    name=dev['name'],
                    email=dev['email'],
                    first_seen=dev['first_seen'],
                    last_seen=dev['last_seen'],
                    commit_count=dev['commit_count']
                )
                alias.save()
                added_count += 1
        
        return added_count

    def get_grouped_developers(self) -> List[Dict]:
        """Get all grouped developers (both auto and manual)"""
        developers = Developer.objects.all()  # Get all developers, not filtered by application
        grouped_developers = []
        
        for developer in developers:
            aliases = DeveloperAlias.objects.filter(developer=developer)
            
            # Calculate total stats for the developer across all applications
            total_commits = sum(alias.commit_count for alias in aliases)
            
            # Sort aliases by name
            sorted_aliases = sorted(aliases, key=lambda x: x.name.lower())
            
            grouped_developers.append({
                'developer_id': str(developer.id),
                'primary_name': developer.primary_name,
                'primary_email': developer.primary_email,
                'github_id': developer.github_id,
                'confidence_score': developer.confidence_score,
                'is_auto_grouped': developer.is_auto_grouped,
                'total_commits': total_commits,
                'aliases': [
                    {
                        'name': alias.name,
                        'email': alias.email,
                        'commit_count': alias.commit_count,
                        'first_seen': alias.first_seen,
                        'last_seen': alias.last_seen
                    }
                    for alias in sorted_aliases
                ]
            })
        
        # Sort developers by primary name (case-insensitive)
        grouped_developers.sort(key=lambda x: x['primary_name'].lower())
        
        return grouped_developers
    
    def get_grouped_developers_for_application(self, application_id: int) -> List[Dict]:
        """
        Get grouped developers that have commits in the specified application
        
        Args:
            application_id: ID of the application to filter by
            
        Returns:
            List of grouped developers with their activity in this application
        """
        # Get all commits for this application
        application_commits = Commit.objects.filter(application_id=application_id)
        
        # Get unique emails from commits in this application
        application_emails = set()
        for commit in application_commits:
            application_emails.add(commit.author_email.lower())
        
        # Get all developers and filter by emails that appear in this application
        developers = Developer.objects.all()
        grouped_developers = []
        
        for developer in developers:
            aliases = DeveloperAlias.objects.filter(developer=developer)
            
            # Filter aliases to only include those that have commits in this application
            relevant_aliases = []
            application_commit_count = 0
            
            for alias in aliases:
                if alias.email.lower() in application_emails:
                    relevant_aliases.append(alias)
                    # Count commits for this alias in this application
                    alias_commits = application_commits.filter(author_email=alias.email)
                    application_commit_count += alias_commits.count()
            
            # Only include developers that have relevant aliases
            if relevant_aliases:
                # Sort aliases by name
                sorted_aliases = sorted(relevant_aliases, key=lambda x: x.name.lower())
                
                grouped_developers.append({
                    'developer_id': str(developer.id),
                    'primary_name': developer.primary_name,
                    'primary_email': developer.primary_email,
                    'github_id': developer.github_id,
                    'confidence_score': developer.confidence_score,
                    'is_auto_grouped': developer.is_auto_grouped,
                    'total_commits': application_commit_count,  # Only commits in this application
                    'aliases': [
                        {
                            'name': alias.name,
                            'email': alias.email,
                            'commit_count': application_commits.filter(author_email=alias.email).count(),
                            'first_seen': alias.first_seen,
                            'last_seen': alias.last_seen
                        }
                        for alias in sorted_aliases
                    ]
                })
        
        # Sort developers by primary name (case-insensitive)
        grouped_developers.sort(key=lambda x: x['primary_name'].lower())
        
        return grouped_developers
    
    def get_all_developers_for_application(self, application_id: int) -> List[Dict]:
        """
        Get all developers (both grouped and ungrouped) for a specific application
        
        Args:
            application_id: ID of the application to filter by
            
        Returns:
            List of all developers with their activity in this application
        """
        # Get all commits for this application
        application_commits = Commit.objects.filter(application_id=application_id)
        
        # Get unique emails from commits in this application
        application_emails = set()
        for commit in application_commits:
            application_emails.add(commit.author_email.lower())
        
        # Get all developers and filter by emails that appear in this application
        developers = Developer.objects.all()
        grouped_developers = []
        grouped_emails = set()  # Track emails that are in developers
        
        for developer in developers:
            aliases = DeveloperAlias.objects.filter(developer=developer)
            
            # Filter aliases to only include those that have commits in this application
            relevant_aliases = []
            application_commit_count = 0
            
            for alias in aliases:
                if alias.email.lower() in application_emails:
                    relevant_aliases.append(alias)
                    grouped_emails.add(alias.email.lower())  # Track this email as grouped
                    # Count commits for this alias in this application
                    alias_commits = application_commits.filter(author_email=alias.email)
                    application_commit_count += alias_commits.count()
            
            # Only include developers that have relevant aliases
            if relevant_aliases:
                # Sort aliases by name
                sorted_aliases = sorted(relevant_aliases, key=lambda x: x.name.lower())
                
                grouped_developers.append({
                    'developer_id': str(developer.id),
                    'primary_name': developer.primary_name,
                    'primary_email': developer.primary_email,
                    'github_id': developer.github_id,
                    'confidence_score': developer.confidence_score,
                    'is_auto_grouped': developer.is_auto_grouped,
                    'total_commits': application_commit_count,  # Only commits in this application
                    'aliases': [
                        {
                            'name': alias.name,
                            'email': alias.email,
                            'commit_count': application_commits.filter(author_email=alias.email).count(),
                            'first_seen': alias.first_seen,
                            'last_seen': alias.last_seen
                        }
                        for alias in sorted_aliases
                    ]
                })
        
        # Find ungrouped developers (emails that are not in any developer)
        ungrouped_emails = application_emails - grouped_emails
        
        # Create individual developer entries for ungrouped developers
        ungrouped_developers = []
        for email in ungrouped_emails:
            # Get commits for this email in this application
            email_commits = application_commits.filter(author_email=email)
            if email_commits.count() > 0:
                # Get the most common name for this email
                name_counts = {}
                for commit in email_commits:
                    name = commit.author_name
                    name_counts[name] = name_counts.get(name, 0) + 1
                
                # Use the most common name
                most_common_name = max(name_counts.items(), key=lambda x: x[1])[0]
                
                ungrouped_developers.append({
                    'developer_id': None,  # No developer
                    'primary_name': most_common_name,
                    'primary_email': email,
                    'github_id': None,
                    'confidence_score': 100,  # Individual developer
                    'is_auto_grouped': False,
                    'total_commits': email_commits.count(),
                    'aliases': [
                        {
                            'name': most_common_name,
                            'email': email,
                            'commit_count': email_commits.count(),
                            'first_seen': email_commits.order_by('authored_date').first().authored_date,
                            'last_seen': email_commits.order_by('-authored_date').first().authored_date
                        }
                    ]
                })
        
        # Combine grouped and ungrouped developers
        all_developers = grouped_developers + ungrouped_developers
        
        # Sort by primary name (case-insensitive)
        all_developers.sort(key=lambda x: x['primary_name'].lower())
        
        return all_developers
    
    def manually_group_developers(self, developer_data: Dict) -> Dict:
        """
        Manually group developers based on user selection (global grouping)
        
        Args:
            developer_data: Dictionary with developer information
                {
                    'primary_name': str,
                    'primary_email': str,
                    'developer_ids': List[str],  # List of developer keys to group
                    'existing_developer_id': str,    # Optional: ID of existing developer to add to
                    'action': str                # 'create' or 'add_to_existing'
                }
        
        Returns:
            Dictionary with grouping results
        """
        try:
            # Get all commits from all applications
            commits = Commit.objects.all()
            all_developers = self._extract_unique_developers(commits)
            
            # Create mapping from developer key to developer data
            dev_key_to_data = {}
            for dev in all_developers:
                dev_key = f"{dev['name']}|{dev['email']}"
                dev_key_to_data[dev_key] = dev
            
            # Find developers to group
            developers_to_group = []
            print(f"DEBUG: Looking for {len(developer_data['developer_ids'])} developers")
            print(f"DEBUG: Available developers in DB: {len(all_developers)}")
            
            for dev_id in developer_data['developer_ids']:
                print(f"DEBUG: Processing dev_id: {dev_id}")
                # Try exact match first
                if dev_id in dev_key_to_data:
                    developers_to_group.append(dev_key_to_data[dev_id])
                    print(f"DEBUG: Found exact match for {dev_id}")
                else:
                    # Try to find by parsing the developer key
                    try:
                        name, email = dev_id.split('|', 1)
                        print(f"DEBUG: Parsed name='{name}', email='{email}'")
                        # Try to find by name and email (case-insensitive)
                        found = False
                        for dev in all_developers:
                            if (dev['name'].lower().strip() == name.lower().strip() and 
                                dev['email'].lower().strip() == email.lower().strip()):
                                developers_to_group.append(dev)
                                print(f"DEBUG: Found case-insensitive match for {dev_id}")
                                found = True
                                break
                        if not found:
                            print(f"DEBUG: No match found for {dev_id}")
                    except ValueError as e:
                        # Invalid format, skip
                        print(f"DEBUG: Invalid format for {dev_id}: {e}")
                        continue
            
            print(f"DEBUG: Found {len(developers_to_group)} developers to group")
            
            if not developers_to_group:
                return {
                    'success': False,
                    'error': 'No valid developers found to group'
                }
            
            # Check if any of these developers are already in existing developers
            # Get all developers (global)
            existing_developers = Developer.objects.all()
            
            # Check for conflicts
            for dev in developers_to_group:
                # Check if this developer is already in any developer
                for existing_developer in existing_developers:
                    existing_alias = DeveloperAlias.objects.filter(
                        developer=existing_developer,
                        email=dev['email'],
                        name=dev['name']
                    ).first()
                    
                    if existing_alias:
                        return {
                            'success': False,
                            'error': f'Developer {dev["name"]} ({dev["email"]}) is already grouped in another developer'
                        }
            
            # Determine action: create new developer or add to existing
            action = developer_data.get('action', 'create')
            existing_developer_id = developer_data.get('existing_developer_id')
            
            if action == 'add_to_existing' and existing_developer_id:
                # Add developers to existing developer
                try:
                    existing_developer = Developer.objects.get(id=existing_developer_id)
                    
                    # Add all developers as aliases to the existing developer
                    added_count = 0
                    for dev in developers_to_group:
                        # Check if this alias already exists in the developer
                        existing_alias = DeveloperAlias.objects.filter(
                            developer=existing_developer,
                            email=dev['email'],
                            name=dev['name']
                        ).first()
                        
                        if not existing_alias:
                            alias = DeveloperAlias(
                                developer=existing_developer,
                                name=dev['name'],
                                email=dev['email'],
                                first_seen=dev['first_seen'],
                                last_seen=dev['last_seen'],
                                commit_count=dev['commit_count']
                            )
                            alias.save()
                            added_count += 1
                    
                    return {
                        'success': True,
                        'developer_id': str(existing_developer.id),
                        'primary_name': existing_developer.primary_name,
                        'primary_email': existing_developer.primary_email,
                        'aliases_count': added_count,
                        'message': f'Successfully added {added_count} developers to existing developer "{existing_developer.primary_name}"',
                        'confidence_score': existing_developer.confidence_score
                    }
                    
                except Developer.DoesNotExist:
                    return {
                        'success': False,
                        'error': f'Existing developer with ID {existing_developer_id} not found'
                    }
            else:
                # Create a new developer for manual grouping (no application_id)
                developer = Developer(
                    application_id=None,  # Global developer
                    primary_name=developer_data['primary_name'],
                    primary_email=developer_data['primary_email'],
                    is_auto_grouped=False,  # Manual grouping
                    confidence_score=100  # Manual grouping has 100% confidence
                )
                developer.save()
                
                # Add all developers as aliases
                for dev in developers_to_group:
                    alias = DeveloperAlias(
                        developer=developer,
                        name=dev['name'],
                        email=dev['email'],
                        first_seen=dev['first_seen'],
                        last_seen=dev['last_seen'],
                        commit_count=dev['commit_count']
                    )
                    alias.save()
                
                return {
                    'success': True,
                    'developer_id': str(developer.id),
                    'primary_name': developer.primary_name,
                    'primary_email': developer.primary_email,
                    'aliases_count': len(developers_to_group),
                    'confidence_score': 100
                }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Error creating manual group: {str(e)}'
            }
    
    def _extract_unique_developers(self, commits) -> List[Dict]:
        """Extract unique developers from commits (global)"""
        developers = {}
        
        for commit in commits:
            dev_key = f"{commit.author_name}|{commit.author_email}"
            if dev_key not in developers:
                developers[dev_key] = {
                    'name': commit.author_name,
                    'email': commit.author_email,
                    'first_seen': commit.authored_date,
                    'last_seen': commit.authored_date,
                    'commit_count': 0
                }
            
            developers[dev_key]['commit_count'] += 1
            developers[dev_key]['last_seen'] = max(
                developers[dev_key]['last_seen'], 
                commit.authored_date
            )
        
        return list(developers.values()) 

    def merge_existing_developers(self) -> Dict:
        """
        Merge existing developers that should be combined based on email or name similarity
        """
        try:
            # Get all existing developers
            existing_developers = Developer.objects.all()
            
            # Find developers to merge
            developers_to_merge = []
            
            for i, developer1 in enumerate(existing_developers):
                for j, developer2 in enumerate(existing_developers[i+1:], i+1):
                    # Check if developers should be merged
                    should_merge = False
                    merge_reason = ""
                    
                    # Check by email
                    if developer1.primary_email.lower() == developer2.primary_email.lower():
                        should_merge = True
                        merge_reason = "same_email"
                    # Check by name similarity
                    elif self._names_are_similar(developer1.primary_name, developer2.primary_name):
                        should_merge = True
                        merge_reason = "similar_name"
                    
                    if should_merge:
                        developers_to_merge.append({
                            'developer1': developer1,
                            'developer2': developer2,
                            'reason': merge_reason
                        })
            
            # Merge the developers
            merged_count = 0
            for merge_data in developers_to_merge:
                developer1 = merge_data['developer1']
                developer2 = merge_data['developer2']
                
                # Move all aliases from developer2 to developer1
                aliases_to_move = DeveloperAlias.objects.filter(developer=developer2)
                moved_count = 0
                
                for alias in aliases_to_move:
                    # Check if this alias already exists in developer1
                    existing_alias = DeveloperAlias.objects.filter(
                        developer=developer1,
                        email=alias.email,
                        name=alias.name
                    ).first()
                    
                    if existing_alias:
                        # Update existing alias
                        existing_alias.commit_count += alias.commit_count
                        existing_alias.last_seen = max(existing_alias.last_seen, alias.last_seen)
                        existing_alias.save()
                        alias.delete()
                    else:
                        # Move alias to developer1
                        alias.developer = developer1
                        alias.save()
                        moved_count += 1
                
                # Delete developer2
                developer2.delete()
                merged_count += 1
            
            return {
                'success': True,
                'developers_merged': merged_count
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Error merging developers: {str(e)}'
            } 