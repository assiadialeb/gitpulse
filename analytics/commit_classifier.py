"""
Commit classification service
"""
import re
import requests
from typing import Tuple


def classify_commit(message: str) -> str:
    """
    Classify a commit message into categories
    
    Args:
        message: Commit message to classify
        
    Returns:
        Category: 'fix', 'feature', 'docs', 'refactor', 'test', 'style', 'chore', 'other'
    """
    if not message:
        return 'other'
    
    message = message.lower().strip()
    
    # Pattern matching with priority order
    patterns = {
        'fix': r'^(fix|bug|hotfix|patch|resolve|correct)',
        'feature': r'^(feat|add|implement|new|enhance|improve)',
        'docs': r'^(docs|readme|documentation|comment)',
        'refactor': r'^(refactor|cleanup|restructure|optimize|reorganize)',
        'test': r'^(test|spec|specs|testing|coverage)',
        'style': r'^(style|format|lint|prettier|indent)',
        'chore': r'^(chore|ci|build|deploy|maintenance|deps)'
    }
    
    # Check patterns in priority order
    for category, pattern in patterns.items():
        if re.match(pattern, message):
            return category
    
    # Check for conventional commits format
    if ':' in message:
        prefix = message.split(':')[0]
        if prefix in ['feat', 'fix', 'docs', 'refactor', 'test', 'style', 'chore']:
            return prefix
    
    # Check for parentheses format (feat(scope): message)
    if '(' in message and ')' in message:
        prefix = message.split('(')[0]
        if prefix in ['feat', 'fix', 'docs', 'refactor', 'test', 'style', 'chore']:
            return prefix
    
    # Heuristics for short messages
    if len(message) < 15:
        return 'chore'  # Short messages are usually maintenance
    
    return 'other'


def classify_commit_with_ollama_fallback(message: str) -> str:
    """
    Classify a commit message using simple classifier first, then Ollama as fallback
    
    Args:
        message: Commit message to classify
        
    Returns:
        Category: 'fix', 'feature', 'docs', 'refactor', 'test', 'style', 'chore', 'other'
    """
    # First try the simple classifier
    simple_result = classify_commit(message)
    
    # If simple classifier returns 'other', try Ollama
    if simple_result == 'other':
        return classify_commit_ollama(message)
    
    return simple_result


def classify_commit_ollama(message: str) -> str:
    """
    Classify a commit message using Ollama LLM
    
    Args:
        message: Commit message to classify
        
    Returns:
        Category: 'fix', 'feature', 'docs', 'refactor', 'test', 'style', 'chore', 'other'
    """
    # Ollama configuration from environment variables
    import os
    OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'localhost')
    OLLAMA_PORT = os.getenv('OLLAMA_PORT', '11434')
    OLLAMA_URL = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}"
    MODEL_NAME = "gemma3:4b"
    
    prompt = f"""Classify this git commit message:

"{message}"

Categories: test, fix, feature, docs, refactor, style, perf, ci, chore, other

Answer with only one word:"""

    try:
        # Call Ollama API
        payload = {
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": 10
            }
        }
        
        response = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        llm_response = result.get('response', '').strip().lower()
        
        # Extract the category from response - only use valid MongoDB choices
        valid_categories = ['fix', 'feature', 'docs', 'refactor', 'test', 'style', 'chore', 'other']
        for category in valid_categories:
            if category in llm_response:
                return category
        
        # Handle common variations that the LLM might use
        variations = {
            'update': 'chore',
            'change': 'refactor',
            'modify': 'refactor',
            'improve': 'feature',
            'enhance': 'feature',
            'add': 'feature',
            'remove': 'refactor',
            'delete': 'refactor',
            'clean': 'refactor',
            'cleanup': 'refactor',
            'optimize': 'refactor',  # Changed from 'perf' to 'refactor'
            'speed': 'refactor',     # Changed from 'perf' to 'refactor'
            'fast': 'refactor',      # Changed from 'perf' to 'refactor'
            'slow': 'refactor',      # Changed from 'perf' to 'refactor'
            'perf': 'refactor',      # Map 'perf' to 'refactor'
            'ci': 'chore',           # Map 'ci' to 'chore'
            'build': 'chore',
            'deploy': 'chore',
            'maintenance': 'chore'
        }
        
        for variation, category in variations.items():
            if variation in llm_response.lower():
                return category
        
        # If no category found in LLM response, return 'other'
        return 'other'
        
    except Exception as e:
        # If Ollama fails, return 'other'
        return 'other'


def classify_commit_with_confidence(message: str) -> Tuple[str, float]:
    """
    Classify a commit message with confidence score
    
    Args:
        message: Commit message to classify
        
    Returns:
        Tuple of (category, confidence_score)
    """
    if not message:
        return 'other', 0.0
    
    message = message.lower().strip()
    
    # Score categories based on keyword presence
    scores = {
        'fix': 0, 'feature': 0, 'docs': 0, 
        'refactor': 0, 'test': 0, 'style': 0, 'chore': 0
    }
    
    # Keywords for each category
    keywords = {
        'fix': ['fix', 'bug', 'hotfix', 'patch', 'resolve', 'correct', 'repair'],
        'feature': ['feat', 'add', 'implement', 'new', 'enhance', 'improve', 'create'],
        'docs': ['docs', 'readme', 'documentation', 'comment', 'doc'],
        'refactor': ['refactor', 'cleanup', 'restructure', 'optimize', 'reorganize', 'simplify'],
        'test': ['test', 'spec', 'specs', 'testing', 'coverage', 'unit'],
        'style': ['style', 'format', 'lint', 'prettier', 'indent', 'whitespace'],
        'chore': ['chore', 'ci', 'build', 'deploy', 'maintenance', 'deps', 'update']
    }
    
    # Calculate scores
    for category, words in keywords.items():
        for word in words:
            if word in message:
                scores[category] += 1
    
    # Get best category
    best_category = max(scores, key=scores.get)
    total_score = sum(scores.values())
    
    # Calculate confidence (0.0 to 1.0)
    confidence = scores[best_category] / max(total_score, 1)
    
    # If no keywords found, use pattern matching
    if total_score == 0:
        category = classify_commit(message)
        confidence = 0.5 if category != 'other' else 0.0
        return category, confidence
    
    return best_category, confidence


def get_commit_type_stats(commits) -> dict:
    """
    Get statistics for commit types
    
    Args:
        commits: QuerySet or list of commits
        
    Returns:
        Dictionary with commit type statistics
    """
    stats = {
        'fix': 0, 'feature': 0, 'docs': 0, 'refactor': 0, 
        'test': 0, 'style': 0, 'chore': 0, 'other': 0
    }
    
    for commit in commits:
        commit_type = getattr(commit, 'commit_type', 'other')
        if commit_type in stats:
            stats[commit_type] += 1
    
    # Calculate percentages
    total = sum(stats.values())
    if total > 0:
        percentages = {k: (v / total) * 100 for k, v in stats.items()}
    else:
        percentages = {k: 0 for k in stats.keys()}
    
    return {
        'counts': stats,
        'percentages': percentages,
        'total': total
    } 