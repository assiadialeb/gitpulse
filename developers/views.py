"""
Views for developers app
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, Http404
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from analytics.models import Developer, DeveloperAlias

from analytics.commit_classifier import get_commit_type_stats
from .github_teams_service import GitHubTeamsService





@login_required
def list_developers(request):
    """List all developers with simple search functionality and tabs"""
    # Get tab parameter
    active_tab = request.GET.get('tab', 'teams')
    
    print(f"DEBUG: active_tab = {active_tab}")  # Debug log
    
    if active_tab == 'teams':
        print("DEBUG: Calling list_teams")  # Debug log
        return list_teams(request)
    elif active_tab == 'aliases':
        print("DEBUG: Calling list_aliases")  # Debug log
        return list_aliases(request)
    
    # Get all developers from MongoDB
    developers = Developer.objects.all().order_by('primary_name')
    
    # Simple search filter
    search_query = request.GET.get('search', '').strip()
    if search_query:
        # For MongoDB, we need to use a different approach
        developers = developers.filter(
            primary_name__icontains=search_query
        )
    
    # Add aliases for each developer
    developers_list = list(developers)  # Convert to list to ensure we can modify
    for developer in developers_list:
        aliases = DeveloperAlias.objects.filter(developer=developer)
        # Only show aliases with different emails than the primary email
        different_emails = []
        for alias in aliases:
            if alias.email.lower() != developer.primary_email.lower():
                different_emails.append(alias.email)
        developer.aliases_list = different_emails
    
    context = {
        'developers': developers_list,
        'search_query': search_query,
        'total_count': len(developers_list),
        'active_tab': active_tab,
    }
    
    return render(request, 'developers/list.html', context)


@login_required
def list_aliases(request):
    """List all unique identities from commits only (with emails)"""
    from analytics.models import Commit
    
    # Get search query
    search_query = request.GET.get('search', '').strip()
    
    # Collect all unique identities from commits only
    identities = set()
    
    # From Commits - use aggregation to get unique author combinations
    if search_query:
        # Use case-insensitive search in MongoDB
        commits_aggregation = Commit.objects.aggregate([
            {
                '$match': {
                    '$or': [
                        {'author_name': {'$regex': search_query, '$options': 'i'}},
                        {'author_email': {'$regex': search_query, '$options': 'i'}}
                    ]
                }
            },
            {
                '$group': {
                    '_id': {
                        'name': '$author_name',
                        'email': '$author_email'
                    }
                }
            }
        ])
    else:
        # Get all unique author combinations
        commits_aggregation = Commit.objects.aggregate([
            {
                '$group': {
                    '_id': {
                        'name': '$author_name',
                        'email': '$author_email'
                    }
                }
            }
        ])
    
    for commit_group in commits_aggregation:
        author_data = commit_group['_id']
        if author_data['name'] and author_data['email']:
            identities.add((author_data['name'].lower(), author_data['email'].lower(), 'Commit'))
    
    # Convert to list and deduplicate
    unique_identities = []
    seen_names = set()
    seen_emails = set()
    
    # Get existing aliases and developers using aggregation for better performance
    existing_aliases_aggregation = DeveloperAlias.objects.aggregate([
        {
            '$group': {
                '_id': {
                    'name': '$name',
                    'email': '$email'
                }
            }
        }
    ])
    
    existing_name_email_combinations = set()
    for alias_group in existing_aliases_aggregation:
        alias_data = alias_group['_id']
        if alias_data['name'] and alias_data['email']:
            existing_name_email_combinations.add((alias_data['name'].lower(), alias_data['email'].lower()))
    
    # Get existing developers
    existing_developers_aggregation = Developer.objects.aggregate([
        {
            '$group': {
                '_id': {
                    'name': '$primary_name',
                    'email': '$primary_email'
                }
            }
        }
    ])
    
    existing_developer_name_email_combinations = set()
    for dev_group in existing_developers_aggregation:
        dev_data = dev_group['_id']
        if dev_data['name'] and dev_data['email']:
            existing_developer_name_email_combinations.add((dev_data['name'].lower(), dev_data['email'].lower()))
    
    for name, email, source in identities:
        name_lower = name.lower()
        email_lower = email.lower() if email else None
        
        # Check if we already have this email in our current list (email-only deduplication)
        if email_lower and email_lower in seen_emails:
            continue
        
        # Check if this exact name+email combination already exists in developer_aliases
        if email_lower and (name_lower, email_lower) in existing_name_email_combinations:
            continue
        
        # Check if this exact name+email combination matches an existing developer's primary identity
        if email_lower and (name_lower, email_lower) in existing_developer_name_email_combinations:
            continue
        
        # Simplified filtering: Check if this email is already used anywhere
        if email_lower:
            # Check if email exists in any alias or developer
            email_in_aliases = DeveloperAlias.objects.filter(email=email_lower).count() > 0
            email_in_developers = Developer.objects.filter(primary_email=email_lower).count() > 0
            
            if email_in_aliases or email_in_developers:
                continue
        
        # Only track emails, not names (allow multiple identities with same name but different emails)
        if email_lower:
            seen_emails.add(email_lower)
        
        unique_identities.append({
            'name': name.title(),  # Capitalize first letter
            'email': email or f'No email ({source})',
            'source': source
        })
    
    # Sort by name
    unique_identities.sort(key=lambda x: x['name'])
    
    context = {
        'aliases': unique_identities,
        'search_query': search_query,
        'total_count': len(unique_identities),
        'active_tab': 'aliases',
    }
    
    return render(request, 'developers/list.html', context)





def search_developers_ajax(request):
    """AJAX endpoint for inline search"""
    # Check if user is authenticated
    if not request.user.is_authenticated:
        return JsonResponse({
            'error': 'Authentication required',
            'developers': [],
            'total_count': 0,
            'search_query': ''
        }, status=401)
    
    search_query = request.GET.get('q', '').strip()
    
    developers = Developer.objects.all().order_by('primary_name')
    
    if search_query:
        # For MongoDB, search in both name and email fields
        # We'll filter by name first, then add email matches
        name_matches = developers.filter(primary_name__icontains=search_query)
        email_matches = developers.filter(primary_email__icontains=search_query)
        
        # Combine results manually (avoid using | operator with MongoDB)
        all_developers = list(developers)
        matching_developers = []
        
        for dev in all_developers:
            name_match = search_query.lower() in (dev.primary_name or '').lower()
            email_match = search_query.lower() in (dev.primary_email or '').lower()
            if name_match or email_match:
                matching_developers.append(dev)
        
        developers = matching_developers
    else:
        developers = list(developers)
    
    # Convert to list for JSON serialization
    developers_data = []
    for dev in developers:
        # Get aliases for this developer
        aliases = DeveloperAlias.objects.filter(developer=dev)
        # Only show aliases with different emails than the primary email
        different_emails = []
        for alias in aliases:
            if alias.email.lower() != dev.primary_email.lower():
                different_emails.append(alias.email)
        
        developers_data.append({
            'id': str(dev.id),
            'name': dev.primary_name or 'Unknown',
            'email': dev.primary_email or 'No email',
            'aliases': ', '.join(different_emails) if different_emails else 'No aliases',
            'detail_url': f'/developers/{dev.id}/'
        })
    
    return JsonResponse({
        'developers': developers_data,
        'total_count': len(developers_data),
        'search_query': search_query
    })


def search_teams_ajax(request):
    """AJAX endpoint for inline teams search"""
    # Check if user is authenticated
    if not request.user.is_authenticated:
        return JsonResponse({
            'error': 'Authentication required',
            'teams': {},
            'total_count': 0,
            'search_query': ''
        }, status=401)
    
    search_query = request.GET.get('q', '').strip()
    
    # Get teams summary
    teams_service = GitHubTeamsService()
    teams_summary = teams_service.get_teams_summary()
    
    if not teams_summary['success']:
        return JsonResponse({
            'teams': {},
            'total_count': 0,
            'search_query': search_query,
            'error': 'Failed to load teams summary'
        }, status=500)
    
    teams_data = teams_summary['teams']
    
    # Filter teams based on search query
    if search_query:
        filtered_teams = {}
        for team_name, members in teams_data.items():
            # Check if team name matches
            if search_query.lower() in team_name.lower():
                filtered_teams[team_name] = members
                continue
            
            # Check if any member name matches
            for member in members:
                if (search_query.lower() in member['name'].lower() or 
                    search_query.lower() in member.get('email', '').lower()):
                    filtered_teams[team_name] = members
                    break
        
        teams_data = filtered_teams
    
    total_teams = len(teams_data)
    total_developers = sum(len(members) for members in teams_data.values())
    
    return JsonResponse({
        'teams': teams_data,
        'total_count': total_teams,
        'total_developers': total_developers,
        'search_query': search_query
    })


def search_aliases_ajax(request):
    """AJAX endpoint for inline aliases search"""
    from analytics.models import Commit
    
    # Check if user is authenticated
    if not request.user.is_authenticated:
        return JsonResponse({
            'error': 'Authentication required',
            'aliases': [],
            'total_count': 0,
            'search_query': ''
        }, status=401)
    
    search_query = request.GET.get('q', '').strip()
    
    # Collect all unique identities from commits only
    identities = set()
    
    # From Commits - use aggregation to get unique author combinations
    if search_query:
        # Use case-insensitive search in MongoDB
        commits_aggregation = Commit.objects.aggregate([
            {
                '$match': {
                    '$or': [
                        {'author_name': {'$regex': search_query, '$options': 'i'}},
                        {'author_email': {'$regex': search_query, '$options': 'i'}}
                    ]
                }
            },
            {
                '$group': {
                    '_id': {
                        'name': '$author_name',
                        'email': '$author_email'
                    }
                }
            }
        ])
    else:
        # Get all unique author combinations
        commits_aggregation = Commit.objects.aggregate([
            {
                '$group': {
                    '_id': {
                        'name': '$author_name',
                        'email': '$author_email'
                    }
                }
            }
        ])
    
    for commit_group in commits_aggregation:
        author_data = commit_group['_id']
        if author_data['name'] and author_data['email']:
            identities.add((author_data['name'].lower(), author_data['email'].lower(), 'Commit'))
    
    # Convert to list and deduplicate
    unique_identities = []
    seen_names = set()
    seen_emails = set()
    
    # Get existing aliases and developers using aggregation for better performance
    existing_aliases_aggregation = DeveloperAlias.objects.aggregate([
        {
            '$group': {
                '_id': {
                    'name': '$name',
                    'email': '$email'
                }
            }
        }
    ])
    
    existing_name_email_combinations = set()
    for alias_group in existing_aliases_aggregation:
        alias_data = alias_group['_id']
        if alias_data['name'] and alias_data['email']:
            existing_name_email_combinations.add((alias_data['name'].lower(), alias_data['email'].lower()))
    
    # Get existing developers
    existing_developers_aggregation = Developer.objects.aggregate([
        {
            '$group': {
                '_id': {
                    'name': '$primary_name',
                    'email': '$primary_email'
                }
            }
        }
    ])
    
    existing_developer_name_email_combinations = set()
    for dev_group in existing_developers_aggregation:
        dev_data = dev_group['_id']
        if dev_data['name'] and dev_data['email']:
            existing_developer_name_email_combinations.add((dev_data['name'].lower(), dev_data['email'].lower()))
    
    for name, email, source in identities:
        name_lower = name.lower()
        email_lower = email.lower() if email else None
        
        # Check if we already have this email in our current list (email-only deduplication)
        if email_lower and email_lower in seen_emails:
            continue
        
        # Check if this exact name+email combination already exists in developer_aliases
        if email_lower and (name_lower, email_lower) in existing_name_email_combinations:
            continue
        
        # Check if this exact name+email combination matches an existing developer's primary identity
        if email_lower and (name_lower, email_lower) in existing_developer_name_email_combinations:
            continue
        
        # Simplified filtering: Check if this email is already used anywhere
        if email_lower:
            # Check if email exists in any alias or developer
            email_in_aliases = DeveloperAlias.objects.filter(email=email_lower).count() > 0
            email_in_developers = Developer.objects.filter(primary_email=email_lower).count() > 0
            
            if email_in_aliases or email_in_developers:
                continue
        
        # Only track emails, not names (allow multiple identities with same name but different emails)
        if email_lower:
            seen_emails.add(email_lower)
        
        unique_identities.append({
            'name': name.title(),  # Capitalize first letter
            'email': email or f'No email ({source})',
            'source': source
        })
    
    # Sort by name
    unique_identities.sort(key=lambda x: x['name'])
    
    return JsonResponse({
        'aliases': unique_identities,
        'total_count': len(unique_identities),
        'search_query': search_query
    })


@login_required
@require_http_methods(["POST"])
def update_developer_name(request, developer_id):
    """Update developer name via AJAX"""
    try:
        from bson import ObjectId
        
        # Convert string to ObjectId
        object_id = ObjectId(developer_id)
        developer = Developer.objects(id=object_id).first()
    except (ValueError, TypeError):
        # If the ID is not a valid ObjectId, try to find by string
        developer = Developer.objects(id=developer_id).first()
    
    if developer is None:
        return JsonResponse({
            'success': False,
            'error': 'Developer not found'
        }, status=404)
    
    # Get the new name from POST data
    new_name = request.POST.get('new_name', '').strip()
    
    if not new_name:
        return JsonResponse({
            'success': False,
            'error': 'Name cannot be empty'
        }, status=400)
    
    # Update the developer name
    old_name = developer.primary_name
    developer.primary_name = new_name
    developer.save()
    
    return JsonResponse({
        'success': True,
        'message': f'Developer name updated from "{old_name}" to "{new_name}"',
        'new_name': new_name
    })


@login_required
@require_http_methods(["POST"])
def merge_developers(request):
    """Merge multiple developers into one primary developer"""
    import json
    from bson import ObjectId
    
    try:
        # Check if request body is empty
        if not request.body:
            return JsonResponse({
                'success': False,
                'error': 'Empty request body'
            }, status=400)
        
        data = json.loads(request.body)
        primary_developer_id = data.get('primary_developer_id')
        other_developer_ids = data.get('other_developer_ids', [])
        
        if not primary_developer_id or not other_developer_ids:
            return JsonResponse({
                'success': False,
                'error': 'Missing required parameters'
            }, status=400)
        
        # Get the primary developer
        try:
            primary_object_id = ObjectId(primary_developer_id)
            primary_developer = Developer.objects(id=primary_object_id).first()
        except (ValueError, TypeError):
            primary_developer = Developer.objects(id=primary_developer_id).first()
        
        if not primary_developer:
            return JsonResponse({
                'success': False,
                'error': 'Primary developer not found'
            }, status=404)
        
        # Get other developers
        other_developers = []
        for dev_id in other_developer_ids:
            try:
                object_id = ObjectId(dev_id)
                developer = Developer.objects(id=object_id).first()
            except (ValueError, TypeError):
                developer = Developer.objects(id=dev_id).first()
            
            if developer:
                other_developers.append(developer)
        
        if not other_developers:
            return JsonResponse({
                'success': False,
                'error': 'No valid developers to merge'
            }, status=400)
        
        # Perform the merge
        try:
            # For each other developer, create aliases and link them to the primary developer
            for other_dev in other_developers:
                # Create alias for the other developer's primary identity
                alias = DeveloperAlias(
                    developer=primary_developer,
                    name=other_dev.primary_name,
                    email=other_dev.primary_email,
                    first_seen=other_dev.created_at,
                    last_seen=other_dev.updated_at,
                    commit_count=0  # Will be calculated from commits
                )
                alias.save()
                
                # Move all existing aliases of the other developer to the primary developer
                existing_aliases = DeveloperAlias.objects(developer=other_dev)
                for existing_alias in existing_aliases:
                    existing_alias.developer = primary_developer
                    existing_alias.save()
                
                # Delete the other developer
                other_dev.delete()
            
            return JsonResponse({
                'success': True,
                'message': f'Successfully merged {len(other_developers)} developer(s) into {primary_developer.primary_name}'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Error during merge: {str(e)}'
            }, status=500)
            
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Unexpected error: {str(e)}'
        }, status=500)


def _calculate_detailed_quality_metrics(commits):
    """Calculate detailed quality metrics for a developer's commits"""
    if not commits:
        return {
            'total_commits': 0,
            'real_code_commits': 0,
            'real_code_ratio': 0,
            'suspicious_commits': 0,
            'suspicious_ratio': 0,
            'doc_only_commits': 0,
            'doc_only_ratio': 0,
            'config_only_commits': 0,
            'config_only_ratio': 0,
            'micro_commits': 0,
            'micro_commits_ratio': 0,
            'no_ticket_commits': 0,
            'no_ticket_ratio': 0,
            'avg_code_quality': 0,
            'avg_impact': 0,
            'avg_complexity': 0
        }
    
    total_commits = commits.count()
    real_code_commits = 0
    suspicious_commits = 0
    doc_only_commits = 0
    config_only_commits = 0
    micro_commits = 0
    no_ticket_commits = 0
    quality_scores = []
    impact_scores = []
    complexity_scores = []
    
    for commit in commits:
        # Check for real code (has code files)
        has_code_files = False
        has_doc_only = True
        has_config_only = True
        
        for file_change in commit.files_changed:
            filename = file_change.filename.lower()
            
            # Check for code files
            if any(ext in filename for ext in ['.py', '.js', '.ts', '.java', '.cpp', '.c', '.go', '.rs', '.php', '.rb']):
                has_code_files = True
                has_doc_only = False
                has_config_only = False
            
            # Check for test files
            elif any(pattern in filename for pattern in ['test', 'spec', 'specs', '_test.', '.test.']):
                has_code_files = True
                has_doc_only = False
                has_config_only = False
            
            # Check for documentation files
            elif any(ext in filename for ext in ['.md', '.txt', '.rst', '.adoc', 'readme', 'docs/', 'documentation/']):
                has_doc_only = has_doc_only and not has_code_files
            
            # Check for configuration files
            elif any(ext in filename for ext in ['.json', '.yaml', '.yml', '.toml', '.ini', '.conf', '.config', 'package.json', 'requirements.txt', 'pom.xml', 'build.gradle']):
                has_config_only = has_config_only and not has_code_files
        
        # Count different types of commits
        if has_code_files:
            real_code_commits += 1
        
        if has_doc_only:
            doc_only_commits += 1
        
        if has_config_only:
            config_only_commits += 1
        
        # Check for micro commits (≤2 changes)
        if commit.total_changes <= 2:
            micro_commits += 1
        
        # Check for no ticket reference
        if not re.search(r'#[0-9]+', commit.message):
            no_ticket_commits += 1
        
        # Detect suspicious patterns
        is_suspicious = False
        
        # Micro commit (≤1 changes, not 0)
        if commit.total_changes <= 1 and commit.total_changes > 0:
            is_suspicious = True
        
        # No ticket reference (only if project uses ticket system)
        # Commented out because most commits don't have ticket references
        # if not re.search(r'#[0-9]+', commit.message):
        #     is_suspicious = True
        
        # Only documentation (not suspicious if it's a real documentation commit)
        if has_doc_only and commit.total_changes > 5:
            is_suspicious = True
        
        # Only configuration (not suspicious if it's a real config change)
        if has_config_only and commit.total_changes > 5:
            is_suspicious = True
        
        # Formatting only (message contains format + small changes)
        if re.search(r'format|style|indent|whitespace', commit.message.lower()) and commit.total_changes <= 5:
            is_suspicious = True
        
        if is_suspicious:
            suspicious_commits += 1
        
        # Calculate quality scores (simplified)
        code_quality = 50  # Base score
        if has_code_files:
            code_quality += 40
        if commit.total_changes > 10:
            code_quality += 15
        quality_scores.append(min(100, code_quality))
        
        # Calculate impact score
        impact_score = 50  # Base score
        if commit.total_changes > 20:
            impact_score += 40
        elif commit.total_changes > 10:
            impact_score += 30
        elif commit.total_changes > 5:
            impact_score += 20
        impact_scores.append(min(100, impact_score))
        
        # Calculate complexity score
        complexity_score = 30  # Base score
        if commit.commit_type == 'feature':
            complexity_score += 40
        elif commit.commit_type == 'fix':
            complexity_score += 35
        elif commit.commit_type == 'refactor':
            complexity_score += 30
        complexity_scores.append(min(100, complexity_score))
    
    # Calculate ratios
    real_code_ratio = (real_code_commits / total_commits * 100) if total_commits > 0 else 0
    suspicious_ratio = (suspicious_commits / total_commits * 100) if total_commits > 0 else 0
    doc_only_ratio = (doc_only_commits / total_commits * 100) if total_commits > 0 else 0
    config_only_ratio = (config_only_commits / total_commits * 100) if total_commits > 0 else 0
    micro_commits_ratio = (micro_commits / total_commits * 100) if total_commits > 0 else 0
    no_ticket_ratio = (no_ticket_commits / total_commits * 100) if total_commits > 0 else 0
    
    # Calculate averages
    avg_code_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0
    avg_impact = sum(impact_scores) / len(impact_scores) if impact_scores else 0
    avg_complexity = sum(complexity_scores) / len(complexity_scores) if complexity_scores else 0
    
    return {
        'total_commits': total_commits,
        'real_code_commits': real_code_commits,
        'real_code_ratio': round(real_code_ratio, 1),
        'suspicious_commits': suspicious_commits,
        'suspicious_ratio': round(suspicious_ratio, 1),
        'doc_only_commits': doc_only_commits,
        'doc_only_ratio': round(doc_only_ratio, 1),
        'config_only_commits': config_only_commits,
        'config_only_ratio': round(config_only_ratio, 1),
        'micro_commits': micro_commits,
        'micro_commits_ratio': round(micro_commits_ratio, 1),
        'no_ticket_commits': no_ticket_commits,
        'no_ticket_ratio': round(no_ticket_ratio, 1),
        'avg_code_quality': round(avg_code_quality, 1),
        'avg_impact': round(avg_impact, 1),
        'avg_complexity': round(avg_complexity, 1)
    }


