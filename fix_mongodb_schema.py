#!/usr/bin/env python3
"""
Script to fix MongoDB documents that were corrupted by the reclassify script.
This removes the commit_categories field that was incorrectly added.
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

# MongoDB connection
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "gitpulse"

def fix_commit_documents():
    """Fix commit documents by removing the commit_categories field"""
    print("Connecting to MongoDB...")
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    commits_collection = db['commits']
    
    # Find documents with commit_categories field
    corrupted_docs = commits_collection.find({"commit_categories": {"$exists": True}})
    corrupted_count = commits_collection.count_documents({"commit_categories": {"$exists": True}})
    
    print(f"Found {corrupted_count} documents with commit_categories field")
    
    if corrupted_count == 0:
        print("No corrupted documents found!")
        return
    
    # Fix each document
    fixed = 0
    for doc in corrupted_docs:
        # Remove the commit_categories field
        commits_collection.update_one(
            {"_id": doc["_id"]},
            {"$unset": {"commit_categories": ""}}
        )
        fixed += 1
        
        if fixed % 100 == 0:
            print(f"Fixed {fixed}/{corrupted_count} documents...")
    
    print(f"\nFixed {fixed} documents!")
    
    # Verify fix
    remaining_corrupted = commits_collection.count_documents({"commit_categories": {"$exists": True}})
    print(f"Remaining documents with commit_categories: {remaining_corrupted}")

def show_commit_schema():
    """Show the current schema of commit documents"""
    print("Connecting to MongoDB...")
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    commits_collection = db['commits']
    
    # Get a sample document
    sample = commits_collection.find_one()
    if sample:
        print("\nSample commit document structure:")
        for key, value in sample.items():
            if key == '_id':
                print(f"  {key}: ObjectId")
            elif key == 'files_changed':
                print(f"  {key}: List of FileChange objects")
            else:
                print(f"  {key}: {type(value).__name__}")
    else:
        print("No commit documents found")

if __name__ == "__main__":
    print("=== MongoDB Schema Fix Script ===")
    
    print("\n1. Showing current schema:")
    show_commit_schema()
    
    print("\n2. Fixing corrupted documents:")
    fix_commit_documents()
    
    print("\n3. Verifying fix:")
    show_commit_schema()
    
    print("\nDone!") 