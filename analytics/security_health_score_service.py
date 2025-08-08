import math
from collections import Counter
from datetime import datetime
from mongoengine import DoesNotExist
from .models import SecurityHealthHistory, CodeQLVulnerability


class SecurityHealthScoreService:
    """Service for calculating Security Health Score (SHS)"""
    
    def __init__(self):
        # Vulnerability severity weights
        self.weights = {
            'critical': 1.0,
            'high': 0.7,
            'medium': 0.4,
            'low': 0.1
        }
        self.alpha = 0.5  # Saturation parameter
    
    def calculate_shs(self, repository_full_name, repository_id, kloc):
        """
        Calculate Security Health Score for a repository
        
        Args:
            repository_full_name (str): Repository full name (owner/repo)
            repository_id (int): Repository ID
            kloc (float): Kilo Lines of Code
            
        Returns:
            dict: SHS calculation results
        """
        try:
            # Get open vulnerabilities only
            vulnerabilities = CodeQLVulnerability.objects.filter(
                repository_full_name=repository_full_name,
                state='open'
            )
            
            if not vulnerabilities:
                # No vulnerabilities found - check if CodeQL analysis is available
                if self._has_codeql_analysis(repository_full_name):
                    return {
                        'shs_score': 100.0,
                        'status': 'perfect',
                        'message': 'No vulnerabilities found',
                        'total_vulnerabilities': 0,
                        'severity_counts': {'critical': 0, 'high': 0, 'medium': 0, 'low': 0},
                        'kloc': kloc,
                        'delta_shs': 0.0
                    }
                else:
                    return {
                        'shs_score': None,
                        'status': 'not_available',
                        'message': 'CodeQL analysis not available',
                        'total_vulnerabilities': 0,
                        'severity_counts': {'critical': 0, 'high': 0, 'medium': 0, 'low': 0},
                        'kloc': kloc,
                        'delta_shs': 0.0
                    }
            
            # Count vulnerabilities by severity
            severity_counts = Counter()
            for vuln in vulnerabilities:
                severity_counts[vuln.severity] += 1
            
            # Calculate weighted total
            total_weight = sum(
                severity_counts[sev] * self.weights[sev] 
                for sev in self.weights.keys()
            )
            
            # Handle edge cases
            if kloc <= 0:
                return {
                    'shs_score': None,
                    'status': 'not_available',
                    'message': 'Repository size not available',
                    'total_vulnerabilities': len(vulnerabilities),
                    'severity_counts': dict(severity_counts),
                    'kloc': kloc,
                    'delta_shs': 0.0
                }
            
            # Calculate surface score
            score_surface = total_weight / kloc
            
            # Apply exponential decay function (higher vulnerabilities = lower score)
            current_shs = 100 * math.exp(-self.alpha * score_surface)
            current_shs = round(current_shs, 1)
            
            # Check if we have a recent calculation (within last hour) to avoid duplicates
            from datetime import timedelta
            from django.utils import timezone
            
            recent_calculation = SecurityHealthHistory.objects.filter(
                repository_full_name=repository_full_name
            ).order_by('-calculated_at').first()
            
            should_save_new = True
            if recent_calculation:
                time_diff = timezone.now() - recent_calculation.calculated_at
                # If the last calculation was within the last hour and the score is the same, don't save again
                if time_diff < timedelta(hours=1) and abs(recent_calculation.shs_score - current_shs) < 0.1:
                    should_save_new = False
                    # Use the existing calculation
                    return {
                        'shs_score': recent_calculation.shs_score,
                        'status': 'calculated',
                        'message': f'Score calculated from {len(vulnerabilities)} vulnerabilities',
                        'total_vulnerabilities': len(vulnerabilities),
                        'severity_counts': dict(severity_counts),
                        'kloc': kloc,
                        'delta_shs': recent_calculation.delta_shs
                    }
            
            # Get delta from previous analysis (before saving new one)
            delta_shs = self._calculate_delta_shs(repository_full_name, current_shs)
            
            # Save to history only if needed
            if should_save_new:
                self._save_shs_history(
                    repository_full_name, repository_id, current_shs, 
                    delta_shs, severity_counts, kloc
                )
            
            return {
                'shs_score': current_shs,
                'status': 'calculated',
                'message': f'Score calculated from {len(vulnerabilities)} vulnerabilities',
                'total_vulnerabilities': len(vulnerabilities),
                'severity_counts': dict(severity_counts),
                'kloc': kloc,
                'delta_shs': round(delta_shs, 1)
            }
            
        except Exception as e:
            return {
                'shs_score': None,
                'status': 'error',
                'message': f'Error calculating SHS: {str(e)}',
                'total_vulnerabilities': 0,
                'severity_counts': {'critical': 0, 'high': 0, 'medium': 0, 'low': 0},
                'kloc': kloc,
                'delta_shs': 0.0
            }
    
    def _has_codeql_analysis(self, repository_full_name):
        """Check if CodeQL analysis is available for the repository"""
        try:
            # Check if any CodeQL data exists (even if no vulnerabilities)
            return len(CodeQLVulnerability.objects.filter(
                repository_full_name=repository_full_name
            )) > 0
        except:
            return False
    
    def _calculate_delta_shs(self, repository_full_name, current_shs):
        """Calculate delta from previous SHS analysis"""
        try:
            # Get the most recent previous analysis
            previous = SecurityHealthHistory.objects.filter(
                repository_full_name=repository_full_name
            ).order_by('-calculated_at').first()
            
            if previous:
                return current_shs - previous.shs_score
            else:
                return 0.0
        except:
            return 0.0
    
    def _save_shs_history(self, repository_full_name, repository_id, shs_score, 
                          delta_shs, severity_counts, kloc):
        """Save SHS calculation to history"""
        try:
            now = datetime.now()
            month = now.strftime('%Y-%m')
            
            history = SecurityHealthHistory(
                repository_full_name=repository_full_name,
                repository_id=repository_id,
                shs_score=shs_score,
                delta_shs=delta_shs,
                calculated_at=now,
                month=month,
                total_vulnerabilities=sum(severity_counts.values()),
                critical_count=severity_counts.get('critical', 0),
                high_count=severity_counts.get('high', 0),
                medium_count=severity_counts.get('medium', 0),
                low_count=severity_counts.get('low', 0),
                kloc=kloc
            )
            history.save()
            
        except Exception as e:
            # Log error but don't fail the calculation
            print(f"Error saving SHS history: {e}")
    
    def get_shs_trend(self, repository_full_name, months=6):
        """Get SHS trend over the last N months"""
        try:
            histories = SecurityHealthHistory.objects.filter(
                repository_full_name=repository_full_name
            ).order_by('-calculated_at').limit(months)
            
            return [{
                'month': h.month,
                'shs_score': h.shs_score,
                'delta_shs': h.delta_shs,
                'calculated_at': h.calculated_at
            } for h in histories]
        except:
            return [] 