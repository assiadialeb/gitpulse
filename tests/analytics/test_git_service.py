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
            ("user/test-repo", "user_test-repo"),
            ("org/repo_name", "org_repo_name"),
            ("owner/repo.with.dots", "owner_repo.with.dots"),
        ]
        
        for input_name, expected in test_cases:
            result = self.git_service._sanitize_repo_dir_name(input_name)
            assert result == expected
            print(f"Safe input: {input_name} -> Sanitized: {result}")

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
        ]
        
        for input_name, expected in test_cases:
            result = self.git_service._sanitize_repo_dir_name(input_name)
            assert result == expected
            print(f"Malicious input: {input_name} -> Sanitized: {result}")

    def test_get_repo_path_uses_sanitized_name(self):
        """Test that get_repo_path uses sanitized directory names."""
        malicious_repo = "owner/../../../etc/passwd"
        
        # Mock the sanitization method
        with patch.object(self.git_service, '_sanitize_repo_dir_name') as mock_sanitize:
            mock_sanitize.return_value = "owner_etc_passwd"
            
            # Mock os.path.exists to simulate repository not found
            with patch('os.path.exists', return_value=False):
                with pytest.raises(GitServiceError):
                    self.git_service.get_repo_path(malicious_repo)
            
            # Verify sanitization was called
            mock_sanitize.assert_called_once_with(malicious_repo)

    def test_clone_repository_uses_sanitized_name(self):
        """Test that clone_repository uses sanitized directory names."""
        valid_repo = "owner/repo"
        
        # Mock the sanitization method
        with patch.object(self.git_service, '_sanitize_repo_dir_name') as mock_sanitize:
            mock_sanitize.return_value = "owner_repo"
            
            # Mock subprocess.run to avoid actual git operations
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                
                # Mock os.path.exists to simulate successful clone
                with patch('os.path.exists', return_value=True):
                    self.git_service.clone_repository("https://github.com/owner/repo.git", valid_repo)
                
                # Verify sanitization was called
                mock_sanitize.assert_called_once_with(valid_repo)

    def test_path_traversal_protection(self):
        """Test protection against path traversal attacks."""
        malicious_inputs = [
            "owner/../../../etc/passwd",
            "user/..\\..\\..\\windows\\system32",
            "org/.../...//etc/passwd",
            "owner/..../....//etc/passwd",
        ]
        
        for malicious_input in malicious_inputs:
            sanitized = self.git_service._sanitize_repo_dir_name(malicious_input)
            
            # Should not contain path traversal sequences
            assert ".." not in sanitized
            assert "\\" not in sanitized
            
            # Should be safe to use in path construction
            repo_dir = os.path.join(self.temp_dir, f"gitpulse_{sanitized}")
            assert repo_dir.startswith(self.temp_dir)
            assert ".." not in repo_dir
            
            print(f"Malicious: {malicious_input} -> Safe: {sanitized}")

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
        
        # All methods should produce the same sanitized result
        assert direct_sanitized == "owner_repo"

    def test_assert_safe_git_args_valid_path(self):
        """Test _assert_safe_git_args with valid repository path."""
        safe_repo_dir = os.path.join(self.temp_dir, "gitpulse_owner_repo")
        
        # Should not raise any exception
        self.git_service._assert_safe_git_args(
            "https://github.com/owner/repo.git",
            safe_repo_dir
        )

    def test_assert_safe_git_args_invalid_pattern(self):
        """Test _assert_safe_git_args with invalid directory pattern."""
        invalid_repo_dir = os.path.join(self.temp_dir, "invalid_pattern")
        
        with pytest.raises(GitServiceError, match="does not follow expected pattern"):
            self.git_service._assert_safe_git_args(
                "https://github.com/owner/repo.git",
                invalid_repo_dir
            )

    def test_assert_safe_git_args_unsafe_characters(self):
        """Test _assert_safe_git_args with unsafe characters in directory name."""
        unsafe_repo_dir = os.path.join(self.temp_dir, "gitpulse_owner*repo")
        
        with pytest.raises(GitServiceError, match="contains unsafe characters"):
            self.git_service._assert_safe_git_args(
                "https://github.com/owner/repo.git",
                unsafe_repo_dir
            )

    def test_assert_safe_git_args_path_traversal(self):
        """Test _assert_safe_git_args with path traversal attempts."""
        traversal_repo_dir = os.path.join(self.temp_dir, "gitpulse_owner..repo")
        
        with pytest.raises(GitServiceError, match="contains path traversal characters"):
            self.git_service._assert_safe_git_args(
                "https://github.com/owner/repo.git",
                traversal_repo_dir
            )

    def test_assert_safe_git_args_whitespace(self):
        """Test _assert_safe_git_args with whitespace in arguments."""
        with pytest.raises(GitServiceError, match="Unsafe whitespace"):
            self.git_service._assert_safe_git_args(
                "https://github.com/owner/repo.git",
                os.path.join(self.temp_dir, "gitpulse_owner repo")
            )

    def test_assert_safe_git_args_null_byte(self):
        """Test _assert_safe_git_args with null byte in arguments."""
        with pytest.raises(GitServiceError, match="null byte"):
            self.git_service._assert_safe_git_args(
                "https://github.com/owner/repo.git",
                os.path.join(self.temp_dir, "gitpulse_owner\x00repo")
            )

    def test_assert_safe_git_args_directory_escape(self):
        """Test _assert_safe_git_args with directory escape attempt."""
        escape_repo_dir = os.path.join(self.temp_dir, "..", "gitpulse_owner_repo")
        
        with pytest.raises(GitServiceError, match="escapes temp directory"):
            self.git_service._assert_safe_git_args(
                "https://github.com/owner/repo.git",
                escape_repo_dir
            )

    def test_assert_safe_git_args_invalid_url(self):
        """Test _assert_safe_git_args with invalid clone URL."""
        safe_repo_dir = os.path.join(self.temp_dir, "gitpulse_owner_repo")
        
        with pytest.raises(GitServiceError, match="Unsupported clone URL scheme"):
            self.git_service._assert_safe_git_args(
                "ftp://github.com/owner/repo.git",
                safe_repo_dir
            )

    def test_assert_safe_git_args_non_github_host(self):
        """Test _assert_safe_git_args with non-GitHub host."""
        safe_repo_dir = os.path.join(self.temp_dir, "gitpulse_owner_repo")
        
        with pytest.raises(GitServiceError, match="Invalid clone URL host"):
            self.git_service._assert_safe_git_args(
                "https://gitlab.com/owner/repo.git",
                safe_repo_dir
            )
