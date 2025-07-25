"""
Commit classification service
"""
import re
import requests
from typing import Tuple, List
from concurrent.futures import ThreadPoolExecutor, as_completed


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
        'fix': r'^(fix|bug|hotfix|patch|resolve|correct|repair|revert|rollback|undo|restore)',
        'feature': r'^(feat|add|implement|new|enhance|improve|create|introduce|enable)',
        'docs': r'^(docs|readme|documentation|comment|doc|clarify|document)',
        'refactor': r'^(refactor|cleanup|restructure|optimize|reorganize|simplify|migrate|port|rewrite)',
        'test': r'^(test|spec|specs|testing|coverage|unit|integration|e2e)',
        'style': r'^(style|format|lint|prettier|indent|whitespace)',
        'chore': r'^(chore|ci|build|deploy|maintenance|deps|update|change|modify|configure|setup|install|uninstall|bump|upgrade|downgrade|pin|unpin|sync|merge|wip|tmp|temp)'
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
    
    # Check for common words in the message (not just at the beginning)
    words = message.split()
    for word in words:
        if word in ['update', 'change', 'modify', 'improve', 'add', 'remove', 'delete', 'fix', 'bug', 'feature', 'new', 'test', 'doc', 'format', 'style', 'chore', 'ci', 'build', 'deploy', 'maintenance', 'deps', 'configure', 'setup', 'install', 'uninstall', 'bump', 'upgrade', 'downgrade', 'pin', 'unpin', 'sync', 'merge', 'wip', 'tmp', 'temp', 'revert', 'rollback', 'undo', 'restore', 'repair', 'resolve', 'correct', 'patch', 'hotfix', 'bugfix', 'implement', 'create', 'introduce', 'enable', 'disable', 'migrate', 'port', 'rewrite', 'restructure', 'reorganize', 'simplify', 'clarify', 'document', 'comment', 'lint', 'prettier', 'indent', 'whitespace', 'testing', 'coverage', 'unit', 'integration', 'e2e', 'performance', 'optimization']:
            # Map common words to categories
            word_mapping = {
                'update': 'chore', 'change': 'refactor', 'modify': 'refactor', 'improve': 'feature', 'add': 'feature', 'remove': 'refactor', 'delete': 'refactor', 'fix': 'fix', 'bug': 'fix', 'feature': 'feature', 'new': 'feature', 'test': 'test', 'doc': 'docs', 'format': 'style', 'style': 'style', 'chore': 'chore', 'ci': 'chore', 'build': 'chore', 'deploy': 'chore', 'maintenance': 'chore', 'deps': 'chore', 'configure': 'chore', 'setup': 'chore', 'install': 'chore', 'uninstall': 'chore', 'bump': 'chore', 'upgrade': 'chore', 'downgrade': 'chore', 'pin': 'chore', 'unpin': 'chore', 'sync': 'chore', 'merge': 'chore', 'wip': 'chore', 'tmp': 'chore', 'temp': 'chore', 'revert': 'fix', 'rollback': 'fix', 'undo': 'fix', 'restore': 'fix', 'repair': 'fix', 'resolve': 'fix', 'correct': 'fix', 'patch': 'fix', 'hotfix': 'fix', 'bugfix': 'fix', 'implement': 'feature', 'create': 'feature', 'introduce': 'feature', 'enable': 'feature', 'disable': 'fix', 'migrate': 'refactor', 'port': 'refactor', 'rewrite': 'refactor', 'restructure': 'refactor', 'reorganize': 'refactor', 'simplify': 'refactor', 'clarify': 'docs', 'document': 'docs', 'comment': 'docs', 'lint': 'style', 'prettier': 'style', 'indent': 'style', 'whitespace': 'style', 'testing': 'test', 'coverage': 'test', 'unit': 'test', 'integration': 'test', 'e2e': 'test', 'performance': 'refactor', 'optimization': 'refactor'
            }
            return word_mapping.get(word, 'other')
    
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


def classify_commits_ollama_parallel(messages: List[str], max_workers: int = 3) -> List[str]:
    """
    Classify multiple commit messages in parallel using Ollama
    
    Args:
        messages: List of commit messages to classify
        max_workers: Number of parallel threads (default: 3)
        
    Returns:
        List of categories in the same order as input messages
    """
    if not messages:
        return []
    
    # If only one message, use single classification
    if len(messages) == 1:
        return [classify_commit_ollama(messages[0])]
    
    def classify_with_index(indexed_message):
        """Helper function to classify with index to preserve order"""
        index, message = indexed_message
        try:
            return index, classify_commit_ollama(message)
        except Exception as e:
            # Fallback to simple classifier on error
            return index, classify_commit(message)
    
    # Create indexed messages to preserve order
    indexed_messages = list(enumerate(messages))
    results = [None] * len(messages)
    
    # Use ThreadPoolExecutor for parallel processing
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_index = {
            executor.submit(classify_with_index, indexed_msg): indexed_msg[0] 
            for indexed_msg in indexed_messages
        }
        
        # Collect results in original order
        for future in as_completed(future_to_index):
            try:
                index, category = future.result()
                results[index] = category
            except Exception as e:
                # Fallback for any remaining errors
                index = future_to_index[future]
                results[index] = classify_commit(messages[index])
    
    return results


