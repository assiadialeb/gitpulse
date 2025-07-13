#!/usr/bin/env python3
"""
Delete all commits from MongoDB
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from analytics.models import Commit

def delete_all_commits():
    print("Deleting all commits from MongoDB...")
    deleted = Commit.objects.delete()
    print(f"Done. Deleted {deleted} commits.")

if __name__ == "__main__":
    delete_all_commits() 