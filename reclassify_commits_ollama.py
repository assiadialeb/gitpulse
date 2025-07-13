#!/usr/bin/env python3
"""
Standalone script to reclassify commits using Ollama with gemma3:1b model.
Requires: pip install requests
"""

import os
import sys
import django
from pathlib import Path
import requests
import json
import time

# Setup Django
sys.path.append(str(Path(__file__).parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from pymongo import MongoClient
import re
from typing import List, Dict, Optional

# MongoDB connection
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "gitpulse"

# Ollama configuration
OLLAMA_URL = "http://localhost:11434"
MODEL_NAME = "gemma3:1b"

# Simple fallback patterns (only used if LLM fails)
COMMIT_PATTERNS = {
    'fix': [r'\bfix\b', r'\bbug\b', r'\berror\b'],
    'feature': [r'\bfeature\b', r'\badd\b', r'\bnew\b'],
    'docs': [r'\bdoc\b', r'\breadme\b'],
    'refactor': [r'\brefactor\b', r'\bcleanup\b'],
    'test': [r'\btest\b'],
    'style': [r'\blint\b', r'\bformat\b'],
    'perf': [r'\bperf\b', r'\bperformance\b'],
    'ci': [r'\bci\b', r'\bdeploy\b'],
    'chore': [r'\bchore\b', r'\bupdate\b']
}

def classify_commit_simple(message: str) -> str:
    """Simple pattern-based classification with better pattern matching"""
    message_lower = message.lower()
    
    # Handle common abbreviations and variations first
    variations = {
        'refacto': 'refactor',
        'refact': 'refactor', 
        'refac': 'refactor',
        'feat': 'feature',
        'func': 'feature',
        'bugfix': 'fix',
        'hotfix': 'fix',
        'patch': 'fix',
        'doc': 'docs',
        'readme': 'docs',
        'format': 'style',
        'lint': 'style',
        'perf': 'perf',
        'ci': 'ci',
        'cd': 'ci',
        'chore': 'chore'
    }
    
    # Check for variations first
    for variation, category in variations.items():
        if variation in message_lower:
            return category
    
    # Then check patterns
    for commit_type, patterns in COMMIT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, message_lower):
                return commit_type
    
    return 'other'

def classify_commit_ollama(message: str, debug_mode=False) -> str:
    """LLM-based classification using Ollama with gemma3:1b"""
    
    # Pre-process message to handle common variations
    processed_message = message.lower()
    
    # Handle common abbreviations and variations
    variations = {
        'refacto': 'refactor',
        'refact': 'refactor', 
        'refac': 'refactor',
        'feat': 'feature',
        'func': 'feature',
        'funcionality': 'feature',
        'bugfix': 'fix',
        'hotfix': 'fix',
        'patch': 'fix',
        'doc': 'docs',
        'documentation': 'docs',
        'readme': 'docs',
        'test': 'test',
        'testing': 'test',
        'spec': 'test',
        'unit': 'test',
        'format': 'style',
        'lint': 'style',
        'prettier': 'style',
        'perf': 'perf',
        'performance': 'perf',
        'optimize': 'perf',
        'ci': 'ci',
        'cd': 'ci',
        'deploy': 'ci',
        'build': 'ci',
        'kubernetes': 'ci',
        'docker': 'ci',
        'pipeline': 'ci',
        'workflow': 'ci',
        'chore': 'chore',
        'maintenance': 'chore',
        'update': 'chore'
    }
    
    # Replace variations in the message
    for variation, standard in variations.items():
        if variation in processed_message:
            processed_message = processed_message.replace(variation, standard)
    
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
        
        # Debug: show what the LLM actually responded
        if debug_mode:
            print(f"Ollama Response: '{llm_response}'")
            print(f"Response length: {len(llm_response)}")
            print(f"Contains 'test': {'test' in llm_response}")
            print(f"Contains 'other': {'other' in llm_response}")
        
        # Extract the category from response - ONLY use LLM response
        for category in ['fix', 'feature', 'docs', 'refactor', 'test', 'style', 'perf', 'ci', 'chore', 'other']:
            if category in llm_response:
                if debug_mode:
                    print(f"Found category '{category}' in response")
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
            'optimize': 'perf',
            'speed': 'perf',
            'fast': 'perf',
            'slow': 'perf'
        }
        
        for variation, category in variations.items():
            if variation in llm_response.lower():
                if debug_mode:
                    print(f"Found variation '{variation}' -> '{category}' in response")
                return category
        
        # If no category found in LLM response, return 'other'
        if debug_mode:
            print("No category found in LLM response, returning 'other'")
        return 'other'
    except Exception as e:
        print(f"Ollama classification failed: {e}")
        return 'other'  # Return 'other' if Ollama fails

