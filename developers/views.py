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
from datetime import datetime, timedelta

from analytics.models import Developer, DeveloperAlias
from applications.models import Application


@login_required
def list_developers(request):
    """List all developers with simple search functionality"""
    # Get all developers from MongoDB
    developers = Developer.objects.all().order_by('primary_name')
    
    # Simple search filter
    search_query = request.GET.get('search', '').strip()
    if search_query:
        # For MongoDB, we need to use a different approach
        developers = developers.filter(
            primary_name__icontains=search_query
        )
    
    context = {
        'developers': developers,
        'search_query': search_query,
        'total_count': developers.count(),
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
        developers_data.append({
            'id': str(dev.id),
            'name': dev.primary_name or 'Unknown',
            'email': dev.primary_email or 'No email',
            'github_id': dev.github_id or '—',
            'detail_url': f'/developers/{dev.id}/'
        })
    
    return JsonResponse({
        'developers': developers_data,
        'total_count': len(developers_data),
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
        
        # Calculate quality scores (simplified)
        code_quality = 50  # Base score
        if has_code_files:
            code_quality += 40
        if commit.total_changes > 10:
            code_quality += 15
        quality_scores.append(min(100, code_quality))
        
        # Calculate impact score
        impact_score = 40  # Base score
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
    """Calculate commit type distribution for a developer"""
    if not commits:
        return {
            'total': 0,
            'types': {},
            'labels': [],
            'values': [],
            'legend': []
        }
    
    # Count commit types
    type_counts = Counter()
    for commit in commits:
        type_counts[commit.commit_type] += 1
    
    total_commits = sum(type_counts.values())
    
    # Define colors for each type
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
    
    # Create data for Chart.js
    labels = []
    values = []
    legend = []
    
    for commit_type in ['fix', 'feature', 'docs', 'refactor', 'test', 'style', 'chore', 'other']:
        count = type_counts.get(commit_type, 0)
        if count > 0:
            labels.append(commit_type.title())
            values.append(count)
            legend.append({
                'label': commit_type.title(),
                'count': count,
                'color': colors.get(commit_type, '#bdbdbd')
            })
    
    return {
        'total': total_commits,
        'types': dict(type_counts),
        'labels': labels,
        'values': values,
        'legend': legend
    }


def _calculate_quality_metrics_by_month(commits):
    """Calculate quality metrics by month for the last 12 months"""
    if not commits:
        return {
            'labels': [],
            'datasets': []
        }
    
    # Get commits from the last 12 months
    now = datetime.utcnow()
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
        now = datetime.utcnow().replace(tzinfo=None)
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
            'commit_type_labels': commit_type_data['labels'],
            'commit_type_values': commit_type_data['values'],
            'commit_type_legend': commit_type_data['legend']
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

