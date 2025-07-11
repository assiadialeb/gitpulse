"""
Developer grouping service for identifying and grouping developers with multiple identities
"""
import re
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from difflib import SequenceMatcher
from collections import defaultdict

from .models import DeveloperGroup, DeveloperAlias, Commit


class DeveloperGroupingService:
    """Service for grouping developers with multiple usernames/emails"""
    
    def __init__(self, application_id: int):
        self.application_id = application_id
    
    def group_developers(self) -> Dict:
        """
        Group developers using multiple strategies
        
        Returns:
            Dictionary with grouping results
        """
        # Get all unique developers from commits
        commits = Commit.objects.filter(application_id=self.application_id)
        developers = self._extract_unique_developers(commits)
        
        # Apply grouping strategies
        groups = self._apply_grouping_strategies(developers)
        
        # Create or update developer groups
        created_groups = self._create_developer_groups(groups)
        
        return {
            'total_developers': len(developers),
            'groups_created': len(created_groups),
            'groups': created_groups
        }
    
    def _extract_unique_developers(self, commits) -> List[Dict]:
        """Extract unique developers from commits"""
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
    
    def _apply_grouping_strategies(self, developers: List[Dict]) -> List[List[Dict]]:
        """Apply multiple strategies to group developers with proper merging"""
        # Start with each developer in their own group
        groups = [[dev] for dev in developers]
        
        # Keep merging groups until no more merges are possible
        merged = True
        while merged:
            merged = False
            
            for i in range(len(groups)):
                if not groups[i]:  # Skip empty groups
                    continue
                    
                for j in range(i + 1, len(groups)):
                    if not groups[j]:  # Skip empty groups
                        continue
                    
                    # Check if groups i and j should be merged
                    if self._should_merge_groups(groups[i], groups[j]):
                        # Merge group j into group i
                        groups[i].extend(groups[j])
                        groups[j] = []  # Mark as merged
                        merged = True
                        break
                
                if merged:
                    break
            
            # Remove empty groups
            groups = [group for group in groups if group]
        
        return groups
    
    def _should_merge_groups(self, group1: List[Dict], group2: List[Dict]) -> bool:
        """Check if two groups should be merged based on any developer in either group"""
        for dev1 in group1:
            for dev2 in group2:
                if (self._same_email_different_name(dev1, dev2) or
                    self._email_domain_username_match(dev1, dev2) or
                    self._name_similarity_match(dev1, dev2) or
                    self._github_id_match(dev1, dev2)):
                    return True
        return False
    
    def _same_email_different_name(self, dev1: Dict, dev2: Dict) -> bool:
        """Check if same email but different names"""
        return (dev1['email'].lower() == dev2['email'].lower() and 
                dev1['name'].lower() != dev2['name'].lower())
    
    def _email_domain_username_match(self, dev1: Dict, dev2: Dict) -> bool:
        """Check if same email domain and similar username"""
        email1 = dev1['email'].lower()
        email2 = dev2['email'].lower()
        
        # Extract domain and username
        try:
            username1, domain1 = email1.split('@')
            username2, domain2 = email2.split('@')
            
            # Same domain
            if domain1 != domain2:
                return False
            
            # Username similarity
            similarity = SequenceMatcher(None, username1, username2).ratio()
            return similarity >= 0.7  # 70% similarity threshold
            
        except ValueError:
            return False
    
    def _name_similarity_match(self, dev1: Dict, dev2: Dict) -> bool:
        """Check if names are similar using fuzzy matching"""
        name1 = dev1['name'].lower()
        name2 = dev2['name'].lower()
        
        # Exact match - should always group same names
        if name1 == name2:
            return True
        
        # Remove common prefixes/suffixes
        name1_clean = self._clean_name(name1)
        name2_clean = self._clean_name(name2)
        
        # Calculate similarity
        similarity = SequenceMatcher(None, name1_clean, name2_clean).ratio()
        
        # Also check if one name is contained in the other
        name_contained = (name1_clean in name2_clean or name2_clean in name1_clean)
        
        return similarity >= 0.8 or name_contained
    
    def _clean_name(self, name: str) -> str:
        """Clean name for better matching"""
        # Remove common prefixes/suffixes
        prefixes = ['mr.', 'ms.', 'dr.', 'prof.']
        suffixes = ['jr.', 'sr.', 'ii', 'iii', 'iv']
        
        name_clean = name.strip()
        
        # Remove prefixes
        for prefix in prefixes:
            if name_clean.startswith(prefix):
                name_clean = name_clean[len(prefix):].strip()
        
        # Remove suffixes
        for suffix in suffixes:
            if name_clean.endswith(suffix):
                name_clean = name_clean[:-len(suffix)].strip()
        
        return name_clean
    
    def _github_id_match(self, dev1: Dict, dev2: Dict) -> bool:
        """Check if emails contain GitHub ID patterns"""
        email1 = dev1['email']
        email2 = dev2['email']
        
        # Check for GitHub ID pattern: number+username@users.noreply.github.com
        github_pattern = r'(\d+)\+([^@]+)@users\.noreply\.github\.com'
        
        match1 = re.search(github_pattern, email1)
        match2 = re.search(github_pattern, email2)
        
        if match1 and match2:
            # Same GitHub ID
            return match1.group(1) == match2.group(1)
        
        return False
    
    def _create_developer_groups(self, groups: List[List[Dict]]) -> List[Dict]:
        """Create or update developer groups in database, always scoped by application_id"""
        created_groups = []
        
        for group in groups:
            if len(group) == 1:
                # Single developer, create minimal group
                dev = group[0]
                group_obj = self._get_or_create_group(dev, dev)
                created_groups.append({
                    'primary_name': dev['name'],
                    'primary_email': dev['email'],
                    'aliases_count': 1,
                    'confidence_score': 100
                })
            else:
                # Multiple developers, find primary and create group
                primary_dev = self._find_primary_developer(group)
                group_obj = self._get_or_create_group(primary_dev, group[0])
                
                # Add all aliases
                for dev in group:
                    self._add_developer_alias(group_obj, dev)
                
                created_groups.append({
                    'primary_name': primary_dev['name'],
                    'primary_email': primary_dev['email'],
                    'aliases_count': len(group),
                    'confidence_score': self._calculate_confidence_score(group)
                })
        
        return created_groups
    
    def _find_primary_developer(self, group: List[Dict]) -> Dict:
        """Find the primary developer in a group (most commits, most recent)"""
        # Sort by commit count (descending), then by last seen (descending)
        sorted_group = sorted(group, 
                            key=lambda x: (x['commit_count'], x['last_seen']), 
                            reverse=True)
        return sorted_group[0]
    
    def _get_or_create_group(self, primary_dev: Dict, first_dev: Dict) -> DeveloperGroup:
        """Get or create a developer group, always scoped by application_id"""
        # Try to find existing group by primary email and application_id
        group = DeveloperGroup.objects.filter(
            application_id=self.application_id,
            primary_email=primary_dev['email']
        ).first()
        
        if not group:
            # Create new group
            group = DeveloperGroup(
                application_id=self.application_id,
                primary_name=primary_dev['name'],
                primary_email=primary_dev['email'],
                is_auto_grouped=True,
                confidence_score=100
            )
            group.save()
        
        return group
    
    def _add_developer_alias(self, group: DeveloperGroup, dev: Dict):
        """Add a developer alias to a group, always scoped by application_id"""
        # Check if alias already exists for this group and application
        alias = DeveloperAlias.objects.filter(
            group=group,
            email=dev['email'],
            name=dev['name']
        ).first()
        
        if not alias:
            # Create new alias
            alias = DeveloperAlias(
                group=group,
                name=dev['name'],
                email=dev['email'],
                first_seen=dev['first_seen'],
                last_seen=dev['last_seen'],
                commit_count=dev['commit_count']
            )
            alias.save()
        else:
            # Update existing alias
            alias.last_seen = max(alias.last_seen, dev['last_seen'])
            alias.commit_count += dev['commit_count']
            alias.save()
    
    def _calculate_confidence_score(self, group: List[Dict]) -> int:
        """Calculate confidence score for a group (0-100)"""
        if len(group) == 1:
            return 100
        
        # Base score based on grouping strategy
        base_score = 70
        
        # Bonus for email domain consistency
        domains = set()
        for dev in group:
            try:
                domain = dev['email'].split('@')[1]
                domains.add(domain)
            except IndexError:
                pass
        
        if len(domains) == 1:
            base_score += 20
        
        # Bonus for name similarity
        name_similarities = []
        for i, dev1 in enumerate(group):
            for dev2 in group[i+1:]:
                similarity = SequenceMatcher(None, dev1['name'], dev2['name']).ratio()
                name_similarities.append(similarity)
        
        if name_similarities:
            avg_similarity = sum(name_similarities) / len(name_similarities)
            base_score += int(avg_similarity * 10)
        
        return min(base_score, 100)
    
    def get_grouped_developers(self) -> List[Dict]:
        """Get all developers grouped by their groups, always scoped by application_id"""
        groups = DeveloperGroup.objects.filter(application_id=self.application_id)
        grouped_developers = []
        
        for group in groups:
            aliases = DeveloperAlias.objects.filter(group=group)
            
            # Calculate total stats for the group
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
        Manually group developers based on user selection
        
        Args:
            group_data: Dictionary with group information
                {
                    'primary_name': str,
                    'primary_email': str,
                    'developer_ids': List[str]  # List of developer keys to group
                }
        
        Returns:
            Dictionary with grouping results
        """
        try:
            # Get all commits for this application
            commits = Commit.objects.filter(application_id=self.application_id)
            all_developers = self._extract_unique_developers(commits)
            
            # Create mapping from developer key to developer data
            dev_key_to_data = {}
            for dev in all_developers:
                dev_key = f"{dev['name']}|{dev['email']}"
                dev_key_to_data[dev_key] = dev
            
            # Find developers to group
            developers_to_group = []
            for dev_id in group_data['developer_ids']:
                if dev_id in dev_key_to_data:
                    developers_to_group.append(dev_key_to_data[dev_id])
            
            if not developers_to_group:
                return {
                    'success': False,
                    'error': 'No valid developers found to group'
                }
            
            # Check if any of these developers are already in existing groups
            # Get all groups for this application
            existing_groups = DeveloperGroup.objects.filter(application_id=self.application_id)
            
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
            
            # Create a new group for manual grouping
            group = DeveloperGroup(
                application_id=self.application_id,
                primary_name=group_data['primary_name'],
                primary_email=group_data['primary_email'],
                is_auto_grouped=False,  # Mark as manual grouping
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