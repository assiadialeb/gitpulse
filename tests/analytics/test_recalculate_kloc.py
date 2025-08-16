import pytest
import tempfile
import os
from unittest.mock import patch, MagicMock
from django.test import TestCase
from analytics.management.commands.recalculate_kloc import Command
from repositories.models import Repository
from analytics.git_service import GitService


class TestRecalculateKLOC(TestCase):
    """Test cases for recalculate_kloc command security."""

    def setUp(self):
        """Set up test fixtures."""
        self.command = Command()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_sanitized_path_construction_in_cleanup(self):
        """Test that cleanup uses sanitized directory names."""
        # Create a mock repository with malicious name
        mock_repo = MagicMock()
        mock_repo.full_name = "owner/../../../etc/passwd"
        mock_repo.id = 1
        mock_repo.owner.id = 1
        mock_repo.clone_url = "https://github.com/owner/repo.git"

        # Mock GitService and its methods
        with patch('analytics.management.commands.recalculate_kloc.GitService') as mock_git_service_class:
            mock_git_service = MagicMock()
            mock_git_service_class.return_value = mock_git_service
            
            # Mock the sanitization method
            mock_git_service._sanitize_repo_dir_name.return_value = "owner_etc_passwd"
            mock_git_service.clone_repository.return_value = "/tmp/safe/path"

            # Mock other dependencies
            with patch('analytics.management.commands.recalculate_kloc.GitHubTokenService.get_token_for_repository_access') as mock_token:
                mock_token.return_value = "fake_token"
                
                with patch('analytics.management.commands.recalculate_kloc.assert_safe_repo_path') as mock_safe_path:
                    mock_safe_path.return_value = "/tmp/safe/path"
                    
                    with patch('analytics.management.commands.recalculate_kloc.KLOCService') as mock_kloc_class:
                        mock_kloc_service = MagicMock()
                        mock_kloc_class.return_value = mock_kloc_service
                        mock_kloc_service.calculate_kloc.return_value = {
                            'kloc': 1.0,
                            'total_lines': 100,
                            'language_breakdown': {'python': 100},
                            'calculated_at': '2023-01-01'
                        }
                        
                        with patch('analytics.management.commands.recalculate_kloc.RepositoryKLOCHistory') as mock_history:
                            mock_history_instance = MagicMock()
                            mock_history.return_value = mock_history_instance
                            
                            # Mock tempfile.gettempdir to return our test directory
                            with patch('tempfile.gettempdir', return_value=self.temp_dir):
                                with patch('os.path.exists', return_value=False):
                                    with patch('shutil.rmtree') as mock_rmtree:
                                        # Execute the method
                                        result = self.command.recalculate_kloc_for_repository(mock_repo)
                                        
                                        # Verify sanitization was called
                                        mock_git_service._sanitize_repo_dir_name.assert_called_once_with("owner/../../../etc/passwd")
                                        
                                        # Verify the result is successful
                                        self.assertTrue(result['success'])

    def test_path_traversal_protection_in_cleanup(self):
        """Test that cleanup is protected against path traversal attacks."""
        malicious_inputs = [
            "owner/../../../etc/passwd",
            "user/..\\..\\..\\windows\\system32",
            "org/repo/with/slashes",
            "owner/repo*with*special*chars",
        ]
        
        for malicious_input in malicious_inputs:
            # Create a mock repository with malicious name
            mock_repo = MagicMock()
            mock_repo.full_name = malicious_input
            mock_repo.id = 1
            mock_repo.owner.id = 1
            mock_repo.clone_url = "https://github.com/owner/repo.git"

            # Mock GitService
            with patch('analytics.management.commands.recalculate_kloc.GitService') as mock_git_service_class:
                mock_git_service = MagicMock()
                mock_git_service_class.return_value = mock_git_service
                mock_git_service.clone_repository.return_value = "/tmp/safe/path"
                
                # Mock the sanitization method to return a safe name
                mock_git_service._sanitize_repo_dir_name.return_value = "safe_name"

                # Mock other dependencies
                with patch('analytics.management.commands.recalculate_kloc.GitHubTokenService.get_token_for_repository_access'):
                    with patch('analytics.management.commands.recalculate_kloc.assert_safe_repo_path'):
                        with patch('analytics.management.commands.recalculate_kloc.KLOCService'):
                            with patch('analytics.management.commands.recalculate_kloc.RepositoryKLOCHistory'):
                                with patch('tempfile.gettempdir', return_value=self.temp_dir):
                                    with patch('os.path.exists', return_value=False):
                                        with patch('shutil.rmtree'):
                                            # Execute the method
                                            result = self.command.recalculate_kloc_for_repository(mock_repo)
                                            
                                            # Verify sanitization was called with the malicious input
                                            mock_git_service._sanitize_repo_dir_name.assert_called_once_with(malicious_input)
                                            
                                            # Verify the result is successful
                                            self.assertTrue(result['success'])

    def test_cleanup_uses_safe_path_construction(self):
        """Test that cleanup constructs safe paths."""
        mock_repo = MagicMock()
        mock_repo.full_name = "owner/repo"
        mock_repo.id = 1
        mock_repo.owner.id = 1
        mock_repo.clone_url = "https://github.com/owner/repo.git"

        # Mock GitService
        with patch('analytics.management.commands.recalculate_kloc.GitService') as mock_git_service_class:
            mock_git_service = MagicMock()
            mock_git_service_class.return_value = mock_git_service
            mock_git_service.clone_repository.return_value = "/tmp/safe/path"
            mock_git_service._sanitize_repo_dir_name.return_value = "owner_repo"

            # Mock other dependencies
            with patch('analytics.management.commands.recalculate_kloc.GitHubTokenService.get_token_for_repository_access'):
                with patch('analytics.management.commands.recalculate_kloc.assert_safe_repo_path'):
                    with patch('analytics.management.commands.recalculate_kloc.KLOCService'):
                        with patch('analytics.management.commands.recalculate_kloc.RepositoryKLOCHistory'):
                            with patch('tempfile.gettempdir', return_value=self.temp_dir):
                                with patch('os.path.exists', return_value=True):
                                    with patch('shutil.rmtree') as mock_rmtree:
                                        # Execute the method
                                        result = self.command.recalculate_kloc_for_repository(mock_repo)
                                        
                                        # Verify the cleanup path is constructed safely
                                        expected_path = os.path.join(self.temp_dir, "gitpulse_owner_repo")
                                        mock_rmtree.assert_called_once_with(expected_path)
                                        
                                        # Verify the path is safe (within temp directory)
                                        self.assertTrue(expected_path.startswith(self.temp_dir))
                                        self.assertNotIn("..", expected_path)