def _calculate_commit_type_distribution(commits):
    """Calculate commit type distribution for a developer, with ratios and status fields"""
    return get_commit_type_stats(commits)


def _calculate_quality_metrics_by_month(commits):
    """Calculate quality metrics by month for the last 12 months"""
    if not commits:
        return {
            'labels': [],
            'datasets': []
        }
    
    # Get commits from the last 12 months
    now = datetime.now(timezone.utc)
    months_data = {}
    
    for i in range(12):
        month_start = now - timedelta(days=30 * (i + 1))
        month_end = now - timedelta(days=30 * i)
        month_key = month_start.strftime('%Y-%m')
        
        month_commits = commits.filter(
            authored_date__gte=month_start,
            authored_date__lt=month_end
        )
        
        if month_commits.count() > 0:
            # Calculate average scores for this month
            quality_scores = []
            impact_scores = []
            complexity_scores = []
            
            for commit in month_commits:
                # Simplified quality calculation
                quality_score = 50  # Base
                if commit.total_changes > 10:
                    quality_score += 20
                quality_scores.append(min(100, quality_score))
                
                impact_score = 40  # Base
                if commit.total_changes > 20:
                    impact_score += 30
                elif commit.total_changes > 10:
                    impact_score += 20
                impact_scores.append(min(100, impact_score))
                
                complexity_score = 30  # Base
                if commit.commit_type == 'feature':
                    complexity_score += 30
                elif commit.commit_type == 'fix':
                    complexity_score += 25
                complexity_scores.append(min(100, complexity_score))
            
            months_data[month_key] = {
                'quality': sum(quality_scores) / len(quality_scores) if quality_scores else 0,
                'impact': sum(impact_scores) / len(impact_scores) if impact_scores else 0,
                'complexity': sum(complexity_scores) / len(complexity_scores) if complexity_scores else 0
            }
    
    # Sort months chronologically
    sorted_months = sorted(months_data.keys())
    
    return {
        'labels': sorted_months,
        'datasets': [
            {
                'label': 'Code Quality',
                'data': [months_data[month]['quality'] for month in sorted_months],
                'borderColor': '#10B981',
                'backgroundColor': 'rgba(16, 185, 129, 0.1)',
                'tension': 0.4
            },
            {
                'label': 'Impact Score',
                'data': [months_data[month]['impact'] for month in sorted_months],
                'borderColor': '#3B82F6',
                'backgroundColor': 'rgba(59, 130, 246, 0.1)',
                'tension': 0.4
            },
            {
                'label': 'Complexity Score',
                'data': [months_data[month]['complexity'] for month in sorted_months],
                'borderColor': '#F59E0B',
                'backgroundColor': 'rgba(245, 158, 11, 0.1)',
                'tension': 0.4
            }
        ]
    }


