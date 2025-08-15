from django.db import models
from django.contrib.auth.models import User
from django.utils.module_loading import import_string
import logging

logger = logging.getLogger(__name__)


class Repository(models.Model):
    """Repository model for storing indexed repositories"""
    
    name = models.CharField(max_length=255)
    full_name = models.CharField(max_length=255, unique=True)  # owner/repo-name
    description = models.TextField(blank=True, null=True)
    private = models.BooleanField(default=False)
    fork = models.BooleanField(default=False)
    language = models.CharField(max_length=50, blank=True, null=True)
    stars = models.IntegerField(default=0)
    forks = models.IntegerField(default=0)
    size = models.BigIntegerField(default=0)
    default_branch = models.CharField(max_length=100, default='main')
    
    # GitHub metadata
    github_id = models.BigIntegerField(unique=True)
    html_url = models.URLField()
    clone_url = models.URLField()
    ssh_url = models.URLField()
    
    # Indexing status
    is_indexed = models.BooleanField(default=False)
    last_indexed = models.DateTimeField(null=True, blank=True)
    commit_count = models.IntegerField(default=0)
    
    # KLOC (Kilo Lines of Code) tracking - now using MongoDB via properties
    # kloc = models.FloatField(default=0.0)  # Current KLOC value - REMOVED
    # kloc_calculated_at = models.DateTimeField(null=True, blank=True)  # When KLOC was last calculated - REMOVED
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Owner
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='repositories')
    
    class Meta:
        verbose_name_plural = "Repositories"
        ordering = ['-updated_at']
    
    def __str__(self):
        return self.full_name
    
    @property
    def owner_name(self):
        """Extract owner name from full_name"""
        return self.full_name.split('/')[0] if '/' in self.full_name else ''
    
    @property
    def repo_name(self):
        """Extract repository name from full_name"""
        return self.full_name.split('/')[1] if '/' in self.full_name else self.name
    
    def should_calculate_kloc(self, max_days=30):
        """
        Check if KLOC should be recalculated based on MongoDB history
        
        Args:
            max_days: Maximum days since last calculation before requiring recalculation
            
        Returns:
            tuple: (should_calculate, reason)
        """
        try:
            from analytics.models import RepositoryKLOCHistory
            latest = RepositoryKLOCHistory.objects.filter(
                repository_id=self.id
            ).order_by('-calculated_at').first()
            
            if not latest:
                return True, "kloc_missing"
            
            from django.utils import timezone
            from datetime import timezone as dt_timezone
            
            # Ensure both dates are timezone-aware
            now = timezone.now()
            calculated_at = latest.calculated_at
            
            # If calculated_at is naive, assume UTC
            if calculated_at.tzinfo is None:
                calculated_at = calculated_at.replace(tzinfo=dt_timezone.utc)
            
            days_since = (now - calculated_at).days
            
            if days_since >= max_days:
                return True, f"kloc_old_{days_since}_days"
            else:
                return False, f"kloc_recent_{days_since}_days"
                
        except Exception as e:
            # Log error but default to calculating
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Error checking KLOC history for {self.full_name}: {e}")
            return True, "kloc_error"

    @property
    def kloc(self):
        """Get the latest KLOC value from MongoDB history"""
        try:
            from analytics.models import RepositoryKLOCHistory
            latest = RepositoryKLOCHistory.objects.filter(
                repository_id=self.id
            ).order_by('-calculated_at').first()
            return latest.kloc if latest else 0.0
        except Exception:
            return 0.0

    @property
    def kloc_calculated_at(self):
        """Get the latest KLOC calculation date from MongoDB history"""
        try:
            from analytics.models import RepositoryKLOCHistory
            latest = RepositoryKLOCHistory.objects.filter(
                repository_id=self.id
            ).order_by('-calculated_at').first()
            return latest.calculated_at if latest else None
        except Exception:
            return None

    def delete(self, *args, **kwargs):
        """
        Standard delete method - no cascade delete by default.
        Use cascade_delete() method explicitly for cascade deletion.
        """
        super().delete(*args, **kwargs)
    
    def cascade_delete(self, confirm_repository_name=None):
        """
        SAFE cascade delete for all related data.
        
        This method requires explicit confirmation by passing the repository name.
        This prevents accidental deletion of wrong data.
        
        Usage:
            repo.cascade_delete(confirm_repository_name=repo.full_name)
        
        Collections that need to be cleaned up:
        - Commit (repository_full_name)
        - PullRequest (repository_full_name)
        - Deployment (repository_full_name) 
        - Release (repository_full_name)
        - SBOM (repository_full_name)
        - SBOMComponent (via sbom_id reference)
        - SonarCloudMetrics (repository_full_name)
        - IndexingState (repository_full_name)
        - RepositoryStats (repository_full_name)
        - SyncLog (repository_full_name)
        - CodeQLVulnerability (repository_full_name)
        - RepositoryKLOCHistory (repository_full_name)
        - SecurityHealthHistory (repository_full_name)
        
        TODO: Update this list when adding new collections
        """
        # Safety check - require explicit confirmation
        if confirm_repository_name != self.full_name:
            raise ValueError(
                f"Cascade delete requires explicit confirmation. "
                f"Expected: {self.full_name}, Got: {confirm_repository_name}"
            )
        
        logger.info(f"🔄 Starting SAFE cascade delete for repository: {self.full_name}")
        
        try:
            # Collections with direct repository_full_name field (excluding SBOM which needs special handling)
            direct_collections = [
                ('analytics.models.Commit', 'repository_full_name'),
                ('analytics.models.PullRequest', 'repository_full_name'),
                ('analytics.models.Deployment', 'repository_full_name'),
                ('analytics.models.Release', 'repository_full_name'),
                ('analytics.models.SonarCloudMetrics', 'repository_full_name'),
                ('analytics.models.IndexingState', 'repository_full_name'),
                ('analytics.models.RepositoryStats', 'repository_full_name'),
                ('analytics.models.SyncLog', 'repository_full_name'),
                ('analytics.models.CodeQLVulnerability', 'repository_full_name'),
                ('analytics.models.RepositoryKLOCHistory', 'repository_full_name'),
                ('analytics.models.SecurityHealthHistory', 'repository_full_name'),
            ]
            
            # Clean up direct collections
            total_deleted = 0
            for model_path, field_name in direct_collections:
                try:
                    model = import_string(model_path)
                    # SAFE: Only delete records for THIS specific repository
                    query = {field_name: self.full_name}
                    deleted_count = model.objects(**query).delete()
                    if deleted_count > 0:
                        logger.info(f"✅ Deleted {deleted_count} {model.__name__} records for {self.full_name}")
                        total_deleted += deleted_count
                except Exception as e:
                    logger.error(f"❌ Failed to delete {model_path} for {self.full_name}: {e}")
            
            # Clean up referenced collections (SBOM components)
            try:
                from analytics.models import SBOM, SBOMComponent
                
                # SAFE: Only get SBOMs for THIS specific repository
                sboms = list(SBOM.objects(repository_full_name=self.full_name))
                sbom_count = len(sboms)
                logger.info(f"📦 Found {sbom_count} SBOMs for {self.full_name}")
                
                # Delete components for each SBOM
                for sbom in sboms:
                    # SAFE: Only delete components for THIS specific SBOM
                    component_deleted = SBOMComponent.objects(sbom_id=sbom).delete()
                    
                    if component_deleted > 0:
                        logger.info(f"✅ Deleted {component_deleted} SBOMComponent records for SBOM {sbom.id}")
                
                # Now delete the SBOMs themselves
                sbom_deleted = SBOM.objects(repository_full_name=self.full_name).delete()
                if sbom_deleted > 0:
                    logger.info(f"✅ Deleted {sbom_deleted} SBOM records for {self.full_name}")
                    total_deleted += sbom_deleted
                    
            except Exception as e:
                logger.error(f"❌ Failed to delete SBOM-related data for {self.full_name}: {e}")
            
            logger.info(f"🎉 Completed SAFE cascade delete for {self.full_name}. Total records deleted: {total_deleted}")
            
            # Finally delete the repository itself
            super().delete()
            
        except Exception as e:
            logger.error(f"💥 Error during cascade delete for {self.full_name}: {e}")
            raise
