"""
Tests for the SBOM service
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock, mock_open
from datetime import datetime, timezone
from django.test import TestCase
import subprocess

from analytics.sbom_service import SBOMService
from analytics.models import SBOM, SBOMComponent
from tests.conftest import BaseTestCase


class TestSBOMService(BaseTestCase):
    """Test cases for SBOMService"""
    
    def setUp(self):
        super().setUp()
        self.repository_full_name = 'test-org/test-repo'
        self.user_id = 1
        self.service = SBOMService(self.repository_full_name, self.user_id)
    
    @patch('analytics.sbom_service.requests.get')
    @patch('analytics.sbom_service.GitHubTokenService.get_token_for_repository_access')
    def test_fetch_github_sbom_success(self, mock_get_token, mock_get):
        """Test successful SBOM fetching from GitHub API"""
        # Mock token service
        mock_get_token.return_value = 'ghp_test_token_12345'
        
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'sbom': {
                'spdxVersion': 'SPDX-2.3',
                'dataLicense': 'CC0-1.0',
                'SPDXID': 'SPDXRef-DOCUMENT',
                'documentNamespace': 'https://github.com/test-org/test-repo',
                'creationInfo': {
                    'creators': ['Tool: GitHub Dependency Graph'],
                    'created': '2023-01-15T10:30:00Z'
                },
                'packages': [
                    {
                        'SPDXID': 'SPDXRef-Package-1',
                        'name': 'requests',
                        'versionInfo': '2.28.1',
                        'packageFileName': 'requests-2.28.1-py3-none-any.whl',
                        'packageVerificationCode': {
                            'packageVerificationCodeValue': 'abc123def456'
                        },
                        'externalRefs': [
                            {
                                'referenceCategory': 'PACKAGE_MANAGER',
                                'referenceType': 'purl',
                                'referenceLocator': 'pkg:pypi/requests@2.28.1'
                            }
                        ]
                    }
                ]
            }
        }
        mock_get.return_value = mock_response
        
        # Test the method
        result = self.service.fetch_github_sbom(self.user_id)
        
        # Assertions
        assert result['spdxVersion'] == 'SPDX-2.3'
        assert result['documentNamespace'] == 'https://github.com/test-org/test-repo'
        assert len(result['packages']) == 1
        assert result['packages'][0]['name'] == 'requests'
        assert result['packages'][0]['versionInfo'] == '2.28.1'
        
        # Verify API call
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert 'api.github.com' in call_args[0][0]
        assert 'dependency-graph/sbom' in call_args[0][0]
    
    @patch('analytics.sbom_service.requests.get')
    @patch('analytics.sbom_service.GitHubTokenService.get_token_for_repository_access')
    def test_fetch_github_sbom_generation_in_progress(self, mock_get_token, mock_get):
        """Test handling of SBOM generation in progress (202 status)"""
        # Mock token service
        mock_get_token.return_value = 'ghp_test_token_12345'
        
        # Mock 202 response (generation in progress)
        mock_response = Mock()
        mock_response.status_code = 202
        mock_get.return_value = mock_response
        
        # Test the method
        with pytest.raises(RuntimeError, match="GitHub SBOM generation in progress"):
            self.service.fetch_github_sbom(self.user_id)
    
    @patch('analytics.sbom_service.requests.get')
    @patch('analytics.sbom_service.GitHubTokenService.get_token_for_repository_access')
    def test_fetch_github_sbom_api_error(self, mock_get_token, mock_get):
        """Test handling of GitHub API errors"""
        # Mock token service
        mock_get_token.return_value = 'ghp_test_token_12345'
        
        # Mock API error response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = 'SBOM not found'
        mock_get.return_value = mock_response
        
        # Test the method
        with pytest.raises(RuntimeError, match="GitHub SBOM API error 404"):
            self.service.fetch_github_sbom(self.user_id)
    
    @patch('analytics.sbom_service.GitHubTokenService.get_token_for_repository_access')
    def test_fetch_github_sbom_no_token(self, mock_get_token):
        """Test handling when no GitHub token is available"""
        # Mock no token available
        mock_get_token.return_value = None
        
        # Test the method
        with pytest.raises(RuntimeError, match="GitHub token not found"):
            self.service.fetch_github_sbom(self.user_id)
    
    @patch('analytics.sbom_service.requests.get')
    @patch('analytics.sbom_service.GitHubTokenService.get_token_for_repository_access')
    def test_fetch_github_sbom_invalid_repository_name(self, mock_get_token, mock_get):
        """Test handling of invalid repository name"""
        # Create service with invalid repository name
        invalid_service = SBOMService('invalid-repo-name', self.user_id)
        
        # Test the method
        with pytest.raises(ValueError, match="Invalid repository_full_name"):
            invalid_service.fetch_github_sbom(self.user_id)
    
    def test_process_spdx_sbom_success(self):
        """Test successful SPDX SBOM processing"""
        # Sample SPDX data
        spdx_data = {
            'spdxVersion': 'SPDX-2.3',
            'dataLicense': 'CC0-1.0',
            'SPDXID': 'SPDXRef-DOCUMENT',
            'documentNamespace': 'https://github.com/test-org/test-repo',
            'creationInfo': {
                'creators': ['Tool: GitHub Dependency Graph'],
                'created': '2023-01-15T10:30:00Z'
            },
            'packages': [
                {
                    'SPDXID': 'SPDXRef-Package-1',
                    'name': 'requests',
                    'versionInfo': '2.28.1',
                    'packageFileName': 'requests-2.28.1-py3-none-any.whl',
                    'packageVerificationCode': {
                        'packageVerificationCodeValue': 'abc123def456'
                    },
                    'externalRefs': [
                        {
                            'referenceCategory': 'PACKAGE_MANAGER',
                            'referenceType': 'purl',
                            'referenceLocator': 'pkg:pypi/requests@2.28.1'
                        }
                    ]
                },
                {
                    'SPDXID': 'SPDXRef-Package-2',
                    'name': 'flask',
                    'versionInfo': '2.2.3',
                    'packageFileName': 'flask-2.2.3-py3-none-any.whl',
                    'packageVerificationCode': {
                        'packageVerificationCodeValue': 'def456ghi789'
                    },
                    'externalRefs': [
                        {
                            'referenceCategory': 'PACKAGE_MANAGER',
                            'referenceType': 'purl',
                            'referenceLocator': 'pkg:pypi/flask@2.2.3'
                        }
                    ]
                }
            ]
        }
        
        # Test the method
        with patch('analytics.sbom_service.SBOM') as mock_sbom_class:
            mock_sbom_instance = Mock()
            mock_sbom_class.return_value = mock_sbom_instance
            
            with patch('analytics.sbom_service.SBOMComponent') as mock_component_class:
                mock_component_instance = Mock()
                mock_component_class.return_value = mock_component_instance
                
                result = self.service.process_spdx_sbom(spdx_data)
                
                # Verify SBOM creation
                mock_sbom_class.assert_called_once()
                call_args = mock_sbom_class.call_args
                assert call_args[1]['repository_full_name'] == self.repository_full_name
                assert call_args[1]['bom_format'] == 'SPDX'
                assert call_args[1]['spec_version'] == 'SPDX-2.3'
                
                # Verify component creation (should be called twice for two packages)
                assert mock_component_class.call_count == 2
    
    def test_process_spdx_sbom_missing_creation_info(self):
        """Test SPDX SBOM processing with missing creation info"""
        # Sample SPDX data without creation info
        spdx_data = {
            'spdxVersion': 'SPDX-2.3',
            'dataLicense': 'CC0-1.0',
            'SPDXID': 'SPDXRef-DOCUMENT',
            'documentNamespace': 'https://github.com/test-org/test-repo',
            'packages': []
        }
        
        # Test the method
        with patch('analytics.sbom_service.SBOM') as mock_sbom_class:
            mock_sbom_instance = Mock()
            mock_sbom_class.return_value = mock_sbom_instance
            
            with patch('analytics.sbom_service.SBOMComponent'):
                result = self.service.process_spdx_sbom(spdx_data)
                
                # Verify SBOM creation with default values
                mock_sbom_class.assert_called_once()
                call_args = mock_sbom_class.call_args
                assert call_args[1]['tool_name'] == 'GitHub Dependency Graph'
    
    def test_process_spdx_sbom_invalid_date_format(self):
        """Test SPDX SBOM processing with invalid date format"""
        # Sample SPDX data with invalid date
        spdx_data = {
            'spdxVersion': 'SPDX-2.3',
            'dataLicense': 'CC0-1.0',
            'SPDXID': 'SPDXRef-DOCUMENT',
            'documentNamespace': 'https://github.com/test-org/test-repo',
            'creationInfo': {
                'creators': ['Tool: GitHub Dependency Graph'],
                'created': 'invalid-date-format'
            },
            'packages': []
        }
        
        # Test the method
        with patch('analytics.sbom_service.SBOM') as mock_sbom_class:
            mock_sbom_instance = Mock()
            mock_sbom_class.return_value = mock_sbom_instance
            
            with patch('analytics.sbom_service.SBOMComponent'):
                result = self.service.process_spdx_sbom(spdx_data)
                
                # Should handle invalid date gracefully
                mock_sbom_class.assert_called_once()
    
    @patch('analytics.sbom_service.subprocess.run')
    @patch('analytics.sbom_service.tempfile.mkdtemp')
    @patch('analytics.sbom_service.shutil.rmtree')
    def test_generate_sbom_with_cyclonedx_success(self, mock_rmtree, mock_mkdtemp, mock_run):
        """Test successful SBOM generation with CycloneDX"""
        # Mock temporary directory
        mock_mkdtemp.return_value = '/tmp/test-sbom'
        
        # Mock subprocess run
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.stdout = b'{"bomFormat": "CycloneDX", "specVersion": "1.4"}'
        mock_run.return_value = mock_process
        
        # Test the method
        with patch('builtins.open', mock_open(read_data='{"test": "data"}')):
            result = self.service.generate_sbom_with_cyclonedx()
            
            # Verify subprocess call
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            assert 'cyclonedx-py' in ' '.join(call_args[0][0])
            
            # Verify cleanup
            mock_rmtree.assert_called_once_with('/tmp/test-sbom')
    
    @patch('analytics.sbom_service.subprocess.run')
    @patch('analytics.sbom_service.tempfile.mkdtemp')
    @patch('analytics.sbom_service.shutil.rmtree')
    def test_generate_sbom_with_cyclonedx_subprocess_error(self, mock_rmtree, mock_mkdtemp, mock_run):
        """Test SBOM generation with subprocess error"""
        # Mock temporary directory
        mock_mkdtemp.return_value = '/tmp/test-sbom'
        
        # Mock subprocess error
        mock_run.side_effect = subprocess.CalledProcessError(1, 'cyclonedx-py')
        
        # Test the method
        with pytest.raises(subprocess.CalledProcessError):
            self.service.generate_sbom_with_cyclonedx()
        
        # Verify cleanup still happens
        mock_rmtree.assert_called_once_with('/tmp/test-sbom')
    
    @patch('analytics.sbom_service.subprocess.run')
    @patch('analytics.sbom_service.tempfile.mkdtemp')
    @patch('analytics.sbom_service.shutil.rmtree')
    def test_generate_sbom_with_cyclonedx_json_error(self, mock_rmtree, mock_mkdtemp, mock_run):
        """Test SBOM generation with invalid JSON output"""
        # Mock temporary directory
        mock_mkdtemp.return_value = '/tmp/test-sbom'
        
        # Mock subprocess run with invalid JSON
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.stdout = b'invalid json'
        mock_run.return_value = mock_process
        
        # Test the method
        with patch('builtins.open', mock_open(read_data='{"test": "data"}')):
            with pytest.raises(json.JSONDecodeError):
                self.service.generate_sbom_with_cyclonedx()
            
            # Verify cleanup still happens
            mock_rmtree.assert_called_once_with('/tmp/test-sbom')
    
    def test_get_or_create_sbom_success(self):
        """Test successful SBOM retrieval or creation"""
        # Mock existing SBOM
        mock_sbom = Mock()
        mock_sbom.generated_at = datetime(2023, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        
        with patch('analytics.sbom_service.SBOM.objects.filter') as mock_filter:
            mock_filter.return_value.first.return_value = mock_sbom
            
            result = self.service.get_or_create_sbom()
            
            # Should return existing SBOM
            assert result == mock_sbom
    
    def test_get_or_create_sbom_not_found(self):
        """Test SBOM creation when not found"""
        # Mock no existing SBOM
        with patch('analytics.sbom_service.SBOM.objects.filter') as mock_filter:
            mock_filter.return_value.first.return_value = None
            
            with patch.object(self.service, 'fetch_github_sbom') as mock_fetch:
                mock_fetch.return_value = {'test': 'data'}
                
                with patch.object(self.service, 'process_spdx_sbom') as mock_process:
                    mock_sbom = Mock()
                    mock_process.return_value = mock_sbom
                    
                    result = self.service.get_or_create_sbom()
                    
                    # Should create new SBOM
                    assert result == mock_sbom
                    mock_fetch.assert_called_once_with(self.user_id)
                    mock_process.assert_called_once()
    
    def test_get_or_create_sbom_github_error_fallback(self):
        """Test SBOM creation with GitHub error and CycloneDX fallback"""
        # Mock no existing SBOM
        with patch('analytics.sbom_service.SBOM.objects.filter') as mock_filter:
            mock_filter.return_value.first.return_value = None
            
            with patch.object(self.service, 'fetch_github_sbom') as mock_fetch:
                mock_fetch.side_effect = RuntimeError("GitHub error")
                
                with patch.object(self.service, 'generate_sbom_with_cyclonedx') as mock_cyclonedx:
                    mock_cyclonedx.return_value = {'bomFormat': 'CycloneDX'}
                    
                    with patch.object(self.service, 'process_cyclonedx_sbom') as mock_process:
                        mock_sbom = Mock()
                        mock_process.return_value = mock_sbom
                        
                        result = self.service.get_or_create_sbom()
                        
                        # Should use CycloneDX fallback
                        assert result == mock_sbom
                        mock_cyclonedx.assert_called_once()
                        mock_process.assert_called_once()
    
    def test_get_or_create_sbom_both_methods_fail(self):
        """Test SBOM creation when both GitHub and CycloneDX fail"""
        # Mock no existing SBOM
        with patch('analytics.sbom_service.SBOM.objects.filter') as mock_filter:
            mock_filter.return_value.first.return_value = None
            
            with patch.object(self.service, 'fetch_github_sbom') as mock_fetch:
                mock_fetch.side_effect = RuntimeError("GitHub error")
                
                with patch.object(self.service, 'generate_sbom_with_cyclonedx') as mock_cyclonedx:
                    mock_cyclonedx.side_effect = Exception("CycloneDX error")
                    
                    # Should raise the last exception
                    with pytest.raises(Exception, match="CycloneDX error"):
                        self.service.get_or_create_sbom()
    
    def test_process_cyclonedx_sbom_success(self):
        """Test successful CycloneDX SBOM processing"""
        # Sample CycloneDX data
        cyclonedx_data = {
            'bomFormat': 'CycloneDX',
            'specVersion': '1.4',
            'metadata': {
                'timestamp': '2023-01-15T10:30:00Z',
                'tools': [
                    {
                        'vendor': 'CycloneDX',
                        'name': 'cyclonedx-py',
                        'version': '1.0.0'
                    }
                ]
            },
            'components': [
                {
                    'type': 'library',
                    'name': 'requests',
                    'version': '2.28.1',
                    'purl': 'pkg:pypi/requests@2.28.1',
                    'bom-ref': 'requests-2.28.1'
                }
            ]
        }
        
        # Test the method
        with patch('analytics.sbom_service.SBOM') as mock_sbom_class:
            mock_sbom_instance = Mock()
            mock_sbom_class.return_value = mock_sbom_instance
            
            with patch('analytics.sbom_service.SBOMComponent') as mock_component_class:
                mock_component_instance = Mock()
                mock_component_class.return_value = mock_component_instance
                
                result = self.service.process_cyclonedx_sbom(cyclonedx_data)
                
                # Verify SBOM creation
                mock_sbom_class.assert_called_once()
                call_args = mock_sbom_class.call_args
                assert call_args[1]['bom_format'] == 'CycloneDX'
                assert call_args[1]['spec_version'] == '1.4'
                
                # Verify component creation
                mock_component_class.assert_called_once()