@login_required
def developer_detail(request, developer_id):
    """Afficher le détail d'un développeur (MongoEngine)"""
    from bson import ObjectId
    from analytics.analytics_service import AnalyticsService
    import re
    
    try:
        # Convert string to ObjectId
        object_id = ObjectId(developer_id)
        developer = Developer.objects(id=object_id).first()
    except (ValueError, TypeError):
        # If the ID is not a valid ObjectId, try to find by string
        developer = Developer.objects(id=developer_id).first()
    
    if developer is None:
        raise Http404("Developer not found")
    
    # Récupérer les alias associés
    aliases = DeveloperAlias.objects(developer=developer)
    
    # Get detailed developer stats using analytics service
    # For global developer stats, we'll use a dummy application_id
    analytics = AnalyticsService(0)  # Pass 0 for global stats
    developer_stats = analytics.get_developer_detailed_stats(str(developer.id))
    
    if developer_stats.get('success', False):
        # Create a developer object with the fields expected by the template
        developer_for_template = type('Developer', (), {
            'name': developer.primary_name,
            'email': developer.primary_email,
            'commit_count': developer_stats.get('total_commits', 0),
            'is_developer': True,
            'github_id': developer.github_id,
            'aliases': aliases
        })()
        
        # Get commits for this developer (all applications)
        from analytics.models import Commit
        alias_emails = [alias.email for alias in aliases]
        all_commits = Commit.objects.filter(author_email__in=alias_emails)

        # Calculate detailed quality metrics
        detailed_quality_metrics = _calculate_detailed_quality_metrics(all_commits)
        
        # Calculate commit type distribution
        commit_type_data = _calculate_commit_type_distribution(all_commits)
        
        # Calculate quality metrics by month
        quality_metrics_by_month = _calculate_quality_metrics_by_month(all_commits)
        
        # Format polar chart data for Chart.js
        polar_chart_data = []
        for repo in developer_stats.get('top_repositories', []):
            net_lines = repo.get('additions', 0) - repo.get('deletions', 0)
            polar_chart_data.append({
                'label': repo['name'],
                'data': [net_lines],
                'backgroundColor': f'rgba({hash(repo["name"]) % 256}, {(hash(repo["name"]) >> 8) % 256}, {(hash(repo["name"]) >> 16) % 256}, 0.6)',
                'borderColor': f'rgba({hash(repo["name"]) % 256}, {(hash(repo["name"]) >> 8) % 256}, {(hash(repo["name"]) >> 16) % 256}, 1)',
                'borderWidth': 2
            })
        if not polar_chart_data:
            polar_chart_data = []

        # --- Correction: Activity Heatmap chart_data ---
        # Only keep commits from the last 365 days
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        cutoff = now - timedelta(days=365)
        commits_365d = [c for c in all_commits if c.authored_date and c.authored_date.replace(tzinfo=None) >= cutoff]
        # Group by repo, then by (days_ago, hour)
        repo_bubbles = {}
        for commit in commits_365d:
            repo = commit.repository_full_name or 'unknown'
            # Use the robust timezone-aware method
            commit_dt = commit.get_authored_date_in_timezone()
            days_ago = (now.date() - commit_dt.date()).days
            hour = commit_dt.hour
            key = (days_ago, hour)
            if repo not in repo_bubbles:
                repo_bubbles[repo] = {}
            if key not in repo_bubbles[repo]:
                repo_bubbles[repo][key] = {'commits': 0, 'changes': 0}
            repo_bubbles[repo][key]['commits'] += 1
            repo_bubbles[repo][key]['changes'] += (commit.additions or 0) + (commit.deletions or 0)
        # Color palette (daisyUI green, blue, orange, purple, pink, etc.)
        palette = [
            {'bg': 'rgba(16, 185, 129, 0.6)', 'border': 'rgba(16, 185, 129, 1)'}, # green
            {'bg': 'rgba(59, 130, 246, 0.6)', 'border': 'rgba(59, 130, 246, 1)'}, # blue
            {'bg': 'rgba(245, 158, 11, 0.6)', 'border': 'rgba(245, 158, 11, 1)'}, # orange
            {'bg': 'rgba(139, 92, 246, 0.6)', 'border': 'rgba(139, 92, 246, 1)'}, # purple
            {'bg': 'rgba(236, 72, 153, 0.6)', 'border': 'rgba(236, 72, 153, 1)'}, # pink
            {'bg': 'rgba(34, 197, 94, 0.6)', 'border': 'rgba(34, 197, 94, 1)'},   # emerald
        ]
        chart_data = []
        for i, (repo, bubbles) in enumerate(repo_bubbles.items()):
            color = palette[i % len(palette)]
            dataset = {
                'label': repo,
                'data': [],
                'backgroundColor': color['bg'],
                'borderColor': color['border'],
                'borderWidth': 1
            }
            for (days_ago, hour), data in bubbles.items():
                dataset['data'].append({
                    'x': days_ago,
                    'y': hour,
                    'r': min(5 + data['commits'] * 2, 20),
                    'commit_count': data['commits'],
                    'changes': data['changes']
                })
            chart_data.append(dataset)
        # --- Fin correction ---

        context = {
            'developer': developer_for_template,
            'developer_id': str(developer.id),
            'aliases': aliases,
            'commit_frequency': analytics.get_developer_commit_frequency(all_commits),
            'commit_quality': developer_stats.get('commit_quality', {}),
            'quality_metrics': detailed_quality_metrics,
            'first_commit': None,  # Will be set if available
            'last_commit': None,   # Will be set if available
            'polar_chart_data': polar_chart_data,
            'quality_metrics_by_month': quality_metrics_by_month,
            'chart_data': chart_data,
            'commit_type_distribution': commit_type_data,
            'commit_type_labels': list(commit_type_data['counts'].keys()),
            'commit_type_values': list(commit_type_data['counts'].values()),
            'commit_type_legend': [
                {'label': k, 'count': v, 'color': _get_commit_type_color(k)}
                for k, v in commit_type_data['counts'].items()
            ]
        }
        # Set first and last commit if available
        if developer_stats.get('first_commit_date'):
            from analytics.models import Commit
            first_commit = Commit.objects.filter(author_email__in=[alias.email for alias in aliases]).order_by('authored_date').first()
            if first_commit:
                context['first_commit'] = first_commit
        if developer_stats.get('last_commit_date'):
            from analytics.models import Commit
            last_commit = Commit.objects.filter(author_email__in=[alias.email for alias in aliases]).order_by('-authored_date').first()
            if last_commit:
                context['last_commit'] = last_commit
    else:
        # Fallback if stats calculation fails
        developer_for_template = type('Developer', (), {
            'name': developer.primary_name,
            'email': developer.primary_email,
            'commit_count': 0,
            'is_developer': True,
            'github_id': developer.github_id,
            'aliases': aliases
        })()
        context = {
            'developer': developer_for_template,
            'developer_id': str(developer.id),
            'aliases': aliases,
            'commit_frequency': {'avg_commits_per_day': 0},
            'commit_quality': {'total_commits': 0, 'explicit_ratio': 0, 'generic_ratio': 0},
            'quality_metrics': {'total_commits': 0},
            'first_commit': None,
            'last_commit': None,
            'polar_chart_data': [],
            'quality_metrics_by_month': {'labels': [], 'datasets': []},
            'chart_data': [],
            'commit_type_distribution': {'total': 0, 'types': {}},
            'commit_type_labels': [],
            'commit_type_values': [],
            'commit_type_legend': []
        }
    return render(request, 'developers/detail.html', context)


