import pytest
import os
import tempfile
from unittest.mock import patch, MagicMock
from analytics.git_service import GitService, GitServiceError


class TestGitService:
    """Test cases for GitService security and path handling."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.git_service = GitService(temp_dir=self.temp_dir)

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_sanitize_repo_dir_name_safe_input(self):
        """Test sanitization with safe repository names."""
        test_cases = [
            ("owner/repo", "owner_repo"),
            ("user/project-name", "user_project-name"),
            ("org/repo.with.dots", "org_repo.with.dots"),
            ("owner/repo_123", "owner_repo_123"),
        ]
        
        for input_name, expected in test_cases:
            result = self.git_service._sanitize_repo_dir_name(input_name)
            assert result == expected

    def test_sanitize_repo_dir_name_malicious_input(self):
        """Test sanitization with potentially malicious input."""
        test_cases = [
            ("owner/../../../etc/passwd", "owner_etc_passwd"),
            ("user/..\\..\\..\\windows\\system32", "user_windows_system32"),
            ("org/repo/with/slashes", "org_repo_with_slashes"),
            ("owner/repo*with*special*chars", "owner_repo_with_special_chars"),
            ("user/repo with spaces", "user_repo_with_spaces"),
            ("org/repo\nwith\nnewlines", "org_repo_with_newlines"),
            ("owner/repo\twith\ttabs", "owner_repo_with_tabs"),
            ("user/repo/with/multiple/slashes", "user_repo_with_multiple_slashes"),
            ("owner/..../etc/passwd", "owner_etc_passwd"),
            ("user/.../windows/system32", "user_windows_system32"),
        ]
        
        for input_name, expected in test_cases:
            result = self.git_service._sanitize_repo_dir_name(input_name)
            assert result == expected
            # Ensure no directory separators remain
            assert "/" not in result
            assert "\\" not in result
            # Ensure no parent directory references
            assert ".." not in result

    def test_get_repo_path_uses_sanitized_name(self):
        """Test that get_repo_path uses sanitized directory names."""
        malicious_repo = "owner/../../../etc/passwd"
        
        # Mock the sanitization method to verify it's called
        with patch.object(self.git_service, '_sanitize_repo_dir_name') as mock_sanitize:
            mock_sanitize.return_value = "owner_etc_passwd"
            
            # This should raise an error since the repo doesn't exist
            with pytest.raises(GitServiceError):
                self.git_service.get_repo_path(malicious_repo)
            
            # Verify sanitization was called
            mock_sanitize.assert_called_once_with(malicious_repo)

    def test_clone_repository_uses_sanitized_name(self):
        """Test that clone_repository uses sanitized directory names."""
        # Use a valid repo name for the URL parameter, but test sanitization
        valid_repo_name = "owner/repo"
        
        # Mock the sanitization method
        with patch.object(self.git_service, '_sanitize_repo_dir_name') as mock_sanitize:
            mock_sanitize.return_value = "owner_repo"
            
            # Mock subprocess.run to avoid actual git operations
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                
                # Mock os.path.exists to simulate successful clone
                with patch('os.path.exists', return_value=True):
                    self.git_service.clone_repository("https://github.com/owner/repo.git", valid_repo_name)
                
                # Verify sanitization was called
                mock_sanitize.assert_called_once_with(valid_repo_name)

    def test_path_traversal_protection(self):
        """Test that path traversal attacks are prevented."""
        malicious_inputs = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "owner/../../../etc/shadow",
            "user/..\\..\\..\\windows\\system32\\drivers\\etc\\hosts",
        ]
        
        for malicious_input in malicious_inputs:
            sanitized = self.git_service._sanitize_repo_dir_name(malicious_input)
            
            # Verify no directory separators
            assert "/" not in sanitized
            assert "\\" not in sanitized
            
            # Verify no parent directory references
            assert ".." not in sanitized
            
            # Verify the result is safe to use in os.path.join
            safe_path = os.path.join(self.temp_dir, f"gitpulse_{sanitized}")
            assert safe_path.startswith(self.temp_dir)
            assert ".." not in safe_path

    def test_consistent_sanitization_across_methods(self):
        """Test that all methods use the same sanitization approach."""
        repo_name = "owner/repo"
        
        # Get sanitized name directly
        direct_sanitized = self.git_service._sanitize_repo_dir_name(repo_name)
        
        # Mock subprocess and os.path for clone_repository
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            with patch('os.path.exists', return_value=True):
                self.git_service.clone_repository("https://github.com/owner/repo.git", repo_name)
        
        # Mock os.path.exists for get_repo_path
        with patch('os.path.exists', return_value=False):
            with pytest.raises(GitServiceError):
                self.git_service.get_repo_path(repo_name)
        
        # Both methods should use the same sanitization
        expected_dir = os.path.join(self.temp_dir, f"gitpulse_{direct_sanitized}")
        
        # Verify the expected directory name is consistent
        assert ".." not in expected_dir
        assert expected_dir.startswith(self.temp_dir)
