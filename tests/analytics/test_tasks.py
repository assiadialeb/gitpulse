import pytest
import tempfile
import os
from unittest.mock import patch, MagicMock
from django.test import TestCase
from analytics.git_service import GitService


class TestTasksSecurity(TestCase):
    """Test cases for tasks.py security and path handling."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_sanitization_works_correctly(self):
        """Test that our sanitization method works correctly for path traversal protection."""
        git_service = GitService()
        
        # Test with malicious input
        malicious_input = "owner/../../../etc/passwd"
        safe_name = git_service._sanitize_repo_dir_name(malicious_input)
        
        # Verify the sanitized name is safe
        self.assertNotIn("..", safe_name)
        self.assertNotIn("/", safe_name)
        self.assertNotIn("\\", safe_name)
        
        # Verify the path would be safe
        temp_dir = tempfile.gettempdir()
        safe_path = os.path.join(temp_dir, f"gitpulse_{safe_name}")
        
        # The path should be within the temp directory
        self.assertTrue(safe_path.startswith(temp_dir))
        
        # The path should not contain any traversal sequences
        self.assertNotIn("..", safe_path)
        
        print(f"Input: {malicious_input}")
        print(f"Sanitized: {safe_name}")
        print(f"Safe path: {safe_path}")

    def test_multiple_malicious_inputs(self):
        """Test sanitization with multiple malicious inputs."""
        git_service = GitService()
        
        malicious_inputs = [
            "owner/../../../etc/passwd",
            "user/..\\..\\..\\windows\\system32",
            "org/repo/with/slashes",
            "owner/repo*with*special*chars",
            "user/repo with spaces",
            "org/repo\nwith\nnewlines",
            "owner/repo\twith\ttabs",
        ]
        
        for malicious_input in malicious_inputs:
            safe_name = git_service._sanitize_repo_dir_name(malicious_input)
            
            # Verify the sanitized name is safe
            self.assertNotIn("..", safe_name)
            self.assertNotIn("/", safe_name)
            self.assertNotIn("\\", safe_name)
            
            # Verify the path would be safe
            temp_dir = tempfile.gettempdir()
            safe_path = os.path.join(temp_dir, f"gitpulse_{safe_name}")
            
            # The path should be within the temp directory
            self.assertTrue(safe_path.startswith(temp_dir))
            
            # The path should not contain any traversal sequences
            self.assertNotIn("..", safe_path)
            
            print(f"Input: {malicious_input} -> Sanitized: {safe_name}")

    def test_safe_inputs_remain_safe(self):
        """Test that safe inputs remain safe after sanitization."""
        git_service = GitService()
        
        safe_inputs = [
            "owner/repo",
            "user/project-name",
            "org/valid_repo",
            "owner/valid-repo",
        ]
        
        for safe_input in safe_inputs:
            sanitized = git_service._sanitize_repo_dir_name(safe_input)
            
            # Should not contain dangerous characters
            self.assertNotIn("..", sanitized)
            self.assertNotIn("/", sanitized)
            self.assertNotIn("\\", sanitized)
            
            print(f"Safe input: {safe_input} -> Sanitized: {sanitized}")