@login_required
@require_http_methods(["POST"])
def remove_developer_alias(request, developer_id, alias_id):
    """Remove an alias from a developer via AJAX"""
    try:
        from bson import ObjectId
        
        # Convert string to ObjectId for developer
        developer_object_id = ObjectId(developer_id)
        developer = Developer.objects(id=developer_object_id).first()
        
        # Convert string to ObjectId for alias
        alias_object_id = ObjectId(alias_id)
        alias = DeveloperAlias.objects(id=alias_object_id).first()
        
    except (ValueError, TypeError):
        return JsonResponse({
            'success': False,
            'error': 'Invalid ID format'
        }, status=400)
    
    if developer is None:
        return JsonResponse({
            'success': False,
            'error': 'Developer not found'
        }, status=404)
    
    if alias is None:
        return JsonResponse({
            'success': False,
            'error': 'Alias not found'
        }, status=404)
    
    # Verify that the alias belongs to this developer
    if alias.developer != developer:
        return JsonResponse({
            'success': False,
            'error': 'Alias does not belong to this developer'
        }, status=400)
    
    # Store alias info before deletion for response
    alias_name = alias.name
    alias_email = alias.email
    
    try:
        # Disassociate the alias from the developer (don't delete it)
        alias.developer = None
        alias.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Successfully disassociated alias "{alias_name}" ({alias_email}) from developer',
            'removed_alias_id': alias_id
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error removing alias: {str(e)}'
        }, status=500)


