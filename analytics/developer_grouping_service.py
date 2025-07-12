"""
Developer grouping service for automatic and manual grouping of developers
"""
import re
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from difflib import SequenceMatcher
from collections import defaultdict

from .models import DeveloperGroup, DeveloperAlias, Commit


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
            # Get all commits from all applications
            commits = Commit.objects.all()
            all_developers = self._extract_unique_developers(commits)
            
            if not all_developers:
                return {
                    'success': False,
                    'error': 'No developers found to group'
                }
            
            # Track which developers have been processed
            processed_developers = set()
            groups_to_create = []
            
            # Step 1: Group by exact email match (highest priority)
            email_groups = defaultdict(list)
            for dev in all_developers:
                email_groups[dev['email'].lower()].append(dev)
            
            for email, developers in email_groups.items():
                if len(developers) > 1:
                    groups_to_create.append({
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
                    
                    groups_to_create.append({
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
                    groups_to_create.append({
                        'type': 'github_id',
                        'key': github_id,
                        'developers': developers,
                        'primary_name': developers[0]['name'],
                        'primary_email': developers[0]['email']
                    })
                    for dev in developers:
                        processed_developers.add(dev['name'] + '|' + dev['email'])
            
            # Create the groups
            created_groups = []
            for group_data in groups_to_create:
                # Check if any of these developers are already in existing groups
                existing_group = self._find_existing_group_for_developers(group_data['developers'])
                
                if existing_group:
                    # Add to existing group
                    added_count = self._add_developers_to_group(existing_group, group_data['developers'])
                    created_groups.append({
                        'group_id': str(existing_group.id),
                        'primary_name': existing_group.primary_name,
                        'primary_email': existing_group.primary_email,
                        'type': group_data['type'],
                        'key': group_data['key'],
                        'added_count': added_count,
                        'action': 'added_to_existing'
                    })
                else:
                    # Create new group
                    group = DeveloperGroup(
                        application_id=None,  # Global group
                        primary_name=group_data['primary_name'],
                        primary_email=group_data['primary_email'],
                        is_auto_grouped=True,
                        confidence_score=self._calculate_confidence_score(group_data['type'])
                    )
                    group.save()
                    
                    # Add all developers as aliases
                    for dev in group_data['developers']:
                        alias = DeveloperAlias(
                            group=group,
                            name=dev['name'],
                            email=dev['email'],
                            first_seen=dev['first_seen'],
                            last_seen=dev['last_seen'],
                            commit_count=dev['commit_count']
                        )
                        alias.save()
                    
                    created_groups.append({
                        'group_id': str(group.id),
                        'primary_name': group.primary_name,
                        'primary_email': group.primary_email,
                        'type': group_data['type'],
                        'key': group_data['key'],
                        'added_count': len(group_data['developers']),
                        'action': 'created_new'
                    })
            
            return {
                'success': True,
                'groups_created': len(created_groups),
                'groups': created_groups
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
    
    def _calculate_confidence_score(self, group_type: str) -> int:
        """Calculate confidence score based on grouping type"""
        if group_type == 'email':
            return 100  # Exact email match
        elif group_type == 'name':
            return 80   # Name match (could be different people with same name)
        elif group_type == 'github_id':
            return 90   # GitHub ID match
        else:
            return 50
    
    def _find_existing_group_for_developers(self, developers: List[Dict]) -> Optional[DeveloperGroup]:
        """Find if any of these developers are already in an existing group or if there's a group with the same name"""
        # First check if any developer is already in an existing group
        for dev in developers:
            existing_alias = DeveloperAlias.objects.filter(
                email=dev['email'],
                name=dev['name']
            ).first()
            
            if existing_alias:
                return existing_alias.group
        
        # If no existing group found, check if there's a group with the same primary name
        if developers:
            # Use the first developer's name as reference
            primary_name = developers[0]['name']
            existing_group = DeveloperGroup.objects.filter(primary_name=primary_name).first()
            if existing_group:
                return existing_group
        
        return None
    
    def _add_developers_to_group(self, group: DeveloperGroup, developers: List[Dict]) -> int:
        """Add developers to an existing group, return number of new aliases added"""
        added_count = 0
        
        for dev in developers:
            # Check if this alias already exists in the group
            existing_alias = DeveloperAlias.objects.filter(
                group=group,
                email=dev['email'],
                name=dev['name']
            ).first()
            
            if not existing_alias:
                alias = DeveloperAlias(
                    group=group,
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
        groups = DeveloperGroup.objects.all()  # Get all groups, not filtered by application
        grouped_developers = []
        
        for group in groups:
            aliases = DeveloperAlias.objects.filter(group=group)
            
            # Calculate total stats for the group across all applications
            total_commits = sum(alias.commit_count for alias in aliases)
            
            # Sort aliases by name
            sorted_aliases = sorted(aliases, key=lambda x: x.name.lower())
            
            grouped_developers.append({
                'group_id': str(group.id),
                'primary_name': group.primary_name,
                'primary_email': group.primary_email,
                'github_id': group.github_id,
                'confidence_score': group.confidence_score,
                'is_auto_grouped': group.is_auto_grouped,
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
        
        # Sort groups by primary name (case-insensitive)
        grouped_developers.sort(key=lambda x: x['primary_name'].lower())
        
        return grouped_developers
    
    def manually_group_developers(self, group_data: Dict) -> Dict:
        """
        Manually group developers based on user selection (global grouping)
        
        Args:
            group_data: Dictionary with group information
                {
                    'primary_name': str,
                    'primary_email': str,
                    'developer_ids': List[str],  # List of developer keys to group
                    'existing_group_id': str,    # Optional: ID of existing group to add to
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
            print(f"DEBUG: Looking for {len(group_data['developer_ids'])} developers")
            print(f"DEBUG: Available developers in DB: {len(all_developers)}")
            
            for dev_id in group_data['developer_ids']:
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
            
            # Check if any of these developers are already in existing groups
            # Get all groups (global)
            existing_groups = DeveloperGroup.objects.all()
            
            # Check for conflicts
            for dev in developers_to_group:
                # Check if this developer is already in any group
                for existing_group in existing_groups:
                    existing_alias = DeveloperAlias.objects.filter(
                        group=existing_group,
                        email=dev['email'],
                        name=dev['name']
                    ).first()
                    
                    if existing_alias:
                        return {
                            'success': False,
                            'error': f'Developer {dev["name"]} ({dev["email"]}) is already grouped in another group'
                        }
            
            # Determine action: create new group or add to existing
            action = group_data.get('action', 'create')
            existing_group_id = group_data.get('existing_group_id')
            
            if action == 'add_to_existing' and existing_group_id:
                # Add developers to existing group
                try:
                    existing_group = DeveloperGroup.objects.get(id=existing_group_id)
                    
                    # Add all developers as aliases to the existing group
                    added_count = 0
                    for dev in developers_to_group:
                        # Check if this alias already exists in the group
                        existing_alias = DeveloperAlias.objects.filter(
                            group=existing_group,
                            email=dev['email'],
                            name=dev['name']
                        ).first()
                        
                        if not existing_alias:
                            alias = DeveloperAlias(
                                group=existing_group,
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
                        'group_id': str(existing_group.id),
                        'primary_name': existing_group.primary_name,
                        'primary_email': existing_group.primary_email,
                        'aliases_count': added_count,
                        'message': f'Successfully added {added_count} developers to existing group "{existing_group.primary_name}"',
                        'confidence_score': existing_group.confidence_score
                    }
                    
                except DeveloperGroup.DoesNotExist:
                    return {
                        'success': False,
                        'error': f'Existing group with ID {existing_group_id} not found'
                    }
            else:
                # Create a new group for manual grouping (no application_id)
                group = DeveloperGroup(
                    application_id=None,  # Global group
                    primary_name=group_data['primary_name'],
                    primary_email=group_data['primary_email'],
                    is_auto_grouped=False,  # Manual grouping
                    confidence_score=100  # Manual grouping has 100% confidence
                )
                group.save()
                
                # Add all developers as aliases
                for dev in developers_to_group:
                    alias = DeveloperAlias(
                        group=group,
                        name=dev['name'],
                        email=dev['email'],
                        first_seen=dev['first_seen'],
                        last_seen=dev['last_seen'],
                        commit_count=dev['commit_count']
                    )
                    alias.save()
                
                return {
                    'success': True,
                    'group_id': str(group.id),
                    'primary_name': group.primary_name,
                    'primary_email': group.primary_email,
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

    def merge_existing_groups(self) -> Dict:
        """
        Merge existing groups that should be combined based on email or name similarity
        """
        try:
            # Get all existing groups
            existing_groups = DeveloperGroup.objects.all()
            
            # Find groups to merge
            groups_to_merge = []
            
            for i, group1 in enumerate(existing_groups):
                for j, group2 in enumerate(existing_groups[i+1:], i+1):
                    # Check if groups should be merged
                    should_merge = False
                    merge_reason = ""
                    
                    # Check by email
                    if group1.primary_email.lower() == group2.primary_email.lower():
                        should_merge = True
                        merge_reason = "same_email"
                    # Check by name similarity
                    elif self._names_are_similar(group1.primary_name, group2.primary_name):
                        should_merge = True
                        merge_reason = "similar_name"
                    
                    if should_merge:
                        groups_to_merge.append({
                            'group1': group1,
                            'group2': group2,
                            'reason': merge_reason
                        })
            
            # Merge the groups
            merged_count = 0
            for merge_data in groups_to_merge:
                group1 = merge_data['group1']
                group2 = merge_data['group2']
                
                # Move all aliases from group2 to group1
                aliases_to_move = DeveloperAlias.objects.filter(group=group2)
                moved_count = 0
                
                for alias in aliases_to_move:
                    # Check if this alias already exists in group1
                    existing_alias = DeveloperAlias.objects.filter(
                        group=group1,
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
                        # Move alias to group1
                        alias.group = group1
                        alias.save()
                        moved_count += 1
                
                # Delete group2
                group2.delete()
                merged_count += 1
            
            return {
                'success': True,
                'groups_merged': merged_count
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Error merging groups: {str(e)}'
            } 