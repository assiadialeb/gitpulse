"""
Django-Q tasks for automated synchronization
"""
import logging
from datetime import datetime, timedelta
from django_q.tasks import async_task, schedule
from django_q.models import Schedule

from .git_sync_service import GitSyncService
from .services import RateLimitService
from .github_service import GitHubRateLimitError
from applications.models import Application, ApplicationRepository
# from github.models import GitHubToken  # Deprecated - using django-allauth now
from .services import DeploymentIndexingService
from .services import ReleaseIndexingService

logger = logging.getLogger(__name__)


def sync_application_task(application_id: int, user_id: int, sync_type: str = 'incremental'):
    """
    Django-Q task to sync all repositories for an application
    
    Args:
        application_id: Application ID to sync
        user_id: User ID who owns the application
        sync_type: 'full' or 'incremental'
    """
    logger.info(f"Starting sync task for application {application_id}, user {user_id}")
    
    try:
        sync_service = GitSyncService(user_id)
        results = sync_service.sync_application_repositories(application_id, sync_type)
        
        logger.info(f"Sync completed for application {application_id}: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Sync task failed for application {application_id}: {e}")
        raise


def sync_repository_task(repo_full_name: str, application_id: int, user_id: int, 
                        sync_type: str = 'incremental'):
    """
    Django-Q task to sync a specific repository
    
    Args:
        repo_full_name: Repository name in format "owner/repo"
        application_id: Application ID
        user_id: User ID who owns the application
        sync_type: 'full' or 'incremental'
    """
    logger.info(f"Starting sync task for repository {repo_full_name}")
    
    try:
        sync_service = GitSyncService(user_id)
        # On a besoin de l'URL du repo pour GitSyncService, on la récupère via ApplicationRepository
        from applications.models import ApplicationRepository
        app_repo = ApplicationRepository.objects.get(github_repo_name=repo_full_name, application_id=application_id)
        
        # Check if github_repo_url exists, if not generate it
        repo_url = getattr(app_repo, 'github_repo_url', None)
        if not repo_url:
            repo_url = f"https://github.com/{app_repo.github_repo_name}.git"
            logger.warning(f"Missing github_repo_url for {app_repo.github_repo_name}, using generated URL: {repo_url}")
        
        results = sync_service.sync_repository(repo_full_name, repo_url, application_id, sync_type)
        
        logger.info(f"Sync completed for repository {repo_full_name}: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Sync task failed for repository {repo_full_name}: {e}")
        raise


def retry_failed_syncs_task():
    """
    Django-Q task to retry failed synchronizations
    """
    logger.info("Starting retry failed syncs task")
    
    try:
        # Get all users with GitHub tokens from django-allauth
        from allauth.socialaccount.models import SocialApp, SocialToken
        from django.contrib.auth.models import User
        
        github_app = SocialApp.objects.filter(provider='github').first()
        if not github_app:
            logger.error("No GitHub SocialApp found")
            return {'error': 'No GitHub SocialApp configured'}
        
        # Get all users who have GitHub tokens
        social_tokens = SocialToken.objects.filter(app=github_app)
        
        total_results = {
            'users_processed': 0,
            'total_retries_attempted': 0,
            'total_retries_successful': 0,
            'total_retries_failed': 0
        }
        
        for social_token in social_tokens:
            try:
                user_id = social_token.account.user.id
                sync_service = GitSyncService(user_id)
                results = sync_service.retry_failed_syncs()
                
                total_results['users_processed'] += 1
                total_results['total_retries_attempted'] += results['retries_attempted']
                total_results['total_retries_successful'] += results['retries_successful']
                total_results['total_retries_failed'] += results['retries_failed']
                
            except Exception as e:
                logger.error(f"Failed to retry syncs for user {social_token.account.user.id}: {e}")
                continue
        
        logger.info(f"Retry failed syncs completed: {total_results}")
        return total_results
        
    except Exception as e:
        logger.error(f"Retry failed syncs task failed: {e}")
        raise


