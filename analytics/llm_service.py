"""
LLM Service for license analysis using Ollama
"""
import os
import json
import logging
import requests
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class LLMService:
    """Service for interacting with Ollama LLM"""
    
    def __init__(self):
        self.ollama_url = os.getenv('OLLAMA_URL', 'http://localhost:11434')
        self.model = os.getenv('OLLAMA_MODEL', 'llama3.2:latest')
    
    def analyze_licenses(self, licenses: List[str]) -> Dict:
        """
        Analyze licenses using Ollama LLM
        
        Args:
            licenses: List of unique license names
            
        Returns:
            Dictionary with LLM analysis
        """
        try:
            # Prepare the prompt
            prompt = self._create_license_prompt(licenses)
            
            # Call Ollama
            response = self._call_ollama(prompt)
            
            if response:
                return {
                    'success': True,
                    'analysis': response,
                    'licenses_analyzed': licenses
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to get response from Ollama'
                }
                
        except Exception as e:
            logger.error(f"Error analyzing licenses with LLM: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_license_verdict(self, licenses: List[str]) -> str:
        """
        Get simple verdict for license compatibility
        
        Args:
            licenses: List of unique license names
            
        Returns:
            Simple verdict: "Compatible", "Caution", or "Not compatible"
        """
        try:
            # Prepare the simple prompt
            prompt = self._create_verdict_prompt(licenses)
            
            # Call Ollama
            response = self._call_ollama(prompt)
            
            if response:
                # Clean the response to get just the verdict
                verdict = response.strip().upper()
                if 'COMPATIBLE' in verdict:
                    return 'Compatible'
                elif 'CAUTION' in verdict:
                    return 'Caution'
                elif 'NOT COMPATIBLE' in verdict or 'INCOMPATIBLE' in verdict:
                    return 'Not compatible'
                else:
                    # Fallback based on license types
                    return self._fallback_verdict(licenses)
            else:
                return self._fallback_verdict(licenses)
                
        except Exception as e:
            logger.error(f"Error getting license verdict: {e}")
            return self._fallback_verdict(licenses)
    
    def _fallback_verdict(self, licenses: List[str]) -> str:
        """Fallback verdict based on license analysis"""
        permissive_licenses = ['MIT', 'APACHE', 'BSD', 'ISC', 'UNLICENSE', '0BSD']
        restrictive_licenses = ['GPL', 'AGPL', 'LGPL', 'MPL']
        
        permissive_count = sum(1 for license in licenses if any(perm in license.upper() for perm in permissive_licenses))
        restrictive_count = sum(1 for license in licenses if any(rest in license.upper() for rest in restrictive_licenses))
        
        total = len(licenses)
        if total == 0:
            return 'Caution'
        
        permissive_ratio = permissive_count / total
        restrictive_ratio = restrictive_count / total
        
        if permissive_ratio >= 0.7:
            return 'Compatible'
        elif restrictive_ratio >= 0.3:
            return 'Not compatible'
        else:
            return 'Caution'
    
    def _create_license_prompt(self, licenses: List[str]) -> str:
        """Create a prompt for license analysis"""
        license_list = ', '.join(licenses)
        
        prompt = f"""Analyze these open source licenses: {license_list}

Provide a concise analysis in JSON format:
{{
    "commercial_compatibility": "YES/NO/CAUTION",
    "summary": "2-3 sentence summary",
    "key_obligations": ["3-5 main obligations"],
    "key_restrictions": ["3-5 main restrictions"],
    "recommendations": ["3-5 actionable recommendations"]
}}

Rules for commercial_compatibility:
- YES: If 70%+ licenses are permissive (MIT, Apache, BSD, ISC)
- CAUTION: If significant copyleft licenses (GPL, LGPL) or patent issues
- NO: If 30%+ restrictive licenses that prevent commercial use

Keep responses brief and actionable. Focus on practical implications for commercial use."""
        
        return prompt
    
    def _create_verdict_prompt(self, licenses: List[str]) -> str:
        """Create a prompt for simple verdict"""
        license_list = ', '.join(licenses)
        
        prompt = f"""Analyze these open source licenses: {license_list}

Respond with ONLY ONE WORD: "Compatible", "Caution", or "Not compatible"

Rules:
- "Compatible": If 70%+ licenses are permissive (MIT, Apache, BSD, ISC)
- "Caution": If significant copyleft licenses (GPL, LGPL) or patent issues
- "Not compatible": If 30%+ restrictive licenses that prevent commercial use

Respond with only the verdict word, nothing else."""

        return prompt
    
    def _call_ollama(self, prompt: str) -> Optional[str]:
        """Call Ollama API"""
        try:
            url = f"{self.ollama_url}/api/generate"
            
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "top_p": 0.9,
                    "max_tokens": 1000
                }
            }
            
            response = requests.post(url, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                return result.get('response', '').strip()
            else:
                logger.error(f"Ollama API error: {response.status_code} - {response.text}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error calling Ollama: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error calling Ollama: {e}")
            return None
    
    def parse_llm_response(self, response: str) -> Dict:
        """Parse LLM response and extract JSON"""
        try:
            # Try to extract JSON from response
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            
            if start_idx != -1 and end_idx > start_idx:
                json_str = response[start_idx:end_idx]
                return json.loads(json_str)
            else:
                # Fallback: return raw response
                return {
                    'raw_response': response,
                    'error': 'Could not parse JSON from response'
                }
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            return {
                'raw_response': response,
                'error': f'JSON parsing error: {str(e)}'
            }
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")
            return {
                'raw_response': response,
                'error': str(e)
            } 