def classify_commits_with_ollama_fallback_batch(messages: List[str]) -> List[str]:
    """
    Classify multiple commit messages using simple classifier first, then Ollama in parallel for 'other' results
    
    Args:
        messages: List of commit messages to classify
        
    Returns:
        List of categories in the same order as input messages
    """
    if not messages:
        return []
    
    # First pass: use simple classifier for all messages
    simple_results = [classify_commit(message) for message in messages]
    
    # Find messages that need Ollama (simple classifier returned 'other')
    ollama_needed_indices = []
    ollama_needed_messages = []
    
    for i, (message, simple_result) in enumerate(zip(messages, simple_results)):
        if simple_result == 'other':
            ollama_needed_indices.append(i)
            ollama_needed_messages.append(message)
    
    # If no messages need Ollama, return simple results
    if not ollama_needed_messages:
        return simple_results
    
    # Classify the 'other' messages in parallel with Ollama
    ollama_results = classify_commits_ollama_parallel(ollama_needed_messages, max_workers=3)
    
    # Merge results: replace 'other' results with Ollama results
    final_results = simple_results.copy()
    for i, ollama_result in zip(ollama_needed_indices, ollama_results):
        final_results[i] = ollama_result
    
    return final_results


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
        llm_response = result.get('response', '').strip().lower()  # Normalize to lowercase
        
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
            'maintenance': 'chore',
            'wip': 'chore',          # Work in progress
            'tmp': 'chore',          # Temporary
            'temp': 'chore',         # Temporary
            'bump': 'chore',         # Version bump
            'upgrade': 'chore',      # Dependency upgrade
            'downgrade': 'chore',    # Dependency downgrade
            'pin': 'chore',          # Pin dependency
            'unpin': 'chore',        # Unpin dependency
            'sync': 'chore',         # Sync
            'merge': 'chore',        # Merge
            'revert': 'fix',         # Revert
            'rollback': 'fix',       # Rollback
            'undo': 'fix',           # Undo
            'restore': 'fix',        # Restore
            'repair': 'fix',         # Repair
            'resolve': 'fix',        # Resolve
            'correct': 'fix',        # Correct
            'patch': 'fix',          # Patch
            'hotfix': 'fix',         # Hotfix
            'bugfix': 'fix',         # Bugfix
            'implement': 'feature',  # Implement
            'create': 'feature',     # Create
            'new': 'feature',        # New
            'introduce': 'feature',  # Introduce
            'enable': 'feature',     # Enable
            'disable': 'fix',        # Disable
            'configure': 'chore',    # Configure
            'setup': 'chore',        # Setup
            'install': 'chore',      # Install
            'uninstall': 'chore',    # Uninstall
            'migrate': 'refactor',   # Migrate
            'port': 'refactor',      # Port
            'rewrite': 'refactor',   # Rewrite
            'restructure': 'refactor', # Restructure
            'reorganize': 'refactor', # Reorganize
            'simplify': 'refactor',  # Simplify
            'clarify': 'docs',       # Clarify
            'document': 'docs',      # Document
            'comment': 'docs',       # Comment
            'format': 'style',       # Format
            'lint': 'style',         # Lint
            'prettier': 'style',     # Prettier
            'indent': 'style',       # Indent
            'whitespace': 'style',   # Whitespace
            'test': 'test',          # Test
            'testing': 'test',       # Testing
            'spec': 'test',          # Spec
            'specs': 'test',         # Specs
            'coverage': 'test',      # Coverage
            'unit': 'test',          # Unit
            'integration': 'test',   # Integration
            'e2e': 'test',           # End-to-end
            'performance': 'refactor', # Performance
            'optimization': 'refactor', # Optimization
        }
        
        # Check variations in both LLM response and original message
        message_lower = message.lower()
        
        # First check LLM response for variations
        for variation, category in variations.items():
            if variation in llm_response:
                return category
        
        # Then check original message for variations (fallback)
        for variation, category in variations.items():
            if variation in message_lower:
                return category
        
        # If LLM said "other" but we found variations in the message, use the variation
        # This is a fallback for when LLM fails to recognize obvious patterns
        if 'other' in llm_response:
            # Check if message contains obvious patterns that LLM missed
            if any(word in message_lower for word in ['update', 'change', 'modify', 'improve', 'add', 'remove', 'delete', 'fix', 'bug', 'feature', 'new', 'test', 'doc', 'format', 'style']):
                # Use simple classifier as final fallback
                return classify_commit(message)
        
        # If no category found in LLM response, return 'other'
        return 'other'
        
    except Exception as e:
        # If Ollama fails, use simple classifier as fallback
        return classify_commit(message)


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


def classify_commits_with_files_batch(commit_data_list: List[dict]) -> List[str]:
    """
    Classify multiple commits using both messages and files in parallel
    
    Args:
        commit_data_list: List of dicts with 'message' and 'files' keys
        
    Returns:
        List of categories in the same order as input
    """
    if not commit_data_list:
        return []
    
    results = []
    messages_for_ollama = []
    ollama_indices = []
    
    # First pass: handle file-based classification and collect messages needing Ollama
    for i, commit_data in enumerate(commit_data_list):
        message = commit_data.get('message', '')
        files = commit_data.get('files', [])
        
        if not files or not isinstance(files, list):
            # No files info, will need message classification
            simple_result = classify_commit(message)
            if simple_result == 'other':
                messages_for_ollama.append(message)
                ollama_indices.append(i)
                results.append(None)  # Placeholder
            else:
                results.append(simple_result)
            continue
        
        # File-based classification
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
            results.append('docs')
        # Si tous les fichiers sont infra/config
        elif exts and all(e in chore_exts for e in exts):
            results.append('chore')
        else:
            # Need message classification
            simple_result = classify_commit(message)
            if simple_result == 'other':
                messages_for_ollama.append(message)
                ollama_indices.append(i)
                results.append(None)  # Placeholder
            else:
                results.append(simple_result)
    
    # Second pass: classify messages needing Ollama in parallel
    if messages_for_ollama:
        ollama_results = classify_commits_ollama_parallel(messages_for_ollama, max_workers=3)
        
        # Fill in the Ollama results
        for idx, ollama_result in zip(ollama_indices, ollama_results):
            results[idx] = ollama_result
    
    return results 