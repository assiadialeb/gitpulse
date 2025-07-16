import sys
from analytics.github_service import GitHubService
from github.models import GitHubToken

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python scripts/debug_github_pr_api.py <repo_full_name> <commit_sha>")
        sys.exit(1)
    repo_full_name = sys.argv[1]
    commit_sha = sys.argv[2]

    # Récupère le token du premier utilisateur GitHub trouvé
    token_obj = GitHubToken.objects.first()
    if not token_obj:
        print("Aucun token GitHub trouvé en base.")
        sys.exit(1)
    service = GitHubService(token_obj.access_token)

    pr_url = f"https://api.github.com/repos/{repo_full_name}/commits/{commit_sha}/pulls"
    try:
        prs, _ = service._make_request(pr_url, params={"per_page": 5})
        print(f"Réponse API pour {repo_full_name} {commit_sha} :")
        print(prs)
    except Exception as e:
        print(f"Erreur lors de l'appel à l'API GitHub : {e}") 