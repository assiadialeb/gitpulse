#!/usr/bin/env python3
"""
Script de test pour analyser la qualité des commits avec Ollama
Analyse le diff entre les 2 derniers commits et évalue la qualité selon nos critères
"""

import subprocess
import json
import os
import sys
import ollama
from typing import Dict, Any, Optional

# Configuration Ollama
MODEL_NAME = "qwen2.5-coder:7b"

def get_last_two_commits() -> tuple[str, str]:
    """Récupère les 2 derniers commits du répertoire courant"""
    try:
        # Récupérer les 2 derniers commits
        result = subprocess.run(
            ['git', 'log', '--oneline', '-2'],
            capture_output=True,
            text=True,
            check=True
        )
        
        lines = result.stdout.strip().split('\n')
        if len(lines) < 2:
            print("Erreur: Pas assez de commits dans l'historique")
            sys.exit(1)
        
        # Extraire les SHAs des 2 derniers commits
        commit1_sha = lines[0].split()[0]
        commit2_sha = lines[1].split()[0]
        
        print(f"Commit 1 (le plus récent): {commit1_sha}")
        print(f"Commit 2: {commit2_sha}")
        
        return commit1_sha, commit2_sha
        
    except subprocess.CalledProcessError as e:
        print(f"Erreur lors de la récupération des commits: {e}")
        sys.exit(1)

def get_diff_between_commits(commit1: str, commit2: str) -> str:
    """Récupère le diff entre les 2 commits"""
    try:
        result = subprocess.run(
            ['git', 'diff', commit2, commit1],
            capture_output=True,
            text=True,
            check=True
        )
        
        diff_content = result.stdout
        if not diff_content.strip():
            print("Aucun changement détecté entre les commits")
            return ""
        
        return diff_content
        
    except subprocess.CalledProcessError as e:
        print(f"Erreur lors de la récupération du diff: {e}")
        sys.exit(1)

def get_commit_message(commit_sha: str) -> str:
    """Récupère le message du commit"""
    try:
        result = subprocess.run(
            ['git', 'log', '--format=%B', '-1', commit_sha],
            capture_output=True,
            text=True,
            check=True
        )
        
        return result.stdout.strip()
        
    except subprocess.CalledProcessError as e:
        print(f"Erreur lors de la récupération du message: {e}")
        return ""

def analyze_commit_with_ollama(commit_message: str, diff_content: str) -> Dict[str, Any]:
    """Analyse la qualité du commit avec Ollama"""
    
    prompt = f"""Analyze the quality of this commit according to our criteria.

Commit message:
"{commit_message}"

Diff of changes:
```
{diff_content}
```

Evaluate this commit on each of these criteria with a score from 1 to 100:

1. **Real Code Commits** - Does the commit contain real functional code?
2. **Suspicious Commits** - Are there any suspicious patterns (micro-commits, trivial changes)?
3. **Documentation Only** - Does the commit contain only documentation?
4. **Configuration Only** - Does the commit contain only configuration?
5. **Micro Commits (≤2 changes)** - Is the commit very small (≤2 changes)?
6. **Overall Score** - A global score from 1 to 100 based on the impact of this code on the application.

Reply ONLY in valid JSON format, with no text before or after:

{{
  "real_code_score": 85,
  "suspicious_score": 20,
  "documentation_only_score": 10,
  "configuration_only_score": 15,
  "micro_commit_score": 25,
  "overall_score": 50,
  "explanation": "Detailed explanation of the evaluation..."
}}"""

    try:
        # Utiliser la bibliothèque ollama
        response = ollama.generate(
            model=MODEL_NAME,
            prompt=prompt,
            options={
                "temperature": 0.3,
                "num_predict": 500
            }
        )
        
        llm_response = response['response'].strip()
        
        # Essayer de parser la réponse JSON
        try:
            # Chercher le JSON dans la réponse
            start_idx = llm_response.find('{')
            end_idx = llm_response.rfind('}') + 1
            
            if start_idx != -1 and end_idx > start_idx:
                json_str = llm_response[start_idx:end_idx]
                analysis = json.loads(json_str)
                return analysis
            else:
                # Si pas de JSON trouvé, créer une réponse par défaut
                return {
                    "real_code_score": 50,
                    "suspicious_score": 50,
                    "documentation_only_score": 50,
                    "configuration_only_score": 50,
                    "micro_commit_score": 50,
                    "overall_score": 50,
                    "explanation": "Impossible de parser la réponse d'Ollama",
                    "raw_response": llm_response
                }
                
        except json.JSONDecodeError:
            return {
                "real_code_score": 50,
                "suspicious_score": 50,
                "documentation_only_score": 50,
                "configuration_only_score": 50,
                "micro_commit_score": 50,
                "overall_score": 50,
                "explanation": "Erreur de parsing JSON",
                "raw_response": llm_response
            }
        
    except Exception as e:
        print(f"Erreur lors de l'appel à Ollama: {e}")
        return {
            "real_code_score": 0,
            "suspicious_score": 0,
            "documentation_only_score": 0,
            "configuration_only_score": 0,
            "micro_commit_score": 0,
            "overall_score": 0,
            "explanation": f"Erreur de connexion à Ollama: {e}"
        }

def main():
    """Fonction principale"""
    print("=== Analyse de qualité des commits avec Ollama ===\n")
    
    # Vérifier que nous sommes dans un repo git
    try:
        subprocess.run(['git', 'status'], capture_output=True, check=True)
    except subprocess.CalledProcessError:
        print("Erreur: Ce script doit être exécuté dans un répertoire git")
        sys.exit(1)
    
    # Récupérer les 2 derniers commits
    print("1. Récupération des 2 derniers commits...")
    commit1_sha, commit2_sha = get_last_two_commits()
    
    # Récupérer le message du commit le plus récent
    print("\n2. Récupération du message du commit...")
    commit_message = get_commit_message(commit1_sha)
    print(f"Message: {commit_message}")
    
    # Récupérer le diff
    print("\n3. Récupération du diff...")
    diff_content = get_diff_between_commits(commit1_sha, commit2_sha)
    
    if not diff_content:
        print("Aucun diff trouvé. Le commit pourrait être vide ou identique au précédent.")
        return
    
    print(f"Diff trouvé ({len(diff_content)} caractères)")
    
    # Analyser avec Ollama
    print(f"\n4. Analyse avec Ollama (modèle: {MODEL_NAME})...")
    analysis = analyze_commit_with_ollama(commit_message, diff_content)
    
    # Afficher les résultats
    print("\n=== RÉSULTATS DE L'ANALYSE ===")
    print(f"Commit SHA: {commit1_sha}")
    print(f"Message: {commit_message}")
    print()
    
    print("Notes de qualité (1-100):")
    print(f"  • Real Code Commits: {analysis.get('real_code_score', 0)}/100")
    print(f"  • Suspicious Commits: {analysis.get('suspicious_score', 0)}/100")
    print(f"  • Documentation Only: {analysis.get('documentation_only_score', 0)}/100")
    print(f"  • Configuration Only: {analysis.get('configuration_only_score', 0)}/100")
    print(f"  • Micro Commits (≤2): {analysis.get('micro_commit_score', 0)}/100")
    print(f"  • Overall Score: {analysis.get('overall_score', 0)}/100")
    
    print(f"\nExplication: {analysis.get('explanation', 'Aucune explication disponible')}")
    
    if 'raw_response' in analysis:
        print(f"\nRéponse brute d'Ollama:")
        print(analysis['raw_response'])

if __name__ == "__main__":
    main() 