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

    # --- Custom ratios and status logic ---
    # Test Coverage Ratio: test/feature >= 0.3 is good
    test_count = stats['test']
    feature_count = stats['feature']
    fix_count = stats['fix']
    if feature_count > 0:
        test_feature_ratio = test_count / feature_count
    else:
        test_feature_ratio = 0
    test_feature_good = test_feature_ratio >= 0.3
    test_feature_status = 'good' if test_feature_good else 'poor'
    test_feature_message = (
        'The ratio of test to feature commits reflects a strong commitment to test coverage. This improves code reliability, eases refactoring, and supports long-term maintainability.'
        if test_feature_good else
        'A low test-to-feature ratio can be a sign of insufficient test coverage. This increases the risk of regressions and may reduce confidence in the stability of new features.'
    )

    # Feature-to-Fix Ratio: feature/fix > 1 is good
    if fix_count > 0:
        feature_fix_ratio = feature_count / fix_count
    else:
        feature_fix_ratio = feature_count
    feature_fix_good = feature_fix_ratio > 1
    feature_fix_status = 'good' if feature_fix_good else 'poor'
    feature_fix_message = (
        'The current feature-to-fix ratio indicates a healthy focus on building new capabilities, with fewer bug fixes. This suggests the codebase is relatively stable and development is moving forward.'
        if feature_fix_good else
        'A low feature-to-fix ratio may indicate a high maintenance burden or recurring issues. It can suggest technical debt or instability slowing down the delivery of new value.'
    )

    # Focus Ratio: (chore + docs) / total < 0.3 is good
    chore_docs_count = stats['chore'] + stats['docs']
    if total > 0:
        chore_docs_ratio = chore_docs_count / total
    else:
        chore_docs_ratio = 0
    chore_docs_good = chore_docs_ratio < 0.3
    chore_docs_status = 'good' if chore_docs_good else 'poor'
    chore_docs_message = (
        'The project shows a clear focus on product-driven development, with a balanced investment in documentation and infrastructure work.'
        if chore_docs_good else
        'A high percentage of chore and documentation commits may indicate overhead or fragmented focus. This can reduce direct impact on feature delivery and product value.'
    )

    return {
        'counts': stats,
        'percentages': percentages,
        'total': total,
        # New ratios and status
        'test_feature_ratio': round(test_feature_ratio, 2),
        'test_feature_status': test_feature_status,
        'test_feature_message': test_feature_message,
        'feature_fix_ratio': round(feature_fix_ratio, 2),
        'feature_fix_status': feature_fix_status,
        'feature_fix_message': feature_fix_message,
        'chore_docs_ratio': round(chore_docs_ratio, 2),
        'chore_docs_status': chore_docs_status,
        'chore_docs_message': chore_docs_message,
    }


def classify_commit_with_files(message: str, files: list) -> str:
    """
    Classify a commit using both the message and the list of modified files.
    - Si tous les fichiers sont de la doc, retourne 'docs'.
    - Si tous les fichiers sont infra/config, retourne 'chore'.
    - Sinon, applique la logique standard sur le message.
    """
    if not files or not isinstance(files, list):
        return classify_commit_with_ollama_fallback(message)

    doc_exts = {'.md', '.rst', '.adoc', '.markdown', '.txt'}
    chore_exts = {'.tf', '.tfvars', '.yml', '.yaml', '.json', '.env', '.ini', '.cfg', '.lock', '.dockerfile', '.gitignore', '.gitattributes', '.sh', '.bat', '.ps1'}
    
    def get_ext(f):
        f = f.lower()
        if f.startswith('dockerfile'):
            return '.dockerfile'
        return '.' + f.split('.')[-1] if '.' in f else ''

    exts = set(get_ext(f) for f in files)
    # Si tous les fichiers sont de la doc
    if exts and all(e in doc_exts for e in exts):
        return 'docs'
    # Si tous les fichiers sont infra/config
    if exts and all(e in chore_exts for e in exts):
        return 'chore'
    # Sinon, logique standard
    return classify_commit_with_ollama_fallback(message) 