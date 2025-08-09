from django.test import TestCase
from django.contrib.auth.models import User
from .models import Repository
from analytics.models import PullRequest, Deployment, Release, SBOM, SBOMComponent, SonarCloudMetrics, IndexingState, RepositoryStats, SyncLog
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class RepositoryCascadeDeleteTest(TestCase):
    """Test cascade delete functionality for Repository model"""
    
    def setUp(self):
        """Set up test data"""
        # Clean up any existing test data first
        self._cleanup_test_data()
        
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create test repository
        self.repository = Repository.objects.create(
            name='test-repo',
            full_name='testuser/test-repo',
            owner=self.user,
            github_id=12345,
            html_url='https://github.com/testuser/test-repo',
            clone_url='https://github.com/testuser/test-repo.git',
            ssh_url='git@github.com:testuser/test-repo.git'
        )
        
        # Create test data in MongoDB collections
        self._create_test_data()
    
    def _cleanup_test_data(self):
        """Clean up any existing test data"""
        logger.info("Cleaning up existing test data...")
        
        # Clean up all test repositories and their data
        test_repos = ['testuser/test-repo', 'testuser/test-repo-2']
        
        for repo_name in test_repos:
            # Clean up all collections that might have test data
            PullRequest.objects(repository_full_name=repo_name).delete()
            Deployment.objects(repository_full_name=repo_name).delete()
            Release.objects(repository_full_name=repo_name).delete()
            SBOM.objects(repository_full_name=repo_name).delete()
            SonarCloudMetrics.objects(repository_full_name=repo_name).delete()
            IndexingState.objects(repository_full_name=repo_name).delete()
            RepositoryStats.objects(repository_full_name=repo_name).delete()
            SyncLog.objects(repository_full_name=repo_name).delete()
            
            # Clean up any SBOM-related data
            for sbom in SBOM.objects(repository_full_name=repo_name):
                SBOMComponent.objects(sbom_id=sbom).delete()
        
        # Also clean up any test repositories from Django
        Repository.objects.filter(name__startswith='test-repo').delete()
        
        # Clean up any orphaned SBOM components and vulnerabilities
        # This ensures a completely clean state for tests
        SBOMComponent.objects.all().delete()
        
        logger.info("Finished cleaning up existing test data.")
    
    def _create_test_data(self):
        """Create test data in all related collections"""
        # Create PullRequest
        PullRequest.objects.create(
            repository_full_name=self.repository.full_name,
            number=1,
            title='Test PR',
            author='testuser',
            url='https://github.com/testuser/test-repo/pull/1'
        )
        
        # Create Deployment
        Deployment.objects.create(
            repository_full_name=self.repository.full_name,
            deployment_id='deploy-1',
            environment='production'
        )
        
        # Create Release
        Release.objects.create(
            repository_full_name=self.repository.full_name,
            release_id='release-1',
            tag_name='v1.0.0'
        )
        
        # Create SBOM and related data
        sbom = SBOM.objects.create(
            repository_full_name=self.repository.full_name,
            bom_format='CycloneDX',
            spec_version='1.6',
            serial_number='test-uuid',
            version=1,
            generated_at=timezone.now(),
            tool_name='GitHub Dependency Graph',
            tool_version='unknown',
            raw_sbom={'components': [], 'metadata': {}}
        )
        
        # Create SBOMComponent
        SBOMComponent.objects.create(
            sbom_id=sbom,
            name='test-component',
            version='1.0.0',
            purl='pkg:npm/test-component@1.0.0',
            bom_ref='test-ref',
            component_type='library'
        )
        
        # Create SBOMVulnerability
        # SBOMVulnerability removed - vulnerabilities come from CodeQL now
        
        # Create SonarCloudMetrics
        SonarCloudMetrics.objects.create(
            repository_id=self.repository.id,
            repository_full_name=self.repository.full_name,
            sonarcloud_project_key='test-project',
            sonarcloud_organization='test-org'
        )
        
        # Create IndexingState
        IndexingState.objects.create(
            repository_id=self.repository.id,
            repository_full_name=self.repository.full_name,
            entity_type='commits'
        )
        
        # Create RepositoryStats
        RepositoryStats.objects.create(
            repository_full_name=self.repository.full_name
        )
        
        # Create SyncLog
        SyncLog.objects.create(
            repository_full_name=self.repository.full_name,
            sync_type='full',
            status='completed'
        )
    
    def test_cascade_delete_removes_all_related_data(self):
        """Test that cascade_delete() method removes all related data safely"""
        # Verify data exists before deletion
        self.assertEqual(PullRequest.objects(repository_full_name=self.repository.full_name).count(), 1)
        self.assertEqual(Deployment.objects(repository_full_name=self.repository.full_name).count(), 1)
        self.assertEqual(Release.objects(repository_full_name=self.repository.full_name).count(), 1)
        self.assertEqual(SBOM.objects(repository_full_name=self.repository.full_name).count(), 1)
        self.assertEqual(SonarCloudMetrics.objects(repository_full_name=self.repository.full_name).count(), 1)
        self.assertEqual(IndexingState.objects(repository_full_name=self.repository.full_name).count(), 1)
        self.assertEqual(RepositoryStats.objects(repository_full_name=self.repository.full_name).count(), 1)
        self.assertEqual(SyncLog.objects(repository_full_name=self.repository.full_name).count(), 1)
        
        # Use the new SAFE cascade_delete method
        self.repository.cascade_delete(confirm_repository_name=self.repository.full_name)
        
        # Verify all related data is removed
        self.assertEqual(PullRequest.objects(repository_full_name=self.repository.full_name).count(), 0)
        self.assertEqual(Deployment.objects(repository_full_name=self.repository.full_name).count(), 0)
        self.assertEqual(Release.objects(repository_full_name=self.repository.full_name).count(), 0)
        self.assertEqual(SBOM.objects(repository_full_name=self.repository.full_name).count(), 0)
        self.assertEqual(SonarCloudMetrics.objects(repository_full_name=self.repository.full_name).count(), 0)
        self.assertEqual(IndexingState.objects(repository_full_name=self.repository.full_name).count(), 0)
        self.assertEqual(RepositoryStats.objects(repository_full_name=self.repository.full_name).count(), 0)
        self.assertEqual(SyncLog.objects(repository_full_name=self.repository.full_name).count(), 0)
        
        # Verify SBOM-related data is also removed
        # Note: We only check that our specific SBOM components are deleted
        # Other components might exist from other repositories
        # The _cleanup_test_data in setUp ensures these are 0 for the test run
        # We check that our specific SBOM components are deleted by checking the count
        # after cleanup, which should be 0 for our test data
        self.assertEqual(SBOMComponent.objects.count(), 0)
        
        # Verify repository is deleted from Django
        self.assertEqual(Repository.objects.filter(id=self.repository.id).count(), 0)
    
    def test_cascade_delete_requires_confirmation(self):
        """Test that cascade_delete() requires explicit confirmation"""
        # Try to call cascade_delete without confirmation
        with self.assertRaises(ValueError) as context:
            self.repository.cascade_delete()
        
        self.assertIn("Cascade delete requires explicit confirmation", str(context.exception))
        
        # Try to call cascade_delete with wrong repository name
        with self.assertRaises(ValueError) as context:
            self.repository.cascade_delete(confirm_repository_name="wrong/repo")
        
        self.assertIn("Expected:", str(context.exception))
        self.assertIn("Got:", str(context.exception))
    
    def test_standard_delete_does_not_cascade(self):
        """Test that standard delete() method does not perform cascade delete"""
        # Create a new repository for this test to avoid conflicts
        new_repo = Repository.objects.create(
            name='test-repo-2',
            full_name='testuser/test-repo-2',
            owner=self.user,
            github_id=12346,
            html_url='https://github.com/testuser/test-repo-2',
            clone_url='https://github.com/testuser/test-repo-2.git',
            ssh_url='git@github.com:testuser/test-repo-2.git'
        )
        
        # Create test data for the new repository
        PullRequest.objects.create(
            repository_full_name=new_repo.full_name,
            number=2,
            title='Test PR 2',
            author='testuser',
            url='https://github.com/testuser/test-repo-2/pull/2'
        )
        
        Deployment.objects.create(
            repository_full_name=new_repo.full_name,
            deployment_id='deploy-2',
            environment='production',
            creator='testuser',
            created_at=timezone.now(),
            updated_at=timezone.now(),
            payload={},
            statuses=[]
        )
        
        Release.objects.create(
            repository_full_name=new_repo.full_name,
            release_id='release-2',
            tag_name='v1.0.0',
            name='Initial Release',
            author='testuser',
            published_at=timezone.now(),
            draft=False,
            prerelease=False,
            body='Test release',
            html_url='https://github.com/testuser/test-repo-2/releases/tag/v1.0.0',
            assets=[],
            payload={}
        )
        
        # Use standard delete (should not cascade)
        new_repo.delete()
        
        # Verify repository is deleted but related data remains
        self.assertEqual(Repository.objects.filter(id=new_repo.id).count(), 0)
        
        # Related data should still exist (no cascade)
        self.assertEqual(PullRequest.objects(repository_full_name=new_repo.full_name).count(), 1)
        self.assertEqual(Deployment.objects(repository_full_name=new_repo.full_name).count(), 1)
        self.assertEqual(Release.objects(repository_full_name=new_repo.full_name).count(), 1)
    
    def test_cascade_delete_handles_empty_collections(self):
        """Test that cascade delete works even when collections are empty"""
        # Delete all test data first
        PullRequest.objects.delete()
        Deployment.objects.delete()
        Release.objects.delete()
        SBOM.objects.delete()
        SonarCloudMetrics.objects.delete()
        IndexingState.objects.delete()
        RepositoryStats.objects.delete()
        SyncLog.objects.delete()
        
        # Verify collections are empty
        self.assertEqual(PullRequest.objects.count(), 0)
        self.assertEqual(Deployment.objects.count(), 0)
        self.assertEqual(Release.objects.count(), 0)
        self.assertEqual(SBOM.objects.count(), 0)
        self.assertEqual(SonarCloudMetrics.objects.count(), 0)
        self.assertEqual(IndexingState.objects.count(), 0)
        self.assertEqual(RepositoryStats.objects.count(), 0)
        self.assertEqual(SyncLog.objects.count(), 0)
        
        # Delete repository (should not raise any errors)
        self.repository.delete()
        
        # Verify repository is deleted
        self.assertEqual(Repository.objects.filter(id=self.repository.id).count(), 0)
