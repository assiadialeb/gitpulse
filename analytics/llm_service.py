"""
LLM Service for license analysis using Ollama
"""
import json
import logging
from typing import Dict, List, Optional
from django.conf import settings
import ollama

logger = logging.getLogger(__name__)


class LLMService:
    """Service for interacting with Ollama LLM using the official Python library"""
    
    def __init__(self):
        self.model = settings.OLLAMA_MODEL
        self.host = self._normalize_host(settings.OLLAMA_HOST)
        # Create a proper Ollama client instance
        self.client = ollama.Client(host=self.host)
        logger.info(f"Ollama client configured with host: {self.host}, model: {self.model}")
    
    def _normalize_host(self, host: str) -> str:
        """Normalize the host URL for Ollama"""
        if host.startswith('http://'):
            return host
        elif host.startswith('https://'):
            return host.replace('https://', 'http://')
        else:
            return f"http://{host}"
    
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
            logger.info(f"Starting license verdict analysis for {len(licenses)} licenses")
            
            # Prepare the simple prompt
            prompt = self._create_verdict_prompt(licenses)
            logger.debug(f"Created prompt for verdict analysis")
            
            # Call Ollama
            logger.info(f"Calling Ollama for verdict")
            response = self._call_ollama(prompt)
            
            if response:
                logger.info(f"Received response from Ollama: {response[:100]}...")
                # Clean the response to get just the verdict
                verdict = response.strip()
                
                # Validate the response is exactly what we expect
                valid_responses = ["✅ Compatible", "⚠️ Caution", "❌ Not Compatible"]
                if verdict in valid_responses:
                    logger.info(f"Valid verdict: {verdict}")
                    return verdict
                else:
                    logger.warning(f"Invalid verdict response: '{verdict}', using fallback")
                    # Fallback based on license types
                    return self._fallback_verdict(licenses)
            else:
                logger.warning("No response from Ollama, using fallback")
                return self._fallback_verdict(licenses)
                
        except Exception as e:
            logger.error(f"Error getting license verdict: {e}")
            return self._fallback_verdict(licenses)
    
    def _fallback_verdict(self, licenses: List[str]) -> str:
        """Fallback verdict based on license analysis"""
        if not licenses:
            return 'Caution'
        
        # Contaminating licenses that can require open-sourcing
        contaminating_licenses = ['AGPL', 'GPL', 'LGPL', 'MPL', 'EPL', 'CDDL']
        
        # Permissive licenses that allow commercial use
        permissive_licenses = ['MIT', 'APACHE', 'BSD', 'ISC', 'UNLICENSE', '0BSD', 'CC0', 'WTFPL']
        
        # Check for contaminating licenses first
        for license in licenses:
            license_upper = license.upper()
            if any(contaminating in license_upper for contaminating in contaminating_licenses):
                return 'Not compatible'
        
        # Check if all licenses are permissive
        all_permissive = all(
            any(permissive in license.upper() for permissive in permissive_licenses)
            for license in licenses
        )
        
        if all_permissive:
            return 'Compatible'
        else:
            return 'Caution'
    
    def _create_license_prompt(self, licenses: List[str]) -> str:
        """Create a prompt for license analysis"""
        license_list = ', '.join(licenses)
        
        prompt = f"""You are an expert software licensing attorney specializing in open source licenses and commercial software development.

Analyze these open source licenses for commercial compatibility: {license_list}

IMPORTANT: Respond with ONLY valid JSON. No text before or after the JSON.

{{
    "commercial_compatibility": "YES/NO/CAUTION",
    "summary": "2-3 sentence summary of the legal implications",
    "key_obligations": ["3-5 main legal obligations"],
    "key_restrictions": ["3-5 main legal restrictions"],
    "recommendations": ["3-5 actionable legal recommendations"]
}}

Legal Analysis Rules:
- YES: All licenses are permissive and allow commercial use (MIT, Apache, BSD, ISC, etc.)
- NO: Any contaminating license present (AGPL, GPL, LGPL, or other copyleft licenses that require source code disclosure)
- CAUTION: Mixed licenses with potential conflicts or unclear commercial implications

Key Legal Principles:
- A single contaminating license (like AGPL) can require the entire project to be open-sourced
- Copyleft licenses can impose significant restrictions on commercial use
- Patent clauses and attribution requirements must be carefully considered

Respond with ONLY the JSON object, no additional text."""
        
        return prompt
    
    def _create_verdict_prompt(self, licenses: List[str]) -> str:
        """Create a prompt for simple verdict"""
        license_list = ', '.join(licenses)
        
        prompt = f"""You are an expert software licensing attorney specializing in open source licenses and commercial software development.

Analyze these open source licenses for commercial compatibility: {license_list}

Legal Analysis Rules:
- YES: All licenses are permissive and allow commercial use (MIT, Apache, BSD, ISC, etc.)
- NO: Any contaminating license present (AGPL, GPL, LGPL, or other copyleft licenses that require source code disclosure)
- CAUTION: Mixed licenses with potential conflicts or unclear commercial implications

Key Legal Principles:
- A single contaminating license (like AGPL) can require the entire project to be open-sourced
- Copyleft licenses can impose significant restrictions on commercial use
- Patent clauses and attribution requirements must be carefully considered

Respond with ONLY ONE of these exact responses:
- "✅ Compatible"
- "⚠️ Caution" 
- "❌ Not Compatible"

Consider the legal implications of each license and their combined effect on commercial use.

Respond with only the exact verdict with emoji, no explanation."""

        return prompt
    
    def _call_ollama(self, prompt: str) -> Optional[str]:
        """Call Ollama API using the official Python library"""
        try:
            logger.info(f"Calling Ollama with model {self.model}")
            
            # Use the client instance to call generate
            response = self.client.generate(
                model=self.model,
                prompt=prompt,
                options={
                    'temperature': 0.0,
                    'top_p': 0.8,
                    'num_predict': 2000,
                }
            )
            
            response_text = response['response'].strip()
            logger.info(f"Ollama response received successfully, length: {len(response_text)}")
            return response_text
                
        except Exception as e:
            logger.error(f"Error calling Ollama: {e}")
            return None
    
    def parse_llm_response(self, response: str) -> Dict:
        """Parse LLM response and extract JSON"""
        try:
            # Clean the response
            response = response.strip()
            
            # Try to extract JSON from response
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            
            if start_idx != -1 and end_idx > start_idx:
                json_str = response[start_idx:end_idx]
                
                # Try to parse the JSON
                try:
                    parsed = json.loads(json_str)
                    
                    # Validate the expected structure
                    if isinstance(parsed, dict):
                        return parsed
                    else:
                        return {
                            'raw_response': response,
                            'error': 'Response is not a valid JSON object'
                        }
                        
                except json.JSONDecodeError as e:
                    # Try to clean up common JSON formatting issues
                    cleaned_json = json_str.replace('\n', ' ').replace('\t', ' ')
                    try:
                        parsed = json.loads(cleaned_json)
                        return parsed
                    except json.JSONDecodeError:
                        return {
                            'raw_response': response,
                            'error': f'JSON parsing error: {str(e)}'
                        }
            else:
                # No JSON found in response
                return {
                    'raw_response': response,
                    'error': 'No JSON object found in response'
                }
                
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")
            return {
                'raw_response': response,
                'error': str(e)
            } 