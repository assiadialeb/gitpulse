#!/usr/bin/env python3
"""
Standalone script to reclassify commits using Phi-2 model.
Requires: pip install transformers torch
"""

import os
import sys
import django
from pathlib import Path

# Setup Django
sys.path.append(str(Path(__file__).parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from pymongo import MongoClient
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
import re
import json
from typing import List, Dict, Optional

# MongoDB connection
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "gitpulse"

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

def classify_commit_llm(message: str, model, tokenizer, debug_mode=False) -> str:
    """LLM-based classification using Phi-3 with transformers"""
    
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
        # Tokenize and generate response using transformers
        inputs = tokenizer(prompt, return_tensors="pt", max_length=512, truncation=True)
        
        # Move inputs to CPU to avoid MPS issues
        inputs = {k: v.to("cpu") for k, v in inputs.items()}
        
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=20,
                temperature=0.3,
                do_sample=True,
                pad_token_id=tokenizer.eos_token_id
            )
        
        response = tokenizer.decode(outputs[0], skip_special_tokens=True)
        
        # Debug: show what the LLM actually responded
        if debug_mode:
            print(f"Full LLM Response: '{response}'")
            print(f"Response length: {len(response)}")
        
        # Extract the category from response - look for categories in the response
        response_lower = response.lower()
        
        # Try to find the last occurrence of a category (most likely the actual answer)
        last_category = None
        for category in ['fix', 'feature', 'docs', 'refactor', 'test', 'style', 'perf', 'ci', 'chore', 'other']:
            if category in response_lower:
                last_category = category
                if debug_mode:
                    print(f"Found category '{category}' in response")
        
        if last_category:
            return last_category
        
        # If no category found, try to be more flexible
        if 'test' in message.lower() or 'testing' in message.lower():
            return 'test'
        if 'fix' in message.lower() or 'bug' in message.lower():
            return 'fix'
        if 'add' in message.lower() or 'new' in message.lower():
            return 'feature'
        
        return 'other'
    except Exception as e:
        print(f"LLM classification failed: {e}")
        return classify_commit_simple(message)

def update_commit_document(commit_doc: Dict, new_type: str) -> Dict:
    """Update commit document with new classification"""
    # Only update the commit_type field to match the MongoDB schema
    commit_doc['commit_type'] = new_type
    
    # Remove any commit_categories field if it exists (it's not in the schema)
    if 'commit_categories' in commit_doc:
        del commit_doc['commit_categories']
    
    return commit_doc

def main():
    """Main function to reclassify commits"""
    # Debug mode - set to True to see detailed output
    DEBUG_MODE = True  # Temporarily enable to analyze "other" commits
    
    print("Connecting to MongoDB...")
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    commits_collection = db['commits']
    
    print("Loading Phi-3 model with transformers...")
    try:
        # Load model and tokenizer from HuggingFace
        model_id = "microsoft/phi-2"
        
        print(f"Loading tokenizer for {model_id}...")
        tokenizer = AutoTokenizer.from_pretrained(model_id)
        
        print(f"Loading model {model_id}...")
        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            torch_dtype=torch.float16,  # Use half precision for memory efficiency
            device_map="auto"  # Automatically handle device placement
        )
        
        # Force CPU usage to avoid MPS issues
        model = model.to("cpu")
        
        use_llm = True
        print("Phi-3 model loaded successfully!")
    except Exception as e:
        print(f"Failed to load Phi-3 model: {e}")
        print("Error details:", str(e))
        print("Falling back to pattern-based classification...")
        use_llm = False
        model = None
        tokenizer = None
    
    # Get all commits
    total_commits = commits_collection.count_documents({})
    print(f"Found {total_commits} commits to process")
    
    if total_commits == 0:
        print("No commits found in database")
        return
    
    # Process commits
    processed = 0
    updated = 0
    
    for commit_doc in commits_collection.find({}):
        processed += 1
        
        if processed % 100 == 0:
            print(f"Processed {processed}/{total_commits} commits...")
        
        message = commit_doc.get('message', '')
        if not message:
            continue
        
        # Get current classification
        current_type = commit_doc.get('commit_type', 'none')
        
        # Classify commit
        if use_llm and model and tokenizer:
            new_type = classify_commit_llm(message, model, tokenizer, debug_mode=DEBUG_MODE)
        else:
            new_type = classify_commit_simple(message)
        
        # Debug output (only if DEBUG_MODE is True)
        if DEBUG_MODE and new_type == 'other':
            print(f"\n--- OTHER Commit {processed} ---")
            print(f"Message: {message}")
            print(f"Current: {current_type}")
            print(f"New: {new_type}")
            if use_llm and model and tokenizer:
                print("LLM was used but failed to classify correctly")
            else:
                print("Using pattern-based classification")
            print("-" * 50)
        
        # Update document
        updated_doc = update_commit_document(commit_doc, new_type)
        
        # Save back to database
        commits_collection.replace_one({'_id': commit_doc['_id']}, updated_doc)
        updated += 1
    
    print(f"\nProcessing complete!")
    print(f"Total commits processed: {processed}")
    print(f"Commits updated: {updated}")
    
    # Show distribution
    print("\nCommit type distribution:")
    pipeline = [
        {"$group": {"_id": "$commit_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    
    for result in commits_collection.aggregate(pipeline):
        print(f"  {result['_id']}: {result['count']}")

if __name__ == "__main__":
    main() 