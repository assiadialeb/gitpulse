import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

import requests
import re
from models import GitHubUser
from analytics.models import DeveloperGroup, DeveloperAlias, Commit
from github.models import GitHubToken
from django.contrib.auth.models import User

ORG = "hove-io"

# Récupérer le token GitHub de l'utilisateur connecté (premier utilisateur pour l'exemple)
user = User.objects.first()
try:
    github_token = GitHubToken.objects.get(user=user)
    access_token = github_token.access_token
    print(f"Token trouvé pour l'utilisateur: {user.username}")
except GitHubToken.DoesNotExist:
    print("Aucun token GitHub trouvé en base de données.")
    exit(1)

headers = {
    "Authorization": f"token {access_token}",
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "GitPulse-Org-Mapper"
}

# Vérifier les DeveloperGroup avec github_id
print("\n=== VÉRIFICATION DES DEVELOPERGROUP ===")
all_groups = list(DeveloperGroup.objects.all())
groups_with_github_id = [g for g in all_groups if g.github_id]
groups_without_github_id = [g for g in all_groups if not g.github_id]

print(f"Total DeveloperGroup: {len(all_groups)}")
print(f"DeveloperGroup avec github_id: {len(groups_with_github_id)}")
print(f"DeveloperGroup sans github_id: {len(groups_without_github_id)}")

if groups_with_github_id:
    print("\nExemples de groupes avec github_id:")
    for group in groups_with_github_id[:5]:
        print(f"  - {group.primary_name} ({group.primary_email}) - GitHub ID: {group.github_id}")

if groups_without_github_id:
    print("\nExemples de groupes sans github_id:")
    for group in groups_without_github_id[:5]:
        print(f"  - {group.primary_name} ({group.primary_email})")

# Vérifier les commits avec GitHub ID dans les emails
print("\n=== VÉRIFICATION DES COMMITS ===")
all_commits = list(Commit.objects.all())
commits_with_github_id_in_email = []
commits_without_github_id_in_email = []

# Pattern pour détecter les GitHub ID dans les emails (ex: 12345678+username@users.noreply.github.com)
github_id_pattern = r'(\d+)\+([^@]+)@users\.noreply\.github\.com'

for commit in all_commits:
    if re.search(github_id_pattern, commit.author_email):
        commits_with_github_id_in_email.append(commit)
    else:
        commits_without_github_id_in_email.append(commit)

print(f"Total commits: {len(all_commits)}")
print(f"Commits avec GitHub ID dans l'email: {len(commits_with_github_id_in_email)}")
print(f"Commits sans GitHub ID dans l'email: {len(commits_without_github_id_in_email)}")

if commits_with_github_id_in_email:
    print("\nExemples de commits avec GitHub ID dans l'email:")
    for commit in commits_with_github_id_in_email[:5]:
        match = re.search(github_id_pattern, commit.author_email)
        github_id = match.group(1) if match else "N/A"
        username = match.group(2) if match else "N/A"
        print(f"  - {commit.sha[:8]} - Author: {commit.author_name} - Email: {commit.author_email} - GitHub ID: {github_id}")

if commits_without_github_id_in_email:
    print("\nExemples de commits sans GitHub ID dans l'email:")
    for commit in commits_without_github_id_in_email[:5]:
        print(f"  - {commit.sha[:8]} - Author: {commit.author_name} - Email: {commit.author_email}")

# 1. Lister les membres de l'organisation
def get_org_members(org):
    url = f"https://api.github.com/orgs/{org}/members"
    members = []
    page = 1
    while True:
        resp = requests.get(url, headers=headers, params={"per_page": 100, "page": page})
        if resp.status_code != 200:
            print(f"Erreur lors de la récupération des membres : {resp.status_code} {resp.text}")
            break
        data = resp.json()
        if not data:
            break
        members.extend(data)
        page += 1
    return members

# 2. Pour chaque membre, récupérer le profil et emails publics
def get_user_profile(login):
    url = f"https://api.github.com/users/{login}"
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print(f"  Erreur profil {login}: {resp.status_code}")
        return None
    return resp.json()

def get_user_emails(login):
    # L'API /users/{login}/emails n'est accessible que pour l'utilisateur authentifié lui-même
    # Pour les autres, seul l'email public du profil est disponible
    profile = get_user_profile(login)
    emails = []
    if profile:
        if profile.get('email'):
            emails.append(profile['email'])
    return emails

members = get_org_members(ORG)
print(f"\nMembres trouvés dans l'organisation {ORG}: {len(members)}")

for member in members:
    login = member['login']
    print(f"\n=== {login} ===")
    profile = get_user_profile(login)
    if not profile:
        continue
    github_id = profile.get('id')
    email = profile.get('email')
    emails = get_user_emails(login)
    print(f"  GitHub ID: {github_id}")
    print(f"  Email(s): {emails}")

    # 3. Chercher/Créer le GitHubUser
    github_user = GitHubUser.objects(login=login).first()
    if not github_user:
        github_user = GitHubUser(login=login, github_id=github_id, email=email, emails=[{"email": e} for e in emails])
        github_user.save()
    else:
        # Mettre à jour les emails si besoin
        new_emails = set(emails) - set([e['email'] for e in github_user.emails])
        if new_emails:
            github_user.emails += [{"email": e} for e in new_emails]
            github_user.save()

    # 4. Trouver les DeveloperAlias correspondants
    all_emails = [github_user.email] if github_user.email else []
    all_emails += [e['email'] for e in github_user.emails if 'email' in e]
    all_emails = list(set(all_emails))
    aliases = list(DeveloperAlias.objects(email__in=all_emails))
    print("  DeveloperAlias:", [f"{a.name} ({a.email})" for a in aliases])

    # 5. Trouver les groupes associés
    groups = set(a.group for a in aliases)
    for group in groups:
        print("  DeveloperGroup:", group.primary_name, group.primary_email, group.github_id)

    # 6. Trouver les commits associés à ces alias
    for alias in aliases:
        commits = list(Commit.objects(author_email=alias.email))
        print(f"    Commits pour {alias.name} ({alias.email}):", len(commits))
        if commits:
            print("      Premier commit:", commits[0].message)