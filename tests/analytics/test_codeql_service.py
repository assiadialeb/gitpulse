"""
Tests for the CodeQL service
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from django.test import TestCase

from analytics.codeql_service import CodeQLService
from analytics.models import CodeQLVulnerability
from tests.conftest import BaseTestCase


class TestCodeQLService(BaseTestCase):
    """Test cases for CodeQLService"""
    
    def setUp(self):
        super().setUp()
        self.github_token = 'ghp_test_token_12345'
        self.service = CodeQLService(self.github_token)
        self.repo_full_name = 'test-org/test-repo'
    
    def test_init_with_token(self):
        """Test service initialization with token"""
        service = CodeQLService(self.github_token)
        assert service.github_token == self.github_token
        assert 'Authorization' in service.session.headers
        assert f'token {self.github_token}' in service.session.headers['Authorization']
    
    def test_init_without_token(self):
        """Test service initialization without token"""
        service = CodeQLService()
        assert service.github_token is None
        assert 'Authorization' not in service.session.headers
    
    @patch('analytics.codeql_service.requests.Session.get')
    def test_make_request_success(self, mock_get):
        """Test successful API request"""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'test': 'data'}
        mock_get.return_value = mock_response
        
        result, success = self.service._make_request('https://api.github.com/test')
        
        assert success is True
        assert result == {'test': 'data'}
        mock_get.assert_called_once()
    
    @patch('analytics.codeql_service.requests.Session.get')
    def test_make_request_404_not_enabled(self, mock_get):
        """Test handling of 404 (CodeQL not enabled)"""
        # Mock 404 response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        result, success = self.service._make_request('https://api.github.com/test')
        
        assert success is False
        assert result is None
    
    @patch('analytics.codeql_service.requests.Session.get')
    def test_make_request_403_not_enabled(self, mock_get):
        """Test handling of 403 (Advanced Security not enabled)"""
        # Mock 403 response with specific error message
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.text = 'code scanning not enabled'
        mock_get.return_value = mock_response
        
        result, success = self.service._make_request('https://api.github.com/test')
        
        assert success is False
        assert result is None
    
    @patch('analytics.codeql_service.requests.Session.get')
    def test_make_request_403_access_denied(self, mock_get):
        """Test handling of 403 (access denied)"""
        # Mock 403 response with different error message
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.text = 'access denied'
        mock_get.return_value = mock_response
        
        result, success = self.service._make_request('https://api.github.com/test')
        
        assert success is False
        assert result is None
    
    @patch('analytics.codeql_service.requests.Session.get')
    def test_make_request_401_unauthorized(self, mock_get):
        """Test handling of 401 (unauthorized)"""
        # Mock 401 response
        mock_response = Mock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response
        
        result, success = self.service._make_request('https://api.github.com/test')
        
        assert success is False
        assert result is None
    
    @patch('analytics.codeql_service.requests.Session.get')
    def test_make_request_422_not_supported(self, mock_get):
        """Test handling of 422 (repository may not support code scanning)"""
        # Mock 422 response
        mock_response = Mock()
        mock_response.status_code = 422
        mock_get.return_value = mock_response
        
        result, success = self.service._make_request('https://api.github.com/test')
        
        assert success is False
        assert result is None
    
    @patch('analytics.codeql_service.requests.Session.get')
    def test_make_request_network_error(self, mock_get):
        """Test handling of network errors"""
        # Mock network error
        mock_get.side_effect = Exception("Network error")
        
        result, success = self.service._make_request('https://api.github.com/test')
        
        assert success is False
        assert result is None or result == []
    
    @patch.object(CodeQLService, '_make_request')
    def test_fetch_codeql_alerts_success(self, mock_make_request):
        """Test successful CodeQL alerts fetching"""
        # Mock successful response
        mock_alerts = [
            {
                'number': 1,
                'rule': {
                    'id': 'test-rule',
                    'name': 'Test Vulnerability',
                    'severity': 'high',
                    'description': 'Test description'
                },
                'most_recent_instance': {
                    'location': {
                        'path': 'src/test.py',
                        'start_line': 10,
                        'end_line': 15
                    }
                },
                'state': 'open',
                'created_at': '2023-01-15T10:30:00Z',
                'updated_at': '2023-01-16T15:45:00Z',
                'dismissed_at': None,
                'dismissed_reason': None,
                'dismissed_by': None,
                'url': 'https://github.com/test-org/test-repo/security/code-scanning/1'
            }
        ]
        mock_make_request.return_value = (mock_alerts, True)
        
        alerts, success = self.service.fetch_codeql_alerts(self.repo_full_name)
        
        assert success is True
        assert len(alerts) == 1
        assert alerts[0]['number'] == 1
        assert alerts[0]['rule']['id'] == 'test-rule'
        assert alerts[0]['state'] == 'open'
        
        # Verify API call
        mock_make_request.assert_called_once()
        call_args = mock_make_request.call_args
        assert 'code-scanning/alerts' in call_args[0][0]
        assert self.repo_full_name in call_args[0][0]
    
    @patch.object(CodeQLService, '_make_request')
    def test_fetch_codeql_alerts_failure(self, mock_make_request):
        """Test CodeQL alerts fetching failure"""
        # Mock failed response
        mock_make_request.return_value = (None, False)
        
        alerts, success = self.service.fetch_codeql_alerts(self.repo_full_name)
        
        assert success is False
        assert alerts == []
    
    @patch.object(CodeQLService, '_make_request')
    def test_fetch_codeql_alerts_with_pagination(self, mock_make_request):
        """Test CodeQL alerts fetching with pagination"""
        # Mock first page response
        mock_alerts_page1 = [
            {
                'number': 1,
                'rule': {'id': 'test-rule-1', 'name': 'Test 1', 'severity': 'high'},
                'most_recent_instance': {'location': {'path': 'src/test1.py'}},
                'state': 'open',
                'created_at': '2023-01-15T10:30:00Z',
                'updated_at': '2023-01-16T15:45:00Z',
                'dismissed_at': None,
                'dismissed_reason': None,
                'dismissed_by': None,
                'url': 'https://github.com/test-org/test-repo/security/code-scanning/1'
            }
        ]
        
        # Mock second page response (empty)
        mock_alerts_page2 = []
        
        mock_make_request.side_effect = [
            (mock_alerts_page1, True),
            (mock_alerts_page2, True)
        ]
        
        alerts, success = self.service.fetch_codeql_alerts(self.repo_full_name, per_page=1)
        
        assert success is True
        assert len(alerts) == 1
        # Note: The service doesn't implement pagination in fetch_codeql_alerts, 
        # so we expect only one call
        assert mock_make_request.call_count == 1
    
    @patch.object(CodeQLService, '_make_request')
    def test_fetch_codeql_alerts_with_state_filter(self, mock_make_request):
        """Test CodeQL alerts fetching with state filter"""
        # Mock response
        mock_alerts = [
            {
                'number': 1,
                'rule': {'id': 'test-rule', 'name': 'Test', 'severity': 'high'},
                'most_recent_instance': {'location': {'path': 'src/test.py'}},
                'state': 'dismissed',
                'created_at': '2023-01-15T10:30:00Z',
                'updated_at': '2023-01-16T15:45:00Z',
                'dismissed_at': '2023-01-17T10:00:00Z',
                'dismissed_reason': 'false positive',
                'dismissed_by': 'johndoe',
                'url': 'https://github.com/test-org/test-repo/security/code-scanning/1'
            }
        ]
        mock_make_request.return_value = (mock_alerts, True)
        
        alerts, success = self.service.fetch_codeql_alerts(self.repo_full_name, state='dismissed')
        
        assert success is True
        assert len(alerts) == 1
        assert alerts[0]['state'] == 'dismissed'
        
        # Verify state parameter was passed
        call_args = mock_make_request.call_args
        assert call_args[0][1]['state'] == 'dismissed'
    
    @patch.object(CodeQLService, '_make_request')
    def test_fetch_all_codeql_alerts_success(self, mock_make_request):
        """Test successful fetching of all CodeQL alerts"""
        # Mock successful responses for different states
        mock_alerts_open = [
            {
                'number': 1,
                'rule': {'id': 'test-rule-1', 'name': 'Test 1', 'severity': 'high'},
                'most_recent_instance': {'location': {'path': 'src/test1.py'}},
                'state': 'open',
                'created_at': '2023-01-15T10:30:00Z',
                'updated_at': '2023-01-16T15:45:00Z',
                'dismissed_at': None,
                'dismissed_reason': None,
                'dismissed_by': None,
                'url': 'https://github.com/test-org/test-repo/security/code-scanning/1'
            }
        ]
        
        mock_alerts_dismissed = [
            {
                'number': 2,
                'rule': {'id': 'test-rule-2', 'name': 'Test 2', 'severity': 'medium'},
                'most_recent_instance': {'location': {'path': 'src/test2.py'}},
                'state': 'dismissed',
                'created_at': '2023-01-15T10:30:00Z',
                'updated_at': '2023-01-16T15:45:00Z',
                'dismissed_at': '2023-01-17T10:00:00Z',
                'dismissed_reason': 'false positive',
                'dismissed_by': 'johndoe',
                'url': 'https://github.com/test-org/test-repo/security/code-scanning/2'
            }
        ]
        
        mock_alerts_fixed = []
        
        mock_make_request.side_effect = [
            (mock_alerts_open, True),
            (mock_alerts_dismissed, True),
            (mock_alerts_fixed, True)
        ]
        
        alerts, success = self.service.fetch_all_codeql_alerts(self.repo_full_name)
        
        assert success is True
        assert len(alerts) == 2
        assert alerts[0]['state'] == 'open'
        assert alerts[1]['state'] == 'dismissed'
        
        # Verify API calls for all states
        assert mock_make_request.call_count == 3
    
    @patch.object(CodeQLService, '_make_request')
    def test_fetch_all_codeql_alerts_failure(self, mock_make_request):
        """Test fetching all CodeQL alerts with failure"""
        # Mock failed response
        mock_make_request.return_value = (None, False)
        
        alerts, success = self.service.fetch_all_codeql_alerts(self.repo_full_name)
        
        assert success is False
        assert len(alerts) == 0
    
    @patch.object(CodeQLService, '_make_request')
    def test_fetch_alert_instances_success(self, mock_make_request):
        """Test successful alert instances fetching"""
        # Mock successful response
        mock_instances = [
            {
                'ref': 'refs/heads/main',
                'analysis_key': 'test-analysis',
                'environment': 'production',
                'category': 'test-category',
                'state': 'open',
                'commit_sha': 'abc123def456',
                'message': {
                    'text': 'Test instance message'
                },
                'location': {
                    'path': 'src/test.py',
                    'start_line': 10,
                    'end_line': 15
                },
                'classifications': ['test-classification']
            }
        ]
        mock_make_request.return_value = (mock_instances, True)
        
        instances, success = self.service.fetch_alert_instances(self.repo_full_name, 1)
        
        assert success is True
        assert len(instances) == 1
        assert instances[0]['ref'] == 'refs/heads/main'
        assert instances[0]['commit_sha'] == 'abc123def456'
        
        # Verify API call
        mock_make_request.assert_called_once()
        call_args = mock_make_request.call_args
        assert 'code-scanning/alerts/1/instances' in call_args[0][0]
    
    @patch.object(CodeQLService, '_make_request')
    def test_fetch_alert_instances_failure(self, mock_make_request):
        """Test alert instances fetching failure"""
        # Mock failed response
        mock_make_request.return_value = (None, False)
        
        instances, success = self.service.fetch_alert_instances(self.repo_full_name, 1)
        
        assert success is False
        assert instances == []
    
    def test_process_codeql_alert_success(self):
        """Test successful CodeQL alert processing"""
        # Sample alert data
        alert_data = {
            'number': 1,
            'id': 'test-alert-123',
            'rule': {
                'id': 'test-rule',
                'name': 'Test Vulnerability',
                'description': 'Test description',
                'severity': 'error',
                'security_severity_level': 'high',
                'precision': 'high',
                'tags': ['security-severity: high', 'CWE-79']
            },
            'most_recent_instance': {
                'location': {
                    'path': 'src/test.py',
                    'start_line': 10,
                    'end_line': 15,
                    'start_column': 5,
                    'end_column': 20
                },
                'message': {
                    'text': 'Test message'
                },
                'commit_sha': 'abc123def456',
                'ref': 'refs/heads/main',
                'analysis_key': 'test-analysis'
            },
            'state': 'open',
            'created_at': '2023-01-15T10:30:00Z',
            'updated_at': '2023-01-16T15:45:00Z',
            'dismissed_at': None,
            'dismissed_reason': None,
            'dismissed_by': None,
            'html_url': 'https://github.com/test-org/test-repo/security/code-scanning/1'
        }
        
        with patch.object(self.service, 'fetch_alert_instances') as mock_fetch_instances:
            mock_fetch_instances.return_value = ([], True)
            
            vulnerability = self.service.process_codeql_alert(alert_data, self.repo_full_name)
            
            assert vulnerability is not None
            assert vulnerability.repository_full_name == self.repo_full_name
            assert vulnerability.vulnerability_id == 'test-alert-123'
            assert vulnerability.rule_id == 'test-rule'
            assert vulnerability.severity == 'high'
            assert vulnerability.state == 'open'
            assert vulnerability.file_path == 'src/test.py'
            assert vulnerability.start_line == 10
            assert vulnerability.end_line == 15
    
    def test_process_codeql_alert_dismissed(self):
        """Test processing of dismissed CodeQL alert"""
        # Sample dismissed alert data
        alert_data = {
            'number': 2,
            'id': 'test-alert-456',
            'rule': {
                'id': 'test-rule-2',
                'name': 'Test Vulnerability 2',
                'description': 'Test description 2',
                'severity': 'warning',
                'precision': 'medium',
                'tags': []
            },
            'most_recent_instance': {
                'location': {
                    'path': 'src/test2.py',
                    'start_line': 20,
                    'end_line': 25
                },
                'message': {
                    'text': 'Test message 2'
                },
                'commit_sha': 'def456ghi789',
                'ref': 'refs/heads/main',
                'analysis_key': 'test-analysis'
            },
            'state': 'dismissed',
            'created_at': '2023-01-15T10:30:00Z',
            'updated_at': '2023-01-16T15:45:00Z',
            'dismissed_at': '2023-01-17T10:00:00Z',
            'dismissed_reason': 'false_positive',
            'dismissed_by': 'johndoe',
            'html_url': 'https://github.com/test-org/test-repo/security/code-scanning/2'
        }
        
        with patch.object(self.service, 'fetch_alert_instances') as mock_fetch_instances:
            mock_fetch_instances.return_value = ([], True)
            
            vulnerability = self.service.process_codeql_alert(alert_data, self.repo_full_name)
            
            assert vulnerability is not None
            assert vulnerability.state == 'dismissed'
            assert vulnerability.dismissed_reason == 'false_positive'
            assert vulnerability.dismissed_at is not None
    
    def test_process_codeql_alert_fixed(self):
        """Test processing of fixed CodeQL alert"""
        # Sample fixed alert data
        alert_data = {
            'number': 3,
            'id': 'test-alert-789',
            'rule': {
                'id': 'test-rule-3',
                'name': 'Test Vulnerability 3',
                'description': 'Test description 3',
                'severity': 'note',
                'precision': 'low',
                'tags': []
            },
            'most_recent_instance': {
                'location': {
                    'path': 'src/test3.py',
                    'start_line': 30,
                    'end_line': 35
                },
                'message': {
                    'text': 'Test message 3'
                },
                'commit_sha': 'ghi789jkl012',
                'ref': 'refs/heads/main',
                'analysis_key': 'test-analysis'
            },
            'state': 'fixed',
            'created_at': '2023-01-15T10:30:00Z',
            'updated_at': '2023-01-16T15:45:00Z',
            'fixed_at': '2023-01-18T10:00:00Z',
            'html_url': 'https://github.com/test-org/test-repo/security/code-scanning/3'
        }
        
        with patch.object(self.service, 'fetch_alert_instances') as mock_fetch_instances:
            mock_fetch_instances.return_value = ([], True)
            
            vulnerability = self.service.process_codeql_alert(alert_data, self.repo_full_name)
            
            assert vulnerability is not None
            assert vulnerability.state == 'fixed'
            assert vulnerability.fixed_at is not None
    
    def test_calculate_security_level_with_vulnerabilities(self):
        """Test security level calculation with vulnerabilities"""
        # Create mock vulnerabilities
        mock_vulns = [
            Mock(
                state='open',
                severity='high',
                category='sql-injection',
                created_at=datetime(2023, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
                get_age_days=lambda: 5,
                is_recently_fixed=lambda: False
            ),
            Mock(
                state='open',
                severity='medium',
                category='xss',
                created_at=datetime(2023, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
                get_age_days=lambda: 5,
                is_recently_fixed=lambda: False
            ),
            Mock(
                state='dismissed',
                severity='low',
                category='other',
                created_at=datetime(2023, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
                get_age_days=lambda: 5,
                is_recently_fixed=lambda: False
            )
        ]
        
        summary = self.service.calculate_security_level(mock_vulns)
        
        assert summary['level'] == 'high'
        assert summary['level_display'] == 'High'
        assert summary['total_vulnerabilities'] == 3
        assert summary['high_count'] == 1
        assert summary['medium_count'] == 1
        assert summary['low_count'] == 0
        assert summary['open_count'] == 2
        assert summary['dismissed_count'] == 1
        assert 'sql-injection' in summary['categories']
        assert 'xss' in summary['categories']
    
    def test_calculate_security_level_no_vulnerabilities(self):
        """Test security level calculation with no vulnerabilities"""
        summary = self.service.calculate_security_level([])
        
        assert summary['level'] == 'safe'
        assert summary['level_display'] == 'Safe'
        assert summary['total_vulnerabilities'] == 0
        assert summary['critical_count'] == 0
        assert summary['high_count'] == 0
        assert summary['medium_count'] == 0
        assert summary['low_count'] == 0
        assert summary['open_count'] == 0
        assert summary['fixed_count'] == 0
        assert summary['dismissed_count'] == 0
        assert summary['trend'] == 'stable'
    
    def test_calculate_security_level_critical_vulnerability(self):
        """Test security level calculation with critical vulnerability"""
        # Create mock critical vulnerability
        mock_vulns = [
            Mock(
                state='open',
                severity='critical',
                category='authentication',
                created_at=datetime(2023, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
                get_age_days=lambda: 5,
                is_recently_fixed=lambda: False
            )
        ]
        
        summary = self.service.calculate_security_level(mock_vulns)
        
        assert summary['level'] == 'critical'
        assert summary['level_display'] == 'Critical'
        assert summary['critical_count'] == 1
        assert summary['open_count'] == 1
    
    def test_map_github_severity_security_level(self):
        """Test GitHub severity mapping with security_severity_level"""
        rule_info = {'security_severity_level': 'critical'}
        severity = self.service.map_github_severity(rule_info)
        assert severity == 'critical'
        
        rule_info = {'security_severity_level': 'high'}
        severity = self.service.map_github_severity(rule_info)
        assert severity == 'high'
        
        rule_info = {'security_severity_level': 'medium'}
        severity = self.service.map_github_severity(rule_info)
        assert severity == 'medium'
        
        rule_info = {'security_severity_level': 'low'}
        severity = self.service.map_github_severity(rule_info)
        assert severity == 'low'
    
    def test_map_github_severity_tags(self):
        """Test GitHub severity mapping with tags"""
        rule_info = {'tags': ['security-severity: high']}
        severity = self.service.map_github_severity(rule_info)
        assert severity == 'high'
        
        rule_info = {'tags': ['security-severity: critical']}
        severity = self.service.map_github_severity(rule_info)
        assert severity == 'critical'
    
    def test_map_github_severity_fallback(self):
        """Test GitHub severity mapping fallback to generic severity"""
        rule_info = {'severity': 'error'}
        severity = self.service.map_github_severity(rule_info)
        assert severity == 'high'
        
        rule_info = {'severity': 'warning'}
        severity = self.service.map_github_severity(rule_info)
        assert severity == 'medium'
        
        rule_info = {'severity': 'note'}
        severity = self.service.map_github_severity(rule_info)
        assert severity == 'low'
    
    def test_map_github_severity_default(self):
        """Test GitHub severity mapping default case"""
        rule_info = {}
        severity = self.service.map_github_severity(rule_info)
        assert severity == 'medium'
        
        rule_info = {'severity': 'unknown'}
        severity = self.service.map_github_severity(rule_info)
        assert severity == 'medium'
    
    def test_extract_category_sql_injection(self):
        """Test category extraction for SQL injection"""
        rule_info = {'id': 'sql-injection-rule', 'tags': []}
        category = self.service._extract_category(rule_info)
        assert category == 'sql-injection'
        
        rule_info = {'id': 'test-rule', 'tags': ['sql']}
        category = self.service._extract_category(rule_info)
        assert category == 'sql-injection'
    
    def test_extract_category_xss(self):
        """Test category extraction for XSS"""
        rule_info = {'id': 'xss-rule', 'tags': []}
        category = self.service._extract_category(rule_info)
        assert category == 'xss'
        
        rule_info = {'id': 'test-rule', 'tags': ['cross-site-scripting']}
        category = self.service._extract_category(rule_info)
        assert category == 'xss'
    
    def test_extract_category_other(self):
        """Test category extraction for unknown rules"""
        rule_info = {'id': 'unknown-rule', 'tags': []}
        category = self.service._extract_category(rule_info)
        assert category == 'other'
    
    def test_extract_cwe_id(self):
        """Test CWE ID extraction"""
        rule_info = {'tags': ['CWE-79', 'other-tag']}
        cwe_id = self.service._extract_cwe_id(rule_info)
        assert cwe_id == 'CWE-79'
        
        rule_info = {'tags': ['other-tag', 'CWE-89']}
        cwe_id = self.service._extract_cwe_id(rule_info)
        assert cwe_id == 'CWE-89'
        
        rule_info = {'tags': ['other-tag']}
        cwe_id = self.service._extract_cwe_id(rule_info)
        assert cwe_id is None