def update_commit_document(commit_doc: Dict, new_type: str) -> Dict:
    """Update commit document with new classification"""
    # Only update the commit_type field to match the MongoDB schema
    commit_doc['commit_type'] = new_type
    
    # Remove any commit_categories field if it exists (it's not in the schema)
    if 'commit_categories' in commit_doc:
        del commit_doc['commit_categories']
    
    return commit_doc

def check_ollama_connection():
    """Check if Ollama is running and the model is available"""
    try:
        # Check if Ollama is running
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        response.raise_for_status()
        
        models = response.json().get('models', [])
        model_names = [model['name'] for model in models]
        
        if MODEL_NAME in model_names:
            print(f"✅ Ollama is running and {MODEL_NAME} is available")
            return True
        else:
            print(f"❌ Model {MODEL_NAME} not found in Ollama")
            print(f"Available models: {model_names}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to Ollama at {OLLAMA_URL}")
        print("Make sure Ollama is running: ollama serve")
        return False
    except Exception as e:
        print(f"❌ Error checking Ollama: {e}")
        return False

def main():
    """Main function to reclassify commits"""
    # Debug mode - set to True to see detailed output
    DEBUG_MODE = True  # Temporarily enable to analyze responses
    
    print("Connecting to MongoDB...")
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    commits_collection = db['commits']
    
    print("Checking Ollama connection...")
    if not check_ollama_connection():
        print("Falling back to pattern-based classification...")
        use_ollama = False
    else:
        use_ollama = True
        print("Ollama connection successful!")
    
    # Get only commits with type 'other'
    total_commits = commits_collection.count_documents({'commit_type': 'other'})
    print(f"Found {total_commits} commits with type 'other' to process")
    
    if total_commits == 0:
        print("No commits with type 'other' found in database")
        return
    
    # Process only commits with type 'other'
    processed = 0
    updated = 0
    
    for commit_doc in commits_collection.find({'commit_type': 'other'}):
        processed += 1
        
        if processed % 100 == 0:
            print(f"Processed {processed}/{total_commits} commits...")
        
        message = commit_doc.get('message', '')
        if not message:
            continue
        
        # Get current classification
        current_type = commit_doc.get('commit_type', 'none')
        
        # Classify commit - ONLY use Ollama, no fallback
        if use_ollama:
            new_type = classify_commit_ollama(message, debug_mode=DEBUG_MODE)
        else:
            print("❌ Ollama not available, skipping commit")
            continue
        
        # Debug output for commits that remain 'other' after Ollama processing
        if DEBUG_MODE and new_type == 'other':
            print(f"\n--- Still OTHER Commit {processed} ---")
            print(f"Message: {message}")
            print(f"Current: {current_type}")
            print(f"New: {new_type}")
            print("Ollama was used but still returned 'other'")
            print("-" * 50)
        
        # Debug output for all processed commits (when DEBUG_MODE is True)
        if DEBUG_MODE:
            print(f"\n--- Processing 'other' Commit {processed} ---")
            print(f"Message: {message}")
            print(f"Current: {current_type}")
            print(f"New: {new_type}")
            print("Ollama was used to reclassify")
            # Get the raw Ollama response for this commit
            if use_ollama:
                try:
                    payload = {
                        "model": MODEL_NAME,
                        "prompt": f"""Classify this git commit message:

"{message}"

Categories: test, fix, feature, docs, refactor, style, perf, ci, chore, other

Answer with only one word:""",
                        "stream": False,
                        "options": {
                            "temperature": 0.3,
                            "num_predict": 10
                        }
                    }
                    
                    response = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=30)
                    result = response.json()
                    raw_response = result.get('response', '').strip()
                    print(f"Raw Ollama Response: '{raw_response}'")
                except Exception as e:
                    print(f"Failed to get raw response: {e}")
            print("-" * 50)
        
        # Update document
        updated_doc = update_commit_document(commit_doc, new_type)
        
        # Save back to database
        commits_collection.replace_one({'_id': commit_doc['_id']}, updated_doc)
        updated += 1
    
    print(f"\nProcessing complete!")
    print(f"Total 'other' commits processed: {processed}")
    print(f"Commits updated: {updated}")
    
    # Show distribution of all commits
    print("\nOverall commit type distribution:")
    pipeline = [
        {"$group": {"_id": "$commit_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    
    for result in commits_collection.aggregate(pipeline):
        print(f"  {result['_id']}: {result['count']}")
    
    # Show how many 'other' commits remain
    remaining_other = commits_collection.count_documents({'commit_type': 'other'})
    print(f"\nRemaining 'other' commits: {remaining_other}")

if __name__ == "__main__":
    main() 