def daily_sync_task():
    """
    Django-Q task to run daily incremental sync for all applications
    """
    logger.info("Starting daily sync task")
    
    try:
        # Get all applications that have repositories
        applications_with_repos = Application.objects.filter(
            applicationrepository__isnull=False
        ).distinct()
        
        total_results = {
            'applications_processed': 0,
            'total_repositories_synced': 0,
            'total_commits_new': 0,
            'total_api_calls': 0,
            'errors': []
        }
        
        for application in applications_with_repos:
            try:
                # Schedule async task for each application
                task_id = async_task(
                    'analytics.tasks.sync_application_task',
                    application.id,
                    application.owner_id,
                    'incremental',
                    group=f'daily_sync_{datetime.now().strftime("%Y%m%d")}',
                    timeout=3600  # 1 hour timeout
                )
                
                logger.info(f"Scheduled sync task {task_id} for application {application.id}")
                total_results['applications_processed'] += 1
                
            except Exception as e:
                error_msg = f"Failed to schedule sync for application {application.id}: {e}"
                logger.error(error_msg)
                total_results['errors'].append(error_msg)
        
        logger.info(f"Daily sync task completed: {total_results}")
        return total_results
        
    except Exception as e:
        logger.error(f"Daily sync task failed: {e}")
        raise


def weekly_full_sync_task():
    """
    Django-Q task to run weekly full sync for all applications
    """
    logger.info("Starting weekly full sync task")
    
    try:
        # Get all applications that have repositories
        applications_with_repos = Application.objects.filter(
            applicationrepository__isnull=False
        ).distinct()
        
        total_results = {
            'applications_processed': 0,
            'applications_scheduled': 0,
            'errors': []
        }
        
        for application in applications_with_repos:
            try:
                # Schedule async task for each application with delay to avoid rate limits
                delay_minutes = total_results['applications_scheduled'] * 10  # 10 min delay between apps
                
                task_id = async_task(
                    'analytics.tasks.sync_application_task',
                    application.id,
                    application.owner_id,
                    'full',
                    group=f'weekly_sync_{datetime.now().strftime("%Y%m%d")}',
                    timeout=7200,  # 2 hour timeout for full sync
                    schedule=datetime.now() + timedelta(minutes=delay_minutes)
                )
                
                logger.info(f"Scheduled full sync task {task_id} for application {application.id} with {delay_minutes}min delay")
                total_results['applications_processed'] += 1
                total_results['applications_scheduled'] += 1
                
            except Exception as e:
                error_msg = f"Failed to schedule full sync for application {application.id}: {e}"
                logger.error(error_msg)
                total_results['errors'].append(error_msg)
        
        logger.info(f"Weekly full sync task completed: {total_results}")
        return total_results
        
    except Exception as e:
        logger.error(f"Weekly full sync task failed: {e}")
        raise


def schedule_sync_tasks():
    """
    Set up scheduled tasks in Django-Q
    This should be called once to create the scheduled tasks
    """
    logger.info("Setting up scheduled sync tasks")
    
    # Clear existing schedules (optional - only run this manually)
    # Schedule.objects.filter(func__startswith='analytics.tasks').delete()
    
    try:
        # Daily incremental sync at 2 AM
        daily_schedule, created = Schedule.objects.get_or_create(
            name='daily_incremental_sync',
            defaults={
                'func': 'analytics.tasks.daily_sync_task',
                'schedule_type': Schedule.DAILY,
                'next_run': datetime.now().replace(hour=2, minute=0, second=0, microsecond=0),
                'repeats': -1  # Infinite repeats
            }
        )
        if created:
            logger.info("Created daily incremental sync schedule")
        else:
            logger.info("Daily incremental sync schedule already exists")
        
        # Weekly full sync on Sunday at 3 AM
        weekly_schedule, created = Schedule.objects.get_or_create(
            name='weekly_full_sync',
            defaults={
                'func': 'analytics.tasks.weekly_full_sync_task',
                'schedule_type': Schedule.WEEKLY,
                'next_run': datetime.now().replace(hour=3, minute=0, second=0, microsecond=0),
                'repeats': -1  # Infinite repeats
            }
        )
        if created:
            logger.info("Created weekly full sync schedule")
        else:
            logger.info("Weekly full sync schedule already exists")
        
        # Retry failed syncs every 4 hours
        retry_schedule, created = Schedule.objects.get_or_create(
            name='retry_failed_syncs',
            defaults={
                'func': 'analytics.tasks.retry_failed_syncs_task',
                'schedule_type': Schedule.HOURLY,
                'minutes': 4 * 60,  # Every 4 hours
                'next_run': datetime.now() + timedelta(hours=1),  # Start in 1 hour
                'repeats': -1  # Infinite repeats
            }
        )
        if created:
            logger.info("Created retry failed syncs schedule")
        else:
            logger.info("Retry failed syncs schedule already exists")
        
        logger.info("Scheduled sync tasks setup completed")
        return {
            'daily_schedule_created': created if 'daily_schedule' in locals() else False,
            'weekly_schedule_created': created if 'weekly_schedule' in locals() else False,
            'retry_schedule_created': created if 'retry_schedule' in locals() else False,
        }
        
    except Exception as e:
        logger.error(f"Failed to set up scheduled tasks: {e}")
        raise