@login_required
@require_http_methods(["POST"])
def create_developer_from_aliases(request):
    """Create a new developer from selected aliases"""
    import json
    
    try:
        # Check if request body is empty
        if not request.body:
            return JsonResponse({
                'success': False,
                'error': 'Empty request body'
            }, status=400)
        
        data = json.loads(request.body)
        developer_name = data.get('developer_name', '').strip()
        primary_email = data.get('primary_email', '').strip()
        aliases_data = data.get('aliases', [])
        is_existing = data.get('is_existing', False)
        
        if not developer_name:
            return JsonResponse({
                'success': False,
                'error': 'Developer name is required'
            }, status=400)
        
        if not aliases_data:
            return JsonResponse({
                'success': False,
                'error': 'At least one alias is required'
            }, status=400)
        
        # Check if developer already exists
        existing_developer = Developer.objects.filter(primary_name=developer_name).first()
        
        if existing_developer and not is_existing:
            return JsonResponse({
                'success': False,
                'error': f'Developer "{developer_name}" already exists'
            }, status=400)
        
        # Use the selected primary email or generate one if none selected
        if not primary_email:
            primary_email = f'{developer_name.lower()}@unknown'
        
        if existing_developer:
            # Add aliases to existing developer
            developer = existing_developer
            action = 'updated'
        else:
            # Create new developer
            developer = Developer(
                primary_name=developer_name,
                primary_email=primary_email or f'{developer_name.lower()}@unknown',
                is_auto_grouped=False  # Manual creation
            )
            developer.save()
            action = 'created'
        
        # Create aliases for all selected identities
        aliases_created = 0
        skipped_aliases = []
        
        for alias_data in aliases_data:
            name = alias_data.get('name', '')
            email = alias_data.get('email', '')
            source = alias_data.get('source', '')
            
            # Normalize email for comparison
            normalized_email = email if not email.startswith('No email') else f'{name.lower()}@{source.lower()}.unknown'
            
            # Skip if this is the primary identity (exact match)
            if (name.lower() == developer_name.lower() and 
                (normalized_email == primary_email or 
                 (primary_email == '' and email.startswith('No email')))):
                continue
            
            # Check if alias already exists for this developer (exact match)
            existing_alias = DeveloperAlias.objects.filter(
                developer=developer,
                name=name,
                email=normalized_email
            ).first()
            
            if existing_alias:
                skipped_aliases.append(f"{name} ({normalized_email})")
                continue
            
            # Check if this alias exists for any other developer
            global_existing_alias = DeveloperAlias.objects.filter(
                name=name,
                email=normalized_email
            ).first()
            
            if global_existing_alias:
                skipped_aliases.append(f"{name} ({normalized_email}) - already linked to another developer")
                continue
            
            # Check if email exists anywhere (due to unique constraint on email)
            email_exists = DeveloperAlias.objects.filter(email=normalized_email).first()
            if email_exists:
                skipped_aliases.append(f"{name} ({normalized_email}) - email already exists in another alias")
                continue
            
            # Create alias
            alias = DeveloperAlias(
                developer=developer,
                name=name,
                email=normalized_email,
                first_seen=datetime.now(timezone.utc),
                last_seen=datetime.now(timezone.utc),
                commit_count=0
            )
            alias.save()
            aliases_created += 1
        
        # Prepare response message
        message = f'Successfully {action} developer "{developer_name}" with {aliases_created} new aliases'
        if skipped_aliases:
            message += f'. Skipped {len(skipped_aliases)} existing aliases: {", ".join(skipped_aliases)}'
        
        return JsonResponse({
            'success': True,
            'message': message,
            'developer_id': str(developer.id)
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Unexpected error: {str(e)}'
        }, status=500)


# Helper for legend colors
def _get_commit_type_color(commit_type):
    colors = {
        'fix': '#4caf50',
        'feature': '#2196f3',
        'docs': '#ffeb3b',
        'refactor': '#ff9800',
        'test': '#9c27b0',
        'style': '#00bcd4',
        'chore': '#607d8b',
        'other': '#bdbdbd'
    }
    return colors.get(commit_type, '#bdbdbd')


@login_required
def debug_identity_issues(request):
    """Debug endpoint to understand why certain identities cannot be added"""
    from analytics.models import Commit, Release, Deployment, PullRequest
    
    # Get a specific identity to debug
    identity_name = request.GET.get('name', '').strip()
    identity_email = request.GET.get('email', '').strip()
    
    if not identity_name and not identity_email:
        return JsonResponse({
            'error': 'Please provide either name or email parameter'
        }, status=400)
    
    # Check if this identity exists in our collections
    found_in_commits = Commit.objects.filter(
        author_name__icontains=identity_name
    ).count() if identity_name else 0
    
    found_in_releases = Release.objects.filter(
        author__icontains=identity_name
    ).count() if identity_name else 0
    
    found_in_deployments = Deployment.objects.filter(
        creator__icontains=identity_name
    ).count() if identity_name else 0
    
    found_in_pull_requests = PullRequest.objects.filter(
        author__icontains=identity_name
    ).count() if identity_name else 0
    
    # Check if this identity already exists in developers or aliases
    existing_developer = Developer.objects.filter(
        primary_name__icontains=identity_name
    ).first()
    
    existing_alias = DeveloperAlias.objects.filter(
        name__icontains=identity_name
    ).first()
    
    # Check email matches
    email_matches = []
    if identity_email:
        email_matches = DeveloperAlias.objects.filter(
            email__icontains=identity_email
        )
    
    return JsonResponse({
        'identity_name': identity_name,
        'identity_email': identity_email,
        'found_in_collections': {
            'commits': found_in_commits,
            'releases': found_in_releases,
            'deployments': found_in_deployments,
            'pull_requests': found_in_pull_requests
        },
        'existing_developer': {
            'exists': existing_developer is not None,
            'name': existing_developer.primary_name if existing_developer else None,
            'email': existing_developer.primary_email if existing_developer else None
        },
        'existing_alias': {
            'exists': existing_alias is not None,
            'name': existing_alias.name if existing_alias else None,
            'email': existing_alias.email if existing_alias else None,
            'developer': str(existing_alias.developer.id) if existing_alias and existing_alias.developer else None
        },
        'email_matches': [
            {
                'name': match.name,
                'email': match.email,
                'developer': str(match.developer.id) if match.developer else None
            }
            for match in email_matches
        ]
    })


