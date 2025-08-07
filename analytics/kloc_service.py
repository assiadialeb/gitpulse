"""
KLOC (Kilo Lines of Code) calculation service
Calculates repository size using git commands
"""
import os
import subprocess
import logging
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class KLOCService:
    """Service for calculating KLOC (Kilo Lines of Code) for repositories"""
    
    # File extensions to count as code
    CODE_EXTENSIONS = {
        # Python
        '.py', '.pyx', '.pxd', '.pyi',
        # JavaScript/TypeScript
        '.js', '.jsx', '.ts', '.tsx',
        # Java
        '.java', '.jsp', '.jspx',
        # C/C++
        '.c', '.cpp', '.cc', '.cxx', '.h', '.hpp', '.hxx',
        # C#
        '.cs', '.cshtml', '.razor',
        # PHP
        '.php', '.phtml',
        # Ruby
        '.rb', '.erb', '.rake',
        # Go
        '.go',
        # Rust
        '.rs',
        # Swift
        '.swift',
        # Kotlin
        '.kt', '.kts',
        # Scala
        '.scala',
        # Clojure
        '.clj', '.cljs', '.cljc',
        # Haskell
        '.hs', '.lhs',
        # F#
        '.fs', '.fsx', '.fsi',
        # Visual Basic
        '.vb', '.vbs',
        # SQL
        '.sql',
        # Shell scripts
        '.sh', '.bash', '.zsh', '.fish', '.ksh',
        # R
        '.r', '.R',
        # MATLAB
        '.m',
        # Perl
        '.pl', '.pm',
        # Tcl
        '.tcl',
        # Lua
        '.lua',
        # Dart
        '.dart',
        # Elm
        '.elm',
        # Elixir
        '.ex', '.exs',
        # Crystal
        '.cr',
        # Nim
        '.nim',
        # V
        '.v',
        # Lean
        '.lean',
        # Agda
        '.agda',
        # Idris
        '.idr',
        # Coq
        '.v',
    }
    
    @staticmethod
    def calculate_kloc(repo_path: str) -> Dict:
        """
        Calculate KLOC (Kilo Lines of Code) for a repository
        
        Args:
            repo_path: Path to the git repository
            
        Returns:
            Dictionary with KLOC data:
            {
                'kloc': float,
                'total_lines': int,
                'language_breakdown': Dict[str, int],
                'calculated_at': datetime
            }
        """
        if not os.path.exists(repo_path):
            logger.error(f"Repository path does not exist: {repo_path}")
            return {
                'kloc': 0.0,
                'total_lines': 0,
                'language_breakdown': {},
                'calculated_at': datetime.now()
            }
        
        try:
            # Change to repository directory
            original_cwd = os.getcwd()
            os.chdir(repo_path)
            
            # Get list of tracked files
            result = subprocess.run(
                ['git', 'ls-files', '--cached', '--exclude-standard'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                logger.error(f"Failed to get git files: {result.stderr}")
                return {
                    'kloc': 0.0,
                    'total_lines': 0,
                    'language_breakdown': {},
                    'calculated_at': datetime.now()
                }
            
            files = result.stdout.strip().split('\n')
            if not files or files == ['']:
                logger.warning(f"No files found in repository: {repo_path}")
                return {
                    'kloc': 0.0,
                    'total_lines': 0,
                    'language_breakdown': {},
                    'calculated_at': datetime.now()
                }
            
            # Filter code files
            code_files = []
            for file_path in files:
                if file_path.strip():
                    _, ext = os.path.splitext(file_path)
                    if ext.lower() in KLOCService.CODE_EXTENSIONS:
                        code_files.append(file_path)
            
            if not code_files:
                logger.warning(f"No code files found in repository: {repo_path}")
                return {
                    'kloc': 0.0,
                    'total_lines': 0,
                    'language_breakdown': {},
                    'calculated_at': datetime.now()
                }
            
            # Count lines for each file
            total_lines = 0
            language_breakdown = {}
            
            for file_path in code_files:
                try:
                    # Count lines in file
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = len(f.readlines())
                    
                    total_lines += lines
                    
                    # Group by language
                    _, ext = os.path.splitext(file_path)
                    ext = ext.lower()
                    language = KLOCService._get_language_name(ext)
                    
                    if language in language_breakdown:
                        language_breakdown[language] += lines
                    else:
                        language_breakdown[language] = lines
                        
                except Exception as e:
                    logger.warning(f"Error counting lines in {file_path}: {e}")
                    continue
            
            # Calculate KLOC
            kloc = total_lines / 1000.0
            
            logger.info(f"Calculated KLOC for {repo_path}: {kloc:.2f} KLOC ({total_lines} lines)")
            
            return {
                'kloc': kloc,
                'total_lines': total_lines,
                'language_breakdown': language_breakdown,
                'calculated_at': datetime.now()
            }
            
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout calculating KLOC for {repo_path}")
            return {
                'kloc': 0.0,
                'total_lines': 0,
                'language_breakdown': {},
                'calculated_at': datetime.now()
            }
        except Exception as e:
            logger.error(f"Error calculating KLOC for {repo_path}: {e}")
            return {
                'kloc': 0.0,
                'total_lines': 0,
                'language_breakdown': {},
                'calculated_at': datetime.now()
            }
        finally:
            # Restore original working directory
            os.chdir(original_cwd)
    
    @staticmethod
    def _get_language_name(extension: str) -> str:
        """Get language name from file extension"""
        language_map = {
            '.py': 'Python',
            '.js': 'JavaScript',
            '.ts': 'TypeScript',
            '.jsx': 'React JSX',
            '.tsx': 'React TSX',
            '.java': 'Java',
            '.c': 'C',
            '.cpp': 'C++',
            '.h': 'C Header',
            '.hpp': 'C++ Header',
            '.cs': 'C#',
            '.php': 'PHP',
            '.rb': 'Ruby',
            '.go': 'Go',
            '.rs': 'Rust',
            '.swift': 'Swift',
            '.kt': 'Kotlin',
            '.scala': 'Scala',
            '.clj': 'Clojure',
            '.hs': 'Haskell',
            '.fs': 'F#',
            '.vb': 'Visual Basic',
            '.sql': 'SQL',
            '.sh': 'Shell',
            '.r': 'R',
            '.m': 'MATLAB',
            '.pl': 'Perl',
            '.lua': 'Lua',
            '.dart': 'Dart',
            '.elm': 'Elm',
            '.ex': 'Elixir',
            '.cr': 'Crystal',
            '.nim': 'Nim',
            '.v': 'V',
            '.lean': 'Lean',
            '.agda': 'Agda',
            '.idr': 'Idris',
            '.coq': 'Coq',
        }
        
        return language_map.get(extension, extension[1:].upper() if extension else 'Unknown') 