def manual_sync_application(application_id: int, sync_type: str = 'incremental'):
    """
    Manually trigger sync for an application (for testing or on-demand sync)
    
    Args:
        application_id: Application ID to sync
        sync_type: 'full' or 'incremental'
        
    Returns:
        Task ID for tracking
    """
    try:
        application = Application.objects.get(id=application_id)
        
        task_id = async_task(
            'analytics.tasks.sync_application_task',
            application_id,
            application.owner_id,
            sync_type,
            group=f'manual_sync_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
            timeout=3600
        )
        
        logger.info(f"Manually triggered sync task {task_id} for application {application_id}")
        return task_id
        
    except Application.DoesNotExist:
        raise ValueError(f"Application {application_id} not found")
    except Exception as e:
        logger.error(f"Failed to manually trigger sync for application {application_id}: {e}")
        raise


def manual_indexing_task(application_id: int, user_id: int):
    """
    Tâche d'indexation manuelle pour une application spécifique (one-shot)
    
    Args:
        application_id: ID de l'application à indexer
        user_id: ID de l'utilisateur qui lance l'indexation
        
    Returns:
        Résultats de l'indexation
    """
    logger.info(f"Starting manual indexing for application {application_id}, user {user_id}")
    
    try:
        # Utiliser la même logique que background_indexing_task mais en mode one-shot
        return background_indexing_task(application_id, user_id, task_id=f"manual_{application_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        
    except Exception as e:
        logger.error(f"Manual indexing failed for application {application_id}: {e}")
        raise


def background_indexing_task(application_id: int, user_id: int, task_id: str = None):
    """
    Background task for indexing with progress tracking
    
    Args:
        application_id: Application ID to index
        user_id: User ID who owns the application
        task_id: Optional task ID for progress tracking
    """
    logger.info(f"Starting background indexing for application {application_id}, user {user_id}")
    try:
        # Get application and repositories
        application = Application.objects.get(id=application_id, owner_id=user_id)
        repositories = application.repositories.all()
        total_repos = repositories.count()
        
        if total_repos == 0:
            logger.warning(f"No repositories found for application {application_id}")
            return {
                'success': False,
                'error': 'No repositories found for this application',
                'task_id': task_id
            }
        
        # Choose indexing service based on configuration
        from django.conf import settings
        indexing_service = getattr(settings, 'INDEXING_SERVICE', 'git_local')
        
        if indexing_service == 'github_api':
            from .sync_service import SyncService
            sync_service = SyncService(user_id)
            logger.info(f"Using GitHub API indexing service for application {application_id}")
        else:
            from .git_sync_service import GitSyncService
            sync_service = GitSyncService(user_id)
            logger.info(f"Using Git local indexing service for application {application_id}")
        
        results = {
            'application_id': application_id,
            'indexing_service': indexing_service,
            'repositories_synced': 0,
            'total_commits_new': 0,
            'total_commits_updated': 0,
            'total_api_calls': 0,
            'errors': [],
            'total_repositories': total_repos,
            'task_id': task_id,
            'started_at': datetime.utcnow().isoformat()
        }
        
        # Process each repository
        for i, app_repo in enumerate(repositories, 1):
            try:
                logger.info(f"Indexing repository {i}/{total_repos}: {app_repo.github_repo_name}")
                
                # Check if github_repo_url exists, if not generate it
                repo_url = getattr(app_repo, 'github_repo_url', None)
                if not repo_url:
                    repo_url = f"https://github.com/{app_repo.github_repo_name}.git"
                    logger.warning(f"Missing github_repo_url for {app_repo.github_repo_name}, using generated URL: {repo_url}")
                
                if indexing_service == 'github_api':
                    # GitHub API service doesn't need repo_url
                    repo_result = sync_service.sync_repository(
                        app_repo.github_repo_name,
                        application_id,
                        'full'  # Always do full sync for indexing
                    )
                else:
                    # Git local service needs repo_url
                    repo_result = sync_service.sync_repository(
                        app_repo.github_repo_name,
                        repo_url,
                        application_id,
                        'full'  # Always do full sync for indexing
                    )
                
                results['repositories_synced'] += 1
                results['total_commits_new'] += repo_result['commits_new']
                results['total_commits_updated'] += repo_result['commits_updated']
                
                # Track API calls only for GitHub API service
                if indexing_service == 'github_api':
                    results['total_api_calls'] += repo_result.get('api_calls', 0)
                else:
                    results['total_api_calls'] = 0
                
                logger.info(f"Completed {i}/{total_repos} repositories")
                
            except Exception as e:
                error_msg = f"Failed to index repository {app_repo.github_repo_name}: {str(e)}"
                logger.error(error_msg)
                results['errors'].append(error_msg)
        
        # Run developer grouping after indexing - DISABLED (using new group_developer_identities_task instead)
        # try:
        #     from .developer_grouping_service import DeveloperGroupingService
        #     grouping_service = DeveloperGroupingService()
        #     grouping_result = grouping_service.auto_group_developers()
        #     logger.info(f"Developer grouping completed: {grouping_result}")
        # except Exception as e:
        #     logger.error(f"Developer grouping failed: {e}")
        #     results['errors'].append(f"Developer grouping failed: {str(e)}")
        
        results['completed_at'] = datetime.utcnow().isoformat()
        logger.info(f"Background indexing completed for application {application_id}: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Background indexing failed for application {application_id}: {e}")
        return {
            'success': False,
            'error': str(e),
            'task_id': task_id
        } 


def daily_indexing_release():
    """
    Django-Q task to index GitHub releases for all repositories of all applications (daily)
    """
    logger.info("Starting daily release indexing task")
    results = {
        'applications_processed': 0,
        'repositories_processed': 0,
        'releases_indexed': 0,
        'errors': []
    }
    try:
        applications_with_repos = Application.objects.filter(
            repositories__isnull=False
        ).distinct()
        for app in applications_with_repos:
            try:
                user_id = app.owner_id
                release_service = ReleaseIndexingService(user_id)
                repos = app.repositories.all()
                for repo in repos:
                    try:
                        release_ids = release_service.index_releases(app.id, repo.github_repo_name)
                        results['repositories_processed'] += 1
                        results['releases_indexed'] += len(release_ids)
                    except Exception as e:
                        error_msg = f"Failed to index releases for repo {repo.github_repo_name} (app {app.id}): {e}"
                        logger.error(error_msg)
                        results['errors'].append(error_msg)
                results['applications_processed'] += 1
            except Exception as e:
                error_msg = f"Failed to process application {app.id}: {e}"
                logger.error(error_msg)
                results['errors'].append(error_msg)
        logger.info(f"Daily release indexing completed: {results}")
        return results
    except Exception as e:
        logger.error(f"Daily release indexing task failed: {e}")
        raise 


def quality_analysis_task(application_id):
    """
    Tâche Q indépendante pour lancer l'analyse de qualité sur tous les commits d'une application.
    """
    from analytics.quality_service import QualityAnalysisService
    return QualityAnalysisService().analyze_commits_for_application(application_id)


def developer_grouping_task(application_id):
    """
    Tâche Q indépendante pour lancer le groupement automatique des développeurs d'une application.
    DISABLED - Use group_developer_identities_task instead
    """
    # from analytics.developer_grouping_service import DeveloperGroupingService
    # return DeveloperGroupingService(application_id).auto_group_developers()
    return {"disabled": True, "message": "Use group_developer_identities_task instead"} 


def quality_analysis_all_apps_task():
    """
    Tâche Q pour lancer l'analyse de qualité sur toutes les applications.
    """
    from applications.models import Application
    from analytics.quality_service import QualityAnalysisService
    processed = 0
    for app in Application.objects.all():
        processed += QualityAnalysisService().analyze_commits_for_application(app.id)
    return processed


def developer_grouping_all_apps_task():
    """
    Tâche Q pour lancer le groupement automatique des développeurs sur toutes les applications.
    DISABLED - Use group_developer_identities_task instead
    """
    # from applications.models import Application
    # from analytics.developer_grouping_service import DeveloperGroupingService
    # results = []
    # for app in Application.objects.all():
    #     results.append(DeveloperGroupingService(app.id).auto_group_developers())
    # return results
    return {"disabled": True, "message": "Use group_developer_identities_task instead"} 


def release_indexing_task(application_id):
    """
    Tâche Q pour indexer les releases de toutes les repositories d'une application.
    """
    from applications.models import Application
    from analytics.services import ReleaseIndexingService
    app = Application.objects.get(id=application_id)
    user_id = app.owner_id
    release_service = ReleaseIndexingService(user_id)
    results = []
    for repo in app.repositories.all():
        results.append(release_service.index_releases(app.id, repo.github_repo_name))
    return results


def release_indexing_all_apps_task():
    """
    Tâche Q pour indexer les releases de toutes les applications et repositories.
    """
    from applications.models import Application
    from analytics.services import ReleaseIndexingService
    results = []
    for app in Application.objects.all():
        user_id = app.owner_id
        release_service = ReleaseIndexingService(user_id)
        for repo in app.repositories.all():
            results.append(release_service.index_releases(app.id, repo.github_repo_name))
    return results 


def fetch_all_pull_requests_task(max_pages_per_repo=50, max_repos_per_run=10):
    """
    Tâche Q optimisée : va chercher les PRs FERMÉES pour les repos via l'API GitHub,
    avec des limites pour éviter les timeouts.
    
    Args:
        max_pages_per_repo: Nombre maximum de pages à traiter par repo (défaut: 50)
        max_repos_per_run: Nombre maximum de repos à traiter par exécution (défaut: 10)
    """
    from applications.models import Application
    from analytics.models import PullRequest
    from analytics.github_service import GitHubService
    from analytics.github_utils import get_github_token_for_user
    import dateutil.parser
    from datetime import timezone, datetime
    import logging
    import time

    logger = logging.getLogger(__name__)
    start_time = time.time()
    max_execution_time = 300  # 5 minutes max

    results = []
    repos_processed = 0
    
    for app in Application.objects.all():
        if repos_processed >= max_repos_per_run:
            logger.info(f"Reached max repos limit ({max_repos_per_run}), stopping")
            break
            
        if time.time() - start_time > max_execution_time:
            logger.info(f"Reached max execution time ({max_execution_time}s), stopping")
            break
            
        user_id = app.owner_id
        access_token = get_github_token_for_user(user_id)
        if not access_token:
            logger.warning(f"[App {app.id}] No GitHub token found for user {user_id}.")
            results.append({'app': app.id, 'error': 'No GitHub token'})
            continue
            
        gh = GitHubService(access_token)
        
        for repo in app.repositories.all():
            if repos_processed >= max_repos_per_run:
                break
                
            if time.time() - start_time > max_execution_time:
                break
                
            repo_name = repo.github_repo_name
            repos_processed += 1
            
            try:
                page = 1
                total_saved = 0
                pages_processed = 0
                
                while page <= max_pages_per_repo and pages_processed < max_pages_per_repo:
                    if time.time() - start_time > max_execution_time:
                        logger.info(f"[App {app.id}][Repo {repo_name}] Timeout reached, stopping at page {page}")
                        break
                        
                    url = f"https://api.github.com/repos/{repo_name}/pulls"
                    params = {'state': 'closed', 'per_page': 100, 'page': page}
                    
                    try:
                        prs, _ = gh._make_request(url, params)
                        pages_processed += 1
                        
                        logger.info(f"[App {app.id}][Repo {repo_name}] Page {page}: {len(prs)} PRs fetched.")
                        
                        if not prs or len(prs) == 0:
                            logger.info(f"[App {app.id}][Repo {repo_name}] No more PRs, stopping pagination")
                            break
                            
                        for pr in prs:
                            pr_number = pr.get('number')
                            try:
                                obj = PullRequest.objects(
                                    application_id=app.id, 
                                    repository_full_name=repo_name, 
                                    number=pr_number
                                ).first()
                                
                                if not obj:
                                    obj = PullRequest(
                                        application_id=app.id,
                                        repository_full_name=repo_name,
                                        number=pr_number
                                    )
                                    
                                obj.title = pr.get('title')
                                obj.author = pr.get('user', {}).get('login')
                                obj.created_at = dateutil.parser.parse(pr.get('created_at')) if pr.get('created_at') else None
                                obj.updated_at = dateutil.parser.parse(pr.get('updated_at')) if pr.get('updated_at') else None
                                obj.closed_at = dateutil.parser.parse(pr.get('closed_at')) if pr.get('closed_at') else None
                                obj.merged_at = dateutil.parser.parse(pr.get('merged_at')) if pr.get('merged_at') else None
                                obj.state = pr.get('state')
                                obj.url = pr.get('html_url')
                                obj.labels = [l['name'] for l in pr.get('labels', [])]
                                obj.payload = pr
                                obj.save()
                                
                                total_saved += 1
                                
                            except Exception as e:
                                logger.error(f"[App {app.id}][Repo {repo_name}] Error saving PR #{pr_number}: {e}")
                                
                        page += 1
                        
                        # Petit délai pour éviter de surcharger l'API
                        time.sleep(0.1)
                        
                    except Exception as e:
                        error_msg = str(e)
                        if "Repository not found or not accessible" in error_msg:
                            logger.warning(f"[App {app.id}][Repo {repo_name}] Repository not accessible with current token - skipping")
                            results.append({
                                'app': app.id, 
                                'repo': repo_name, 
                                'status': 'skipped',
                                'reason': 'Repository not accessible with current token',
                                'pages_processed': 0,
                                'total_saved': 0
                            })
                            break
                        else:
                            logger.error(f"[App {app.id}][Repo {repo_name}] Error fetching page {page}: {e}")
                            break
                
                execution_time = time.time() - start_time
                logger.info(f"[App {app.id}][Repo {repo_name}] Completed: {total_saved} PRs saved, {pages_processed} pages processed in {execution_time:.1f}s")
                
                results.append({
                    'app': app.id, 
                    'repo': repo_name, 
                    'status': 'ok', 
                    'total_saved': total_saved,
                    'pages_processed': pages_processed,
                    'execution_time': execution_time
                })
                
            except Exception as e:
                logger.error(f"[App {app.id}][Repo {repo_name}] Error: {e}")
                results.append({'app': app.id, 'repo': repo_name, 'error': str(e)})
    
    total_execution_time = time.time() - start_time
    logger.info(f"Task completed: {repos_processed} repos processed in {total_execution_time:.1f}s")
    
    return {
        'results': results,
        'repos_processed': repos_processed,
        'total_execution_time': total_execution_time,
        'max_pages_per_repo': max_pages_per_repo,
        'max_repos_per_run': max_repos_per_run
    } 


def group_developer_identities_task(application_id=None):
    """
    Tâche Django-Q pour regrouper automatiquement les identités de développeurs.
    
    Cette tâche :
    1. Lit tous les commits de l'application (ou tous si application_id=None)
    2. Extrait les identités uniques (author_name + author_email)
    3. Crée/met à jour les DeveloperAlias
    4. Applique les règles de regroupement pour créer/lier les Developer
    
    Args:
        application_id: ID de l'application à traiter (None pour toutes)
    
    Returns:
        dict: Résultats du regroupement
    """
    import re
    import unicodedata
    from difflib import SequenceMatcher
    from analytics.models import Commit, Developer, DeveloperAlias
    
    logger.info(f"Starting developer identity grouping task for application {application_id}")
    
    def normalize_name(name):
        """Normalise un nom : minuscules, sans accents, sans espaces/tirets/underscores"""
        if not name:
            return ""
        # Supprimer les accents
        name = unicodedata.normalize('NFD', name).encode('ascii', 'ignore').decode('ascii')
        # Minuscules et supprimer caractères spéciaux
        name = re.sub(r'[^a-zA-Z0-9]', '', name.lower())
        return name
    
    def extract_email_local(email):
        """Extrait la partie locale d'un email (avant @)"""
        if not email or '@' not in email:
            return ""
        return email.split('@')[0].lower()
    
    def extract_initials_from_name(name):
        """Extrait les initiales d'un nom complet"""
        if not name:
            return ""
        parts = re.split(r'[^a-zA-Z]+', name.lower())
        return ''.join([part[0] for part in parts if part])
    
    def name_initials_match(identity1, identity2):
        """Vérifie si nom + initiales correspondent entre deux identités"""
        # Cas 1: nom complet vs initiales dans email
        name1_parts = [part for part in re.split(r'[^a-zA-Z]+', identity1['name'].lower()) if part]
        name2_parts = [part for part in re.split(r'[^a-zA-Z]+', identity2['name'].lower()) if part]
        email1_local = extract_email_local(identity1['email'])
        email2_local = extract_email_local(identity2['email'])
        
        # Vérifier si l'email local contient les initiales du nom
        if len(name1_parts) >= 2 and name1_parts[0] and name1_parts[-1]:
            initials1 = name1_parts[0][0] + name1_parts[-1]  # première lettre prénom + nom
            if initials1 in email2_local or email2_local in initials1:
                return True
        
        if len(name2_parts) >= 2 and name2_parts[0] and name2_parts[-1]:
            initials2 = name2_parts[0][0] + name2_parts[-1]  # première lettre prénom + nom
            if initials2 in email1_local or email1_local in initials2:
                return True
        
        # Cas 2: prénom.nom dans email vs nom complet
        if '.' in email1_local:
            email_parts = email1_local.split('.')
            if len(email_parts) == 2 and len(name2_parts) >= 2 and name2_parts[0] and name2_parts[-1]:
                if (email_parts[0] in name2_parts[0] or name2_parts[0] in email_parts[0]) and \
                   (email_parts[1] in name2_parts[-1] or name2_parts[-1] in email_parts[1]):
                    return True
        
        if '.' in email2_local:
            email_parts = email2_local.split('.')
            if len(email_parts) == 2 and len(name1_parts) >= 2 and name1_parts[0] and name1_parts[-1]:
                if (email_parts[0] in name1_parts[0] or name1_parts[0] in email_parts[0]) and \
                   (email_parts[1] in name1_parts[-1] or name1_parts[-1] in email_parts[1]):
                    return True
        
        return False
    
    def fuzzy_match(str1, str2, threshold=0.85):
        """Calcule la similarité entre deux chaînes"""
        if not str1 or not str2:
            return False
        return SequenceMatcher(None, str1, str2).ratio() >= threshold
    
    def should_group_identities(identity1, identity2):
        """Détermine si deux identités doivent être regroupées"""
        email1_local = extract_email_local(identity1['email'])
        email2_local = extract_email_local(identity2['email'])
        name1_norm = normalize_name(identity1['name'])
        name2_norm = normalize_name(identity2['name'])
        
        # 1. Email local exact match
        if email1_local and email2_local and email1_local == email2_local:
            return True, "email_local_match"
        
        # 2. Nom normalisé exact match
        if name1_norm and name2_norm and name1_norm == name2_norm:
            return True, "normalized_name_match"
        
        # 3. Email ↔ Name cross match
        if (email1_local and name2_norm and email1_local == name2_norm) or \
           (email2_local and name1_norm and email2_local == name1_norm):
            return True, "email_name_cross_match"
        
        # 4. Initiales + nom match
        if name_initials_match(identity1, identity2):
            return True, "name_initials_match"
        
        # 5. Fuzzy match sur noms normalisés
        if name1_norm and name2_norm and len(name1_norm) > 3 and len(name2_norm) > 3:
            if fuzzy_match(name1_norm, name2_norm, 0.85):
                return True, "fuzzy_name_match"
        
        # 6. Patterns spéciaux GitHub/GitLab
        if 'noreply.github.com' in identity1['email'] or 'noreply.gitlab.com' in identity1['email']:
            github_user = extract_email_local(identity1['email'])
            if github_user and name2_norm and github_user in name2_norm:
                return True, "github_pattern_match"
        
        if 'noreply.github.com' in identity2['email'] or 'noreply.gitlab.com' in identity2['email']:
            github_user = extract_email_local(identity2['email'])
            if github_user and name1_norm and github_user in name1_norm:
                return True, "github_pattern_match"
        
        return False, None
    
    try:
        # Construire la requête pour les commits
        commit_filter = {}
        if application_id:
            commit_filter['application_id'] = application_id
        
        # Extraire toutes les identités uniques des commits
        commits = Commit.objects(**commit_filter)
        identities = {}  # key: (name, email), value: {name, email, commit_count, first_seen, last_seen}
        
        logger.info(f"Processing {commits.count()} commits to extract identities")
        
        for commit in commits:
            # Traiter author
            author_key = (commit.author_name, commit.author_email)
            if author_key not in identities:
                identities[author_key] = {
                    'name': commit.author_name,
                    'email': commit.author_email,
                    'commit_count': 0,
                    'first_seen': commit.authored_date,
                    'last_seen': commit.authored_date
                }
            
            identities[author_key]['commit_count'] += 1
            if commit.authored_date < identities[author_key]['first_seen']:
                identities[author_key]['first_seen'] = commit.authored_date
            if commit.authored_date > identities[author_key]['last_seen']:
                identities[author_key]['last_seen'] = commit.authored_date
            
            # Traiter committer s'il est différent de l'author
            if commit.committer_name != commit.author_name or commit.committer_email != commit.author_email:
                committer_key = (commit.committer_name, commit.committer_email)
                if committer_key not in identities:
                    identities[committer_key] = {
                        'name': commit.committer_name,
                        'email': commit.committer_email,
                        'commit_count': 0,
                        'first_seen': commit.committed_date,
                        'last_seen': commit.committed_date
                    }
                
                identities[committer_key]['commit_count'] += 1
                if commit.committed_date < identities[committer_key]['first_seen']:
                    identities[committer_key]['first_seen'] = commit.committed_date
                if commit.committed_date > identities[committer_key]['last_seen']:
                    identities[committer_key]['last_seen'] = commit.committed_date
        
        logger.info(f"Found {len(identities)} unique identities")
        
        # Créer/mettre à jour les DeveloperAlias
        aliases_created = 0
        aliases_updated = 0
        
        for identity_data in identities.values():
            alias_filter = {
                'name': identity_data['name'],
                'email': identity_data['email']
            }
            
            alias = DeveloperAlias.objects(**alias_filter).first()
            if not alias:
                alias = DeveloperAlias(**alias_filter)
                aliases_created += 1
            else:
                aliases_updated += 1
            
            alias.commit_count = identity_data['commit_count']
            alias.first_seen = identity_data['first_seen']
            alias.last_seen = identity_data['last_seen']
            alias.save()
        
        logger.info(f"Created {aliases_created} new aliases, updated {aliases_updated} existing aliases")
        
        # Regroupement automatique
        # Récupérer tous les aliases non groupés pour cette application
        ungrouped_aliases = list(DeveloperAlias.objects(developer=None))
        
        if application_id:
            # Filtrer par application en regardant les commits
            app_emails = set()
            for commit in Commit.objects(application_id=application_id):
                app_emails.add(commit.author_email)
                app_emails.add(commit.committer_email)
            
            ungrouped_aliases = [alias for alias in ungrouped_aliases if alias.email in app_emails]
        
        logger.info(f"Processing {len(ungrouped_aliases)} ungrouped aliases for grouping")
        
        developers_created = 0
        aliases_grouped = 0
        grouping_details = []
        
        # Algorithme de regroupement
        processed_aliases = set()
        
        for i, alias1 in enumerate(ungrouped_aliases):
            if alias1.id in processed_aliases:
                continue
            
            # Créer un nouveau groupe avec cette alias
            group = [alias1]
            identity1 = {'name': alias1.name, 'email': alias1.email}
            
            # Chercher d'autres aliases qui correspondent
            for j, alias2 in enumerate(ungrouped_aliases[i+1:], i+1):
                if alias2.id in processed_aliases:
                    continue
                
                identity2 = {'name': alias2.name, 'email': alias2.email}
                should_group, reason = should_group_identities(identity1, identity2)
                
                if should_group:
                    group.append(alias2)
                    grouping_details.append({
                        'alias1': f"{alias1.name} ({alias1.email})",
                        'alias2': f"{alias2.name} ({alias2.email})",
                        'reason': reason
                    })
            
            # Créer un Developer pour ce groupe
            if len(group) > 0:
                # Choisir l'alias avec le plus de commits comme identité principale
                primary_alias = max(group, key=lambda a: a.commit_count)
                
                developer = Developer(
                    primary_name=primary_alias.name,
                    primary_email=primary_alias.email,
                    application_id=application_id,
                    is_auto_grouped=True,
                    confidence_score=min(100, 50 + len(group) * 10)  # Score basé sur le nombre d'aliases
                )
                developer.save()
                developers_created += 1
                
                # Lier toutes les aliases à ce developer
                for alias in group:
                    alias.developer = developer
                    alias.save()
                    processed_aliases.add(alias.id)
                    aliases_grouped += 1
        
        results = {
            'application_id': application_id,
            'identities_found': len(identities),
            'aliases_created': aliases_created,
            'aliases_updated': aliases_updated,
            'developers_created': developers_created,
            'aliases_grouped': aliases_grouped,
            'grouping_details': grouping_details[:10],  # Limiter pour éviter des logs trop longs
            'total_grouping_details': len(grouping_details)
        }
        
        logger.info(f"Developer identity grouping completed: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Developer identity grouping task failed: {e}")
        raise


def daily_indexing_all_apps_task():
    """
    Tâche planifiée unique : lance l'indexation pour toutes les applications.
    """
    from applications.models import Application
    from django.utils import timezone
    results = []
    for app in Application.objects.all():
        # Lancer l'indexation en asynchrone pour chaque application
        task_id = async_task('analytics.tasks.background_indexing_task', app.id, app.owner_id, None)
        results.append({'app_id': app.id, 'task_id': task_id})
    return results