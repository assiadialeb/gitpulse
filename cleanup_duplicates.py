#!/usr/bin/env python3
"""
Script to clean up duplicates in Developer and DeveloperAlias collections
"""
import os
import sys
import django
from collections import defaultdict

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from analytics.models import Developer, DeveloperAlias
from datetime import datetime, timezone

def cleanup_developer_aliases():
    """Clean up duplicate DeveloperAlias entries"""
    print("🔍 Cleaning up DeveloperAlias duplicates...")
    
    # Find duplicates by email
    email_groups = defaultdict(list)
    for alias in DeveloperAlias.objects.all():
        email_groups[alias.email.lower()].append(alias)
    
    aliases_merged = 0
    aliases_deleted = 0
    
    for email, aliases in email_groups.items():
        if len(aliases) > 1:
            print(f"  📧 Found {len(aliases)} aliases for email: {email}")
            
            # Sort by commit_count (keep the one with most commits)
            aliases.sort(key=lambda x: x.commit_count, reverse=True)
            primary_alias = aliases[0]
            
            # Merge names from all aliases
            all_names = set()
            for alias in aliases:
                if alias.name:
                    all_names.add(alias.name)
            
            # Update primary alias with combined name
            if len(all_names) > 1:
                primary_alias.name = " | ".join(sorted(all_names))
            
            # Update commit count and dates
            total_commits = sum(alias.commit_count for alias in aliases)
            first_seen = min(alias.first_seen for alias in aliases)
            last_seen = max(alias.last_seen for alias in aliases)
            
            primary_alias.commit_count = total_commits
            primary_alias.first_seen = first_seen
            primary_alias.last_seen = last_seen
            primary_alias.save()
            
            # Delete other aliases
            for alias in aliases[1:]:
                # If this alias was linked to a developer, update the primary alias
                if alias.developer and not primary_alias.developer:
                    primary_alias.developer = alias.developer
                    primary_alias.save()
                
                alias.delete()
                aliases_deleted += 1
            
            aliases_merged += 1
            print(f"    ✅ Merged into: {primary_alias.name} ({primary_alias.email})")
    
    print(f"  📊 Results: {aliases_merged} groups merged, {aliases_deleted} aliases deleted")
    return aliases_merged, aliases_deleted

def cleanup_developers():
    """Clean up duplicate Developer entries"""
    print("🔍 Cleaning up Developer duplicates...")
    
    # Find duplicates by primary_email
    email_groups = defaultdict(list)
    for developer in Developer.objects.all():
        email_groups[developer.primary_email.lower()].append(developer)
    
    developers_merged = 0
    developers_deleted = 0
    
    for email, developers in email_groups.items():
        if len(developers) > 1:
            print(f"  📧 Found {len(developers)} developers for email: {email}")
            
            # Sort by confidence_score (keep the one with highest confidence)
            developers.sort(key=lambda x: x.confidence_score, reverse=True)
            primary_developer = developers[0]
            
            # Merge names from all developers
            all_names = set()
            for dev in developers:
                if dev.primary_name:
                    all_names.add(dev.primary_name)
            
            # Update primary developer with combined name
            if len(all_names) > 1:
                primary_developer.primary_name = " | ".join(sorted(all_names))
            
            # Update confidence score
            max_confidence = max(dev.confidence_score for dev in developers)
            primary_developer.confidence_score = max_confidence
            primary_developer.save()
            
            # Move all aliases to primary developer
            for dev in developers[1:]:
                # Move aliases to primary developer
                for alias in DeveloperAlias.objects.filter(developer=dev):
                    alias.developer = primary_developer
                    alias.save()
                
                dev.delete()
                developers_deleted += 1
            
            developers_merged += 1
            print(f"    ✅ Merged into: {primary_developer.primary_name} ({primary_developer.primary_email})")
    
    print(f"  📊 Results: {developers_merged} groups merged, {developers_deleted} developers deleted")
    return developers_merged, developers_deleted

def fix_orphan_aliases():
    """Fix aliases that are linked to non-existent developers"""
    print("🔍 Fixing orphan aliases...")
    
    orphan_count = 0
    for alias in DeveloperAlias.objects.all():
        if alias.developer and not Developer.objects.filter(id=alias.developer.id).exists():
            print(f"  🚨 Found orphan alias: {alias.name} ({alias.email})")
            alias.developer = None
            alias.save()
            orphan_count += 1
    
    print(f"  📊 Results: {orphan_count} orphan aliases fixed")
    return orphan_count

def show_statistics():
    """Show current statistics"""
    print("\n📊 Current Statistics:")
    print(f"  👥 Total Developers: {Developer.objects.count()}")
    print(f"  📧 Total Aliases: {DeveloperAlias.objects.count()}")
    print(f"  🔗 Linked Aliases: {DeveloperAlias.objects.filter(developer__ne=None).count()}")
    print(f"  🚫 Unlinked Aliases: {DeveloperAlias.objects.filter(developer=None).count()}")
    
    # Show some examples of duplicates
    print("\n🔍 Checking for potential duplicates...")
    
    # Check DeveloperAlias duplicates
    email_counts = {}
    for alias in DeveloperAlias.objects.all():
        email = alias.email.lower()
        email_counts[email] = email_counts.get(email, 0) + 1
    
    duplicate_emails = {email: count for email, count in email_counts.items() if count > 1}
    if duplicate_emails:
        print(f"  📧 Found {len(duplicate_emails)} emails with multiple aliases:")
        for email, count in list(duplicate_emails.items())[:5]:  # Show first 5
            print(f"    - {email}: {count} aliases")
    else:
        print("  ✅ No duplicate emails found in aliases")
    
    # Check Developer duplicates
    dev_email_counts = {}
    for dev in Developer.objects.all():
        email = dev.primary_email.lower()
        dev_email_counts[email] = dev_email_counts.get(email, 0) + 1
    
    duplicate_dev_emails = {email: count for email, count in dev_email_counts.items() if count > 1}
    if duplicate_dev_emails:
        print(f"  👥 Found {len(duplicate_dev_emails)} emails with multiple developers:")
        for email, count in list(duplicate_dev_emails.items())[:5]:  # Show first 5
            print(f"    - {email}: {count} developers")
    else:
        print("  ✅ No duplicate emails found in developers")

def main():
    """Main cleanup function"""
    print("🧹 Starting cleanup of Developer and DeveloperAlias duplicates...")
    print("=" * 60)
    
    # Show initial statistics
    show_statistics()
    
    print("\n" + "=" * 60)
    
    # Clean up duplicates
    aliases_merged, aliases_deleted = cleanup_developer_aliases()
    developers_merged, developers_deleted = cleanup_developers()
    orphan_count = fix_orphan_aliases()
    
    print("\n" + "=" * 60)
    print("📊 Cleanup Summary:")
    print(f"  📧 Aliases: {aliases_merged} groups merged, {aliases_deleted} deleted")
    print(f"  👥 Developers: {developers_merged} groups merged, {developers_deleted} deleted")
    print(f"  🚫 Orphan aliases fixed: {orphan_count}")
    
    print("\n" + "=" * 60)
    
    # Show final statistics
    show_statistics()
    
    print("\n✅ Cleanup completed!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n❌ Cleanup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Error during cleanup: {e}")
        sys.exit(1) 