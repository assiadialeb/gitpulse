#!/usr/bin/env python3
"""
Explore suspicious commits in detail
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from analytics.models import Commit
from pymongo import MongoClient

def explore_suspicious_commits():
    """Explore suspicious commits in detail"""
    
    # Connect to MongoDB
    client = MongoClient('localhost', 27017)
    db = client['gitpulse']
    quality_collection = db['developer_quality_metrics']
    
    # Get commits with suspicious patterns
    suspicious_commits = quality_collection.find({
        'suspicious_patterns': {'$ne': []},
        'application_id': 12
    }).sort('commit_date', -1).limit(50)
    
    print("Exploring suspicious commits...")
    print("=" * 80)
    
    for commit in suspicious_commits:
        print(f"\nCommit: {commit['commit_sha'][:8]}")
        print(f"Developer: {commit['developer_name']} ({commit['developer_email']})")
        print(f"Date: {commit['commit_date']}")
        print(f"Message: {commit.get('message', 'N/A')}")
        print(f"Type: {commit['commit_type']}")
        print(f"Changes: +{commit['additions']} -{commit['deletions']} ({commit['total_changes']} total)")
        print(f"Files: {commit['files_count']}")
        print(f"Patterns: {commit['suspicious_patterns']}")
        print(f"Quality scores: Code={commit['code_quality_score']}, Impact={commit['impact_score']}, Complexity={commit['complexity_score']}")
        print(f"File types: Code={commit['code_files']}, Test={commit['test_files']}, Doc={commit['doc_files']}, Config={commit['config_files']}")
        print("-" * 40)

def explore_developer_commits(developer_email, application_id=None):
    """Explore all commits from a specific developer"""
    
    # Connect to MongoDB
    client = MongoClient('localhost', 27017)
    db = client['gitpulse']
    quality_collection = db['developer_quality_metrics']
    
    # Build query
    query = {'developer_email': developer_email}
    if application_id:
        query['application_id'] = application_id
    
    # Get all commits from this developer
    commits = quality_collection.find(query).sort('commit_date', -1)
    
    print(f"\nAll commits from {developer_email}:")
    print("=" * 80)
    
    for commit in commits:
        print(f"\n{commit['commit_date'].strftime('%Y-%m-%d %H:%M')} - {commit['commit_sha'][:8]}")
        print(f"Message: {commit.get('message', 'N/A')}")
        print(f"Type: {commit['commit_type']}")
        print(f"Changes: +{commit['additions']} -{commit['deletions']}")
        print(f"Files: {commit['files_count']} (Code:{commit['code_files']}, Test:{commit['test_files']}, Doc:{commit['doc_files']}, Config:{commit['config_files']})")
        print(f"Patterns: {commit['suspicious_patterns']}")
        print("-" * 30)

def main():
    """Main function"""
    
    print("1. Explore suspicious commits")
    print("2. Explore specific developer")
    choice = input("Choose option (1 or 2): ")
    
    if choice == "1":
        explore_suspicious_commits()
    elif choice == "2":
        email = input("Enter developer email: ")
        explore_developer_commits(email)
    else:
        print("Invalid choice")

if __name__ == "__main__":
    main() 