@login_required
def list_teams(request):
    """List all teams with their members"""
    from django.contrib import messages
    
    print("DEBUG: list_teams view called")  # Debug log
    
    # Get search query
    search_query = request.GET.get('search', '').strip()
    
    # Get teams summary
    teams_service = GitHubTeamsService()
    print("DEBUG: Calling get_teams_summary")  # Debug log
    teams_summary = teams_service.get_teams_summary()
    print(f"DEBUG: Teams summary: {teams_summary}")  # Debug log
    
    if not teams_summary['success']:
        messages.warning(request, f"No teams data available: {teams_summary.get('error', 'Unknown error')}")
        teams_data = {}
        total_teams = 0
        total_developers = 0
    else:
        teams_data = teams_summary['teams']
        
        # Filter teams based on search query
        if search_query:
            filtered_teams = {}
            for team_name, members in teams_data.items():
                # Check if team name matches
                if search_query.lower() in team_name.lower():
                    filtered_teams[team_name] = members
                    continue
                
                # Check if any member name matches
                for member in members:
                    if (search_query.lower() in member['name'].lower() or 
                        search_query.lower() in member.get('email', '').lower()):
                        filtered_teams[team_name] = members
                        break
            
            teams_data = filtered_teams
        
        total_teams = len(teams_data)
        total_developers = sum(len(members) for members in teams_data.values())
    
    context = {
        'teams': teams_data,
        'total_teams': total_teams,
        'total_developers': total_developers,
        'active_tab': 'teams',
        'search_query': search_query,
    }
    
    return render(request, 'developers/list.html', context)


@login_required
@require_http_methods(["POST"])
def sync_github_teams(request):
    """Sync GitHub teams for all developers"""
    from django.contrib import messages
    
    print("DEBUG: sync_github_teams view called")  # Debug log
    
    try:
        print("DEBUG: Creating GitHubTeamsService")  # Debug log
        teams_service = GitHubTeamsService()
        print("DEBUG: Calling sync_all_developers_teams")  # Debug log
        result = teams_service.sync_all_developers_teams()
        print(f"DEBUG: Result: {result}")  # Debug log
        
        if result['success']:
            messages.success(
                request, 
                f"Successfully synced {result['synced_count']}/{result['total_developers']} developers with GitHub teams"
            )
            
            if result.get('errors'):
                for error in result['errors'][:5]:  # Show first 5 errors
                    messages.warning(request, f"Sync warning: {error}")
        else:
            messages.error(request, f"Sync failed: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        messages.error(request, f"Sync failed with exception: {str(e)}")
    
    # Redirect back to teams tab
    print(f"DEBUG: Redirecting to /developers/?tab=teams")
    return redirect('/developers/?tab=teams')

