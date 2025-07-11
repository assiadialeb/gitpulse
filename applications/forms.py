from django import forms
from .models import Application, ApplicationRepository


class ApplicationForm(forms.ModelForm):
    """Form for creating and editing applications"""
    
    class Meta:
        model = Application
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'input input-bordered w-full rounded-xl border-gray-200 focus:border-primary-green focus:ring-2 focus:ring-primary-green/20 transition-all duration-300',
                'placeholder': 'Enter application name'
            }),
            'description': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full rounded-xl border-gray-200 focus:border-primary-blue focus:ring-2 focus:ring-primary-blue/20 transition-all duration-300',
                'rows': 4,
                'placeholder': 'Enter a short description of your application'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].label = 'Application Name'
        self.fields['description'].label = 'Description'


class RepositorySelectionForm(forms.Form):
    """Form for selecting GitHub repositories to add to an application"""
    search_query = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input input-bordered w-full rounded-xl border-gray-200 focus:border-primary-green focus:ring-2 focus:ring-primary-green/20 transition-all duration-300',
            'placeholder': 'Search repositories...'
        }),
        label="Search Repositories"
    )
    repositories = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'checkbox checkbox-primary'
        }),
        required=False,
        label="Select Repositories"
    )
    
    def __init__(self, *args, **kwargs):
        github_repos = kwargs.pop('github_repos', [])
        existing_repos = kwargs.pop('existing_repos', [])
        search_query = kwargs.pop('search_query', '')
        super().__init__(*args, **kwargs)
        
        # Create choices from GitHub repos, excluding already added ones and filtering by search
        print(f"DEBUG FORM INIT:")
        print(f"  - github_repos count: {len(github_repos)}")
        print(f"  - existing_repos count: {len(existing_repos)}")
        print(f"  - search_query: '{search_query}'")
        print(f"  - existing_repos list: {existing_repos}")
        
        choices = []
        filtered_out_by_existing = 0
        filtered_out_by_search = 0
        added_to_choices = 0
        
        for i, repo in enumerate(github_repos):
            repo_full_name = repo.get('full_name', '')
            description = repo.get('description', '')
            
            print(f"  Processing repo {i+1}: {repo_full_name}")
            
            # Skip if already added
            if repo_full_name in existing_repos:
                print(f"    -> SKIPPED (already added)")
                filtered_out_by_existing += 1
                continue
                
            # Filter by search query if provided
            if search_query:
                search_lower = search_query.lower()
                if (search_lower not in repo_full_name.lower() and 
                    search_lower not in (description or '').lower()):
                    print(f"    -> SKIPPED (search filter)")
                    filtered_out_by_search += 1
                    continue
            
            if description is None:
                description = 'No description'
            else:
                description = description[:100]
            
            choices.append((
                repo_full_name,
                f"{repo_full_name} - {description}"
            ))
            added_to_choices += 1
            print(f"    -> ADDED to choices")
        
        print(f"DEBUG FORM RESULT:")
        print(f"  - Total repos processed: {len(github_repos)}")
        print(f"  - Filtered out by existing: {filtered_out_by_existing}")
        print(f"  - Filtered out by search: {filtered_out_by_search}")
        print(f"  - Added to choices: {added_to_choices}")
        print(f"  - Final choices count: {len(choices)}")
        if choices:
            print(f"  - First 3 choices: {choices[:3]}")
        
        self.fields['repositories'].choices = choices 