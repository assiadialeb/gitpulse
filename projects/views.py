from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from .models import Project
from repositories.models import Repository


@login_required
def project_list(request):
    """List all projects"""
    projects = Project.objects.all().order_by('name')
    
    context = {
        'projects': projects,
    }
    return render(request, 'projects/list.html', context)


@login_required
def project_detail(request, project_id):
    """Show project details with aggregated stats"""
    project = get_object_or_404(Project, id=project_id)
    
    # Get all repositories in this project
    repositories = project.repositories.all()
    
    # Calculate aggregated stats
    total_commits = project.get_total_commits()
    total_developers = project.get_total_developers()
    total_repositories = project.get_total_repositories()
    
    context = {
        'project': project,
        'repositories': repositories,
        'total_commits': total_commits,
        'total_developers': total_developers,
        'total_repositories': total_repositories,
    }
    return render(request, 'projects/detail.html', context)


@login_required
def project_create(request):
    """Create a new project"""
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        repository_ids = request.POST.getlist('repositories')
        
        if name:
            project = Project.objects.create(
                name=name,
                description=description
            )
            
            # Add selected repositories
            if repository_ids:
                repositories = Repository.objects.filter(id__in=repository_ids)
                project.repositories.set(repositories)
            
            messages.success(request, f'Project "{name}" created successfully.')
            return redirect('projects:detail', project_id=project.id)
        else:
            messages.error(request, 'Project name is required.')
    
    # Get available repositories
    repositories = Repository.objects.all().order_by('name')
    
    context = {
        'repositories': repositories,
    }
    return render(request, 'projects/create.html', context)


@login_required
def project_edit(request, project_id):
    """Edit an existing project"""
    project = get_object_or_404(Project, id=project_id)
    
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        repository_ids = request.POST.getlist('repositories')
        
        if name:
            project.name = name
            project.description = description
            project.save()
            
            # Update repositories
            if repository_ids:
                repositories = Repository.objects.filter(id__in=repository_ids)
                project.repositories.set(repositories)
            else:
                project.repositories.clear()
            
            messages.success(request, f'Project "{name}" updated successfully.')
            return redirect('projects:detail', project_id=project.id)
        else:
            messages.error(request, 'Project name is required.')
    
    # Get available repositories
    repositories = Repository.objects.all().order_by('name')
    
    context = {
        'project': project,
        'repositories': repositories,
    }
    return render(request, 'projects/edit.html', context)


@login_required
def project_delete(request, project_id):
    """Delete a project"""
    project = get_object_or_404(Project, id=project_id)
    
    if request.method == 'POST':
        name = project.name
        project.delete()
        messages.success(request, f'Project "{name}" deleted successfully.')
        return redirect('projects:list')
    
    context = {
        'project': project,
    }
    return render(request, 'projects/delete.html', context)
