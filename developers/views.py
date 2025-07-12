


import urllib.parse
from datetime import datetime, timedelta
import json
from collections import defaultdict

from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from .models import DeveloperGroup, DeveloperIdentity
from analytics.models import Commit
import base64

@login_required
def list_groups(request):
    """Retourne la liste de tous les groupes existants (id, nom, email) pour sélection côté frontend."""
    from analytics.models import DeveloperGroup
    try:
        groups = DeveloperGroup.objects.all()
        data = []
        for group in groups:
            try:
                # Utiliser les bons champs MongoDB
                name = getattr(group, 'primary_name', '') or ''
                email = getattr(group, 'primary_email', '') or ''
                
                # S'assurer que les chaînes sont bien des chaînes UTF-8 valides
                if isinstance(name, bytes):
                    name = name.decode('utf-8', errors='replace')
                if isinstance(email, bytes):
                    email = email.decode('utf-8', errors='replace')
                
                # Nettoyer les caractères problématiques
                name = str(name).replace('\x00', '').strip()
                email = str(email).replace('\x00', '').strip()
                
                # S'assurer que l'ID est une chaîne valide
                group_id = str(group.id)
                if not group_id or group_id == 'None':
                    continue
                
                data.append({
                    'id': group_id,
                    'name': name,
                    'email': email
                })
            except Exception as group_error:
                print(f"Error processing group {getattr(group, 'id', 'unknown')}: {str(group_error)}")
                continue
        
        return JsonResponse({'groups': data}, safe=False)
    except Exception as e:
        print(f"Error in list_groups: {str(e)}")
        return JsonResponse({'error': 'Failed to load groups', 'details': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def merge_group(request):
    """Fusionne tous les alias du groupe source dans le groupe cible, puis supprime le groupe source."""
    from analytics.models import DeveloperGroup, DeveloperAlias
    try:
        data = json.loads(request.body)
        source_group_id = data.get('source_group_id')
        target_group_id = data.get('target_group_id')
        if not source_group_id or not target_group_id:
            return JsonResponse({'error': 'source_group_id et target_group_id requis'}, status=400)
        if source_group_id == target_group_id:
            return JsonResponse({'error': 'Les deux groupes doivent être différents'}, status=400)
        source_group = DeveloperGroup.objects.get(id=source_group_id)
        target_group = DeveloperGroup.objects.get(id=target_group_id)
        # Rattacher tous les alias du groupe source au groupe cible
        updated = DeveloperAlias.objects(group=source_group).update(set__group=target_group)
        # Supprimer le groupe source
        source_group.delete()
        return JsonResponse({'success': True, 'aliases_moved': updated})
    except DeveloperGroup.DoesNotExist:
        return JsonResponse({'error': 'Groupe introuvable'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_http_methods(["POST"])
def add_identity_to_group(request):
    """Ajoute une identité individuelle (nom/email) à un groupe existant."""
    from analytics.models import DeveloperGroup, DeveloperAlias
    try:
        data = json.loads(request.body)
        group_id = data.get('group_id')
        name = data.get('name')
        email = data.get('email')
        if not group_id or not name or not email:
            return JsonResponse({'error': 'group_id, name et email requis'}, status=400)
        group = DeveloperGroup.objects.get(id=group_id)
        # Vérifier si l'alias existe déjà
        exists = DeveloperAlias.objects(group=group, name=name, email=email).first()
        if exists:
            return JsonResponse({'error': 'Cette identité existe déjà dans ce groupe'}, status=400)
        # Créer le nouvel alias
        alias = DeveloperAlias(group=group, name=name, email=email)
        alias.save()
        return JsonResponse({'success': True, 'alias_id': str(alias.id)})
    except DeveloperGroup.DoesNotExist:
        return JsonResponse({'error': 'Groupe introuvable'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def developer_list(request):
    """List all developers with grouping information"""
    from analytics.developer_grouping_service import DeveloperGroupingService
    
    # Get grouped developers (both auto and manual)
    grouping_service = DeveloperGroupingService()
    grouped_developers = grouping_service.get_grouped_developers()
    
    # Create a set of grouped developer keys for filtering
    grouped_developers_set = set()
    for group in grouped_developers:
        for alias in group['aliases']:
            dev_key = f"{alias['name']}|{alias['email']}"
            grouped_developers_set.add(dev_key)
    
    # Get all individual developers from commits
    from analytics.models import Commit
    commits = Commit.objects.all()
    
    # Extract unique developers from commits
    seen_developers = set()
    all_individual_developers = []
    
    for commit in commits:
        # Create a unique key for this developer
        dev_key = f"{commit.author_name}|{commit.author_email}"
        
        if dev_key not in seen_developers:
            seen_developers.add(dev_key)
            
            # Create URL-safe encoded ID for the developer
            dev_data = f"{commit.author_name}|{commit.author_email}"
            # Use proper URL encoding
            encoded_data = urllib.parse.quote(dev_data, safe='')
            developer = {
                'name': commit.author_name,
                'email': commit.author_email,
                'commit_count': 1,  # Will be updated
                'first_seen': commit.authored_date,
                'last_seen': commit.authored_date,
                'is_grouped': False,
                'group_id': f"individual_{encoded_data}"
            }
            all_individual_developers.append(developer)
        else:
            # Update existing developer
            for dev in all_individual_developers:
                if f"{dev['name']}|{dev['email']}" == dev_key:
                    dev['commit_count'] += 1
                    if commit.authored_date < dev['first_seen']:
                        dev['first_seen'] = commit.authored_date
                    if commit.authored_date > dev['last_seen']:
                        dev['last_seen'] = commit.authored_date
                    break
    
    # Combine grouped and individual developers
    all_developers = []
    
    # Add grouped developers
    for developer in grouped_developers:
        developer['is_grouped'] = True
        # Normalize keys for template compatibility
        developer['name'] = developer.get('primary_name', '')
        developer['email'] = developer.get('primary_email', '')
        # Preserve the group_id for the template
        developer['group_id'] = developer.get('group_id', '')
        all_developers.append(developer)
    
    # Add individual developers (not already in groups)
    for developer in all_individual_developers:
        dev_key = f"{developer['name']}|{developer['email']}"
        if dev_key not in grouped_developers_set:
            developer['application'] = {
                'id': 0,  # Global
                'name': 'All Applications'
            }
            developer['is_grouped'] = False
            all_developers.append(developer)
    
    # Get search parameter
    search_term = request.GET.get('search', '').strip().lower()
    
    # Filter developers based on search term
    if search_term:
        filtered_developers = []
        for developer in all_developers:
            name = developer.get('name', '').lower()
            email = developer.get('email', '').lower()
            first_seen = developer.get('first_seen', '').strftime('%b %d, %Y').lower() if developer.get('first_seen') else ''
            last_seen = developer.get('last_seen', '').strftime('%b %d, %Y').lower() if developer.get('last_seen') else ''
            
            if (search_term in name or 
                search_term in email or 
                search_term in first_seen or 
                search_term in last_seen):
                filtered_developers.append(developer)
        all_developers = filtered_developers
    
    # Get sorting parameters
    sort_by = request.GET.get('sort', 'name')  # Default sort by name
    sort_order = request.GET.get('order', 'asc')  # Default ascending
    
    # Sort developers
    if sort_by == 'name':
        all_developers.sort(key=lambda x: x['name'].lower(), reverse=(sort_order == 'desc'))
    elif sort_by == 'email':
        all_developers.sort(key=lambda x: x['email'].lower(), reverse=(sort_order == 'desc'))
    elif sort_by == 'first_seen':
        all_developers.sort(key=lambda x: x.get('first_seen', datetime.min), reverse=(sort_order == 'desc'))
    elif sort_by == 'last_seen':
        all_developers.sort(key=lambda x: x.get('last_seen', datetime.min), reverse=(sort_order == 'desc'))
    else:  # Default: sort by commit count
        all_developers.sort(key=lambda x: x.get('commit_count', x.get('total_commits', 0)), reverse=(sort_order == 'desc'))
    
    # Paginate
    paginator = Paginator(all_developers, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Count grouped vs ungrouped
    grouped_count = len([d for d in all_developers if d.get('is_grouped', False)])
    ungrouped_count = len(all_developers) - grouped_count
    
    context = {
        'page_obj': page_obj,
        'total_count': len(all_developers),
        'grouped_count': grouped_count,
        'ungrouped_count': ungrouped_count,
        'sort_by': sort_by,
        'sort_order': sort_order,
        'search_term': search_term,
    }
    
    return render(request, 'developers/list.html', context)


def _generate_commit_quality_data(commits_query):
    """Generate commit quality metrics for a developer"""
    import re
    
    # Define patterns for generic vs explicit messages
    generic_patterns = [
        r'^wip$', r'^fix$', r'^update$', r'^cleanup$', r'^refactor$',
        r'^typo$', r'^style$', r'^format$', r'^test$', r'^docs$',
        r'^chore:', r'^feat:', r'^fix:', r'^docs:', r'^style:',
        r'^refactor:', r'^test:', r'^chore\(', r'^feat\(', r'^fix\(',
        r'^update\s+\w+$', r'^fix\s+\w+$', r'^add\s+\w+$'
    ]
    
    explicit_count = 0
    generic_count = 0
    total_commits = 0
    
    for commit in commits_query:
        total_commits += 1
        message = commit.message.lower().strip()
        
        # Check if message matches generic patterns
        is_generic = False
        for pattern in generic_patterns:
            if re.match(pattern, message):
                is_generic = True
                break
        
        if is_generic:
            generic_count += 1
        else:
            explicit_count += 1
    
    if total_commits > 0:
        explicit_ratio = (explicit_count / total_commits) * 100
        generic_ratio = (generic_count / total_commits) * 100
    else:
        explicit_ratio = 0
        generic_ratio = 0
    
    return {
        'total_commits': total_commits,
        'explicit_commits': explicit_count,
        'generic_commits': generic_count,
        'explicit_ratio': round(explicit_ratio, 1),
        'generic_ratio': round(generic_ratio, 1)
    }

def _generate_commit_type_distribution(commits_query):
    """Generate commit type distribution for a developer"""
    from analytics.commit_classifier import get_commit_type_stats
    
    return get_commit_type_stats(commits_query)


def _generate_commit_frequency_data(commits_query):
    """Generate commit frequency metrics for a developer"""
    from analytics.analytics_service import AnalyticsService
    
    # Create a temporary analytics service instance
    # We don't need application_id for this calculation
    analytics_service = AnalyticsService(0)
    
    return analytics_service.get_developer_commit_frequency(commits_query)

def _generate_polar_chart_data(commits_query):
    """Generate polar area chart data for repositories by net lines added"""
    from collections import defaultdict
    
    # Group commits by repository and calculate net lines added
    repo_stats = defaultdict(lambda: {'additions': 0, 'deletions': 0})
    
    for commit in commits_query:
        repo_name = commit.repository_full_name
        repo_stats[repo_name]['additions'] += commit.additions
        repo_stats[repo_name]['deletions'] += commit.deletions
    
    # Calculate net lines added and prepare chart data
    chart_data = []
    colors = [
        'rgba(34, 197, 94, 0.7)',   # green
        'rgba(59, 130, 246, 0.7)',  # blue
        'rgba(168, 85, 247, 0.7)',  # purple
        'rgba(239, 68, 68, 0.7)',   # red
        'rgba(245, 158, 11, 0.7)',  # orange
        'rgba(16, 185, 129, 0.7)',  # emerald
        'rgba(236, 72, 153, 0.7)',  # pink
        'rgba(99, 102, 241, 0.7)',  # indigo
    ]
    
    for i, (repo_name, stats) in enumerate(repo_stats.items()):
        net_lines = stats['additions'] - stats['deletions']
        if net_lines > 0:  # Only show positive net lines
            chart_data.append({
                'label': repo_name,
                'data': [net_lines],
                'backgroundColor': colors[i % len(colors)],
                'borderColor': colors[i % len(colors)].replace('0.7', '1'),
                'borderWidth': 2
            })
    
    return chart_data

def _generate_chart_data(commits_query, days_back=120):
    """Generate bubble chart data from commits for the last N days"""
    from datetime import datetime, timedelta
    
    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    
    # Get commits in date range
    commits = commits_query.filter(authored_date__gte=start_date).order_by('authored_date')
    
    # Group by repository and hour
    activity_data = defaultdict(lambda: defaultdict(int))
    total_changes = defaultdict(lambda: defaultdict(int))
    
    for commit in commits:
        # Get date and hour
        commit_date = commit.authored_date.date()
        commit_hour = commit.authored_date.hour
        repository = commit.repository_full_name
        
        # Count commits
        activity_data[repository][(commit_date, commit_hour)] += 1
        
        # Sum additions/deletions for bubble size
        changes = (commit.additions or 0) + (commit.deletions or 0)
        total_changes[repository][(commit_date, commit_hour)] += changes
    
    # Generate datasets for Chart.js
    datasets = []
    colors = [
        'rgba(59, 130, 246, 0.7)',   # Blue
        'rgba(16, 185, 129, 0.7)',   # Green
        'rgba(245, 158, 11, 0.7)',   # Yellow
        'rgba(239, 68, 68, 0.7)',    # Red
        'rgba(139, 92, 246, 0.7)',   # Purple
        'rgba(6, 182, 212, 0.7)',    # Cyan
        'rgba(132, 204, 22, 0.7)',   # Lime
        'rgba(249, 115, 22, 0.7)'    # Orange
    ]
    
    for i, (repository, data) in enumerate(activity_data.items()):
        color = colors[i % len(colors)]
        dataset = {
            'label': repository,
            'data': [],
            'backgroundColor': color,
            'borderColor': color.replace('0.7', '1.0'),  # Solid border
            'borderWidth': 1
        }
        
        for (date, hour), commit_count in data.items():
            # Calculate bubble size based on changes (fallback to commit count)
            changes = total_changes[repository][(date, hour)]
            bubble_size = max(changes / 100, commit_count * 5)  # Scale appropriately
            
            # Convert date to days ago for simpler x-axis
            days_ago = (end_date.date() - date).days
            
            dataset['data'].append({
                'x': days_ago,
                'y': hour,
                'r': bubble_size,
                'repository': repository,
                'commit_count': commit_count,
                'changes': changes
            })
        
        datasets.append(dataset)
    
    return datasets, start_date, end_date

@login_required
def developer_detail(request, developer_id):
    """Show details for a specific developer or group"""
    try:
        # Check if this is a MongoDB group ID (24 character hex string)
        if len(developer_id) == 24 and all(c in '0123456789abcdef' for c in developer_id.lower()):
            # MongoDB group ID - get the group and its aliases
            from analytics.models import DeveloperGroup, DeveloperAlias
            try:
                group = DeveloperGroup.objects.get(id=developer_id)
                aliases = DeveloperAlias.objects.filter(group=group)
                
                # Build query for exact name/email pairs
                from mongoengine.queryset.visitor import Q
                query = Q()
                for alias in aliases:
                    query |= Q(author_name__iexact=alias.name, author_email__iexact=alias.email)
                
                commits = Commit.objects(query).order_by('-authored_date')
                
                # Get first and last commit dates from all commits (not just the 50 most recent)
                first_commit = Commit.objects(query).order_by('authored_date').first()
                last_commit = Commit.objects(query).order_by('-authored_date').first()
                
                # Generate chart data
                chart_data, min_date, max_date = _generate_chart_data(Commit.objects(query))
                polar_chart_data = _generate_polar_chart_data(Commit.objects(query))
                commit_quality = _generate_commit_quality_data(Commit.objects(query))
                commit_type_distribution = _generate_commit_type_distribution(Commit.objects(query))
                commit_frequency = _generate_commit_frequency_data(Commit.objects(query))
                
                # Prepare doughnut chart data
                doughnut_colors = {
                    'fix': '#4caf50',
                    'feature': '#2196f3',
                    'docs': '#ffeb3b',
                    'refactor': '#ff9800',
                    'test': '#9c27b0',
                    'style': '#00bcd4',
                    'chore': '#607d8b',
                    'other': '#bdbdbd',
                }
                
                context = {
                    'developer': {
                        'name': group.primary_name,
                        'email': group.primary_email,
                        'github_id': group.github_id,
                        'commit_count': commits.count(),
                        'is_group': True
                    },
                    'identities': aliases,
                    'chart_data': json.dumps(chart_data),
                    'polar_chart_data': json.dumps(polar_chart_data),
                    'commit_quality': commit_quality,
                    'commit_type_distribution': commit_type_distribution,
                    'commit_type_labels': json.dumps(list(commit_type_distribution['counts'].keys())),
                    'commit_type_values': json.dumps(list(commit_type_distribution['counts'].values())),
                    'doughnut_colors': doughnut_colors,
                    'min_date': min_date,
                    'max_date': max_date,
                    'first_commit': first_commit,
                    'last_commit': last_commit,
                    'is_group': True,
                    'commit_frequency': commit_frequency,
                }
                # Prépare la légende après
                legend_data = []
                for label, count in commit_type_distribution['counts'].items():
                    color = doughnut_colors.get(label, '#bdbdbd')
                    legend_data.append({'label': label, 'count': count, 'color': color})
                context['commit_type_legend'] = legend_data
            except DeveloperGroup.DoesNotExist:
                return redirect('developers:list')
        else:
            # Assume it's an individual developer (URL encoded name|email)
            try:
                # Use proper URL decoding
                decoded = urllib.parse.unquote(developer_id)
                name, email = decoded.split('|', 1)
                
                # Remove 'individual_' prefix if present
                if name.startswith('individual_'):
                    name = '_'.join(name.split('_')[1:])  # Remove 'individual_' prefix
                    
            except Exception:
                return redirect('developers:list')
            print(f"[DEBUG] Recherche commits pour name='{name}', email='{email}'")
            
            # Use same logic as groups: exact name/email pair
            from mongoengine.queryset.visitor import Q
            query = Q(author_name__iexact=name, author_email__iexact=email)
            commits = Commit.objects(query).order_by('-authored_date')
            print(f"[DEBUG] Nb commits trouvés: {commits.count()}")
            
            # Get first and last commit dates from all commits (not just the 50 most recent)
            first_commit = Commit.objects(query).order_by('authored_date').first()
            last_commit = Commit.objects(query).order_by('-authored_date').first()
            
            # Generate chart data
            chart_data, min_date, max_date = _generate_chart_data(Commit.objects(query))
            polar_chart_data = _generate_polar_chart_data(Commit.objects(query))
            commit_quality = _generate_commit_quality_data(Commit.objects(query))
            commit_type_distribution = _generate_commit_type_distribution(Commit.objects(query))
            commit_frequency = _generate_commit_frequency_data(Commit.objects(query))
            
            # Prepare doughnut chart data
            doughnut_colors = {
                'fix': '#4caf50',
                'feature': '#2196f3',
                'docs': '#ffeb3b',
                'refactor': '#ff9800',
                'test': '#9c27b0',
                'style': '#00bcd4',
                'chore': '#607d8b',
                'other': '#bdbdbd',
            }
            
            context = {
                'developer': {
                    'name': name,
                    'email': email,
                    'commit_count': commits.count(),
                    'is_group': False
                },
                'chart_data': json.dumps(chart_data),
                'polar_chart_data': json.dumps(polar_chart_data),
                'commit_quality': commit_quality,
                'commit_type_distribution': commit_type_distribution,
                'commit_type_labels': json.dumps(list(commit_type_distribution['counts'].keys())),
                'commit_type_values': json.dumps(list(commit_type_distribution['counts'].values())),
                'doughnut_colors': doughnut_colors,
                'min_date': min_date,
                'max_date': max_date,
                'first_commit': first_commit,
                'last_commit': last_commit,
                'is_group': False,
                'commit_frequency': commit_frequency,
            }
            # Prépare la légende après
            legend_data = []
            for label, count in commit_type_distribution['counts'].items():
                color = doughnut_colors.get(label, '#bdbdbd')
                legend_data.append({'label': label, 'count': count, 'color': color})
            context['commit_type_legend'] = legend_data
    except Exception as e:
        print(f"Error processing developer: {str(e)}")
        return redirect('developers:list')
    
    return render(request, 'developers/detail.html', context)

import base64
import urllib.parse
from datetime import datetime

from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from .models import DeveloperGroup, DeveloperIdentity
from analytics.models import Commit
import json

@login_required
@require_http_methods(["POST"])
def merge_group(request):
    """Fusionne tous les alias du groupe source dans le groupe cible, puis supprime le groupe source."""
    from analytics.models import DeveloperGroup, DeveloperAlias
    try:
        data = json.loads(request.body)
        source_group_id = data.get('source_group_id')
        target_group_id = data.get('target_group_id')
        if not source_group_id or not target_group_id:
            return JsonResponse({'error': 'source_group_id et target_group_id requis'}, status=400)
        if source_group_id == target_group_id:
            return JsonResponse({'error': 'Les deux groupes doivent être différents'}, status=400)
        source_group = DeveloperGroup.objects.get(id=source_group_id)
        target_group = DeveloperGroup.objects.get(id=target_group_id)
        # Rattacher tous les alias du groupe source au groupe cible
        updated = DeveloperAlias.objects(group=source_group).update(set__group=target_group)
        # Supprimer le groupe source
        source_group.delete()
        return JsonResponse({'success': True, 'aliases_moved': updated})
    except DeveloperGroup.DoesNotExist:
        return JsonResponse({'error': 'Groupe introuvable'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_http_methods(["POST"])
def add_identity_to_group(request):
    """Ajoute une identité individuelle (nom/email) à un groupe existant."""
    from analytics.models import DeveloperGroup, DeveloperAlias
    try:
        data = json.loads(request.body)
        group_id = data.get('group_id')
        name = data.get('name')
        email = data.get('email')
        if not group_id or not name or not email:
            return JsonResponse({'error': 'group_id, name et email requis'}, status=400)
        group = DeveloperGroup.objects.get(id=group_id)
        # Vérifier si l'alias existe déjà
        exists = DeveloperAlias.objects(group=group, name=name, email=email).first()
        if exists:
            return JsonResponse({'error': 'Cette identité existe déjà dans ce groupe'}, status=400)
        # Créer le nouvel alias
        alias = DeveloperAlias(group=group, name=name, email=email)
        alias.save()
        return JsonResponse({'success': True, 'alias_id': str(alias.id)})
    except DeveloperGroup.DoesNotExist:
        return JsonResponse({'error': 'Groupe introuvable'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def sync_from_mongo(request):
    """Sync developer data from MongoDB (placeholder for now)"""
    messages.success(request, "Developer data is extracted directly from commits. No sync needed.")
    return redirect('developers:list')


@login_required
def create_group(request):
    """Create a new empty developer group"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('name')
            email = data.get('email')
            
            if not name or not email:
                return JsonResponse({'error': 'Name and email are required'}, status=400)
            
            # Import the models
            from analytics.models import DeveloperGroup
            
            # Check if a group with this name/email already exists
            existing_group = DeveloperGroup.objects.filter(
                primary_name=name,
                primary_email=email
            ).first()
            
            if existing_group:
                return JsonResponse({'error': 'A group with this name and email already exists'}, status=400)
            
            # Create a new empty group
            new_group = DeveloperGroup(
                primary_name=name,
                primary_email=email
            )
            new_group.save()
            
            return JsonResponse({
                'success': True,
                'group_id': str(new_group.id),
                'group_name': name,
                'group_email': email
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'POST method required'}, status=405)


@login_required
def search_developers(request):
    """AJAX endpoint for searching developers"""
    from analytics.developer_grouping_service import DeveloperGroupingService
    
    search_term = request.GET.get('q', '').strip().lower()
    page = request.GET.get('page', 1)
    sort_by = request.GET.get('sort', 'name')
    sort_order = request.GET.get('order', 'asc')
    
    # Get grouped developers
    grouping_service = DeveloperGroupingService()
    grouped_developers = grouping_service.get_grouped_developers()
    
    # Create a set of grouped developer keys for filtering
    grouped_developers_set = set()
    for group in grouped_developers:
        for alias in group['aliases']:
            dev_key = f"{alias['name']}|{alias['email']}"
            grouped_developers_set.add(dev_key)
    
    # Get all individual developers from commits
    from analytics.models import Commit
    commits = Commit.objects.all()
    
    # Extract unique developers from commits
    seen_developers = set()
    all_individual_developers = []
    
    for commit in commits:
        dev_key = f"{commit.author_name}|{commit.author_email}"
        
        if dev_key not in seen_developers:
            seen_developers.add(dev_key)
            
            dev_data = f"{commit.author_name}|{commit.author_email}"
            encoded_data = urllib.parse.quote(dev_data, safe='')
            developer = {
                'name': commit.author_name,
                'email': commit.author_email,
                'commit_count': 1,
                'first_seen': commit.authored_date,
                'last_seen': commit.authored_date,
                'is_grouped': False,
                'group_id': f"individual_{encoded_data}"
            }
            all_individual_developers.append(developer)
        else:
            for dev in all_individual_developers:
                if f"{dev['name']}|{dev['email']}" == dev_key:
                    dev['commit_count'] += 1
                    if commit.authored_date < dev['first_seen']:
                        dev['first_seen'] = commit.authored_date
                    if commit.authored_date > dev['last_seen']:
                        dev['last_seen'] = commit.authored_date
                    break
    
    # Combine grouped and individual developers
    all_developers = []
    
    for developer in grouped_developers:
        developer['is_grouped'] = True
        developer['name'] = developer.get('primary_name', '')
        developer['email'] = developer.get('primary_email', '')
        developer['group_id'] = developer.get('group_id', '')
        all_developers.append(developer)
    
    for developer in all_individual_developers:
        dev_key = f"{developer['name']}|{developer['email']}"
        if dev_key not in grouped_developers_set:
            developer['application'] = {
                'id': 0,
                'name': 'All Applications'
            }
            developer['is_grouped'] = False
            all_developers.append(developer)
    
    # Filter by search term
    if search_term:
        filtered_developers = []
        for developer in all_developers:
            name = developer.get('name', '').lower()
            email = developer.get('email', '').lower()
            first_seen = developer.get('first_seen', '').strftime('%b %d, %Y').lower() if developer.get('first_seen') else ''
            last_seen = developer.get('last_seen', '').strftime('%b %d, %Y').lower() if developer.get('last_seen') else ''
            
            if (search_term in name or 
                search_term in email or 
                search_term in first_seen or 
                search_term in last_seen):
                filtered_developers.append(developer)
        all_developers = filtered_developers
    
    # Sort developers
    if sort_by == 'name':
        all_developers.sort(key=lambda x: x['name'].lower(), reverse=(sort_order == 'desc'))
    elif sort_by == 'email':
        all_developers.sort(key=lambda x: x['email'].lower(), reverse=(sort_order == 'desc'))
    elif sort_by == 'first_seen':
        all_developers.sort(key=lambda x: x.get('first_seen', datetime.min), reverse=(sort_order == 'desc'))
    elif sort_by == 'last_seen':
        all_developers.sort(key=lambda x: x.get('last_seen', datetime.min), reverse=(sort_order == 'desc'))
    else:
        all_developers.sort(key=lambda x: x.get('commit_count', x.get('total_commits', 0)), reverse=(sort_order == 'desc'))
    
    # Paginate
    paginator = Paginator(all_developers, 20)
    page_obj = paginator.get_page(page)
    
    # Prepare data for JSON response
    developers_data = []
    for dev in page_obj:
        developers_data.append({
            'name': dev['name'],
            'email': dev['email'],
            'first_seen': dev.get('first_seen', '').strftime('%b %d, %Y') if dev.get('first_seen') else '',
            'last_seen': dev.get('last_seen', '').strftime('%b %d, %Y') if dev.get('last_seen') else '',
            'is_grouped': dev.get('is_grouped', False),
            'group_id': dev.get('group_id', ''),
            'commit_count': dev.get('commit_count', 0)
        })
    
    return JsonResponse({
        'developers': developers_data,
        'total_count': len(all_developers),
        'grouped_count': len([d for d in all_developers if d.get('is_grouped', False)]),
        'ungrouped_count': len(all_developers) - len([d for d in all_developers if d.get('is_grouped', False)]),
        'has_previous': page_obj.has_previous(),
        'has_next': page_obj.has_next(),
        'current_page': page_obj.number,
        'total_pages': page_obj.paginator.num_pages
    })


@login_required
def add_to_group(request):
    """Add developer to group"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            developer_id = data.get('developer_id')
            group_id = data.get('group_id')
            
            if not developer_id or not group_id:
                return JsonResponse({'error': 'Developer ID and Group ID are required'}, status=400)
            
            # For now, just return success - in a real implementation, you'd store this in the database
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'POST method required'}, status=405)

