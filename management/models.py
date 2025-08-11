from django.db import models


class IntegrationConfig(models.Model):
    """Generic integration configuration supporting multiple instances per provider.

    Phase 1 scope: GitHub OAuth multi-organization.
    """
    PROVIDER_CHOICES = (
        ('github', 'GitHub'),
        ('sonarcloud', 'SonarCloud'),
    )

    provider = models.CharField(max_length=50, choices=PROVIDER_CHOICES)
    name = models.CharField(max_length=100, help_text="Admin label, e.g., 'GitHub - Org Foo'")

    # GitHub-specific fields (GitHub App, multi-organization)
    github_organization = models.CharField(
        max_length=100,
        blank=True,
        help_text="Target GitHub organization login (owner). Leave blank for default/global."
    )
    # GitHub App credentials
    app_id = models.CharField(max_length=50, blank=True, help_text="GitHub App ID")
    private_key = models.TextField(blank=True, help_text="GitHub App Private Key (PEM)")

    status = models.CharField(max_length=20, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['provider', 'github_organization', 'status']),
        ]
        verbose_name = 'Integration Configuration'
        verbose_name_plural = 'Integration Configurations'

    def __str__(self) -> str:
        provider_label = dict(self.PROVIDER_CHOICES).get(self.provider, self.provider)
        suffix = f" ({self.github_organization})" if self.github_organization else ""
        return f"{provider_label} - {self.name}{suffix}"
