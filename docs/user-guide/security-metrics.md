# Security Metrics Guide

This guide explains GitPulse's security analytics features, with a focus on the Security Health Score (SHS) and CodeQL integration.

## Security Health Score (SHS)

The Security Health Score is GitPulse's flagship security metric, providing a comprehensive view of your codebase's security posture.

### Understanding SHS

The SHS is a sophisticated metric that goes beyond simple vulnerability counting. It provides:

- **Normalized Risk Assessment**: Compares security across repositories of different sizes
- **Severity Weighting**: Critical vulnerabilities have more impact than low-severity ones
- **Trend Analysis**: Tracks security improvements over time
- **Actionable Insights**: Helps prioritize security efforts

### How SHS Works

#### 1. Vulnerability Analysis
GitPulse analyzes CodeQL vulnerability data from your repositories:
- **Critical Vulnerabilities**: Highest security risk (weight: 1.0)
- **High Vulnerabilities**: Significant security risk (weight: 0.7)
- **Medium Vulnerabilities**: Moderate security risk (weight: 0.4)
- **Low Vulnerabilities**: Minimal security risk (weight: 0.1)

#### 2. Size Normalization
The score is normalized by repository size (KLOC - Kilo Lines of Code):
- Larger repositories naturally have more potential vulnerabilities
- Normalization enables fair comparison across different-sized codebases
- Formula: `weighted_vulnerabilities ÷ KLOC`

#### 3. Score Calculation
GitPulse applies a saturation function to create an intuitive 0-100 scale:
- **Higher scores** = Better security posture
- **Lower scores** = Higher security risk
- **100/100** = Perfect security (no vulnerabilities)

### Interpreting Your SHS

#### Score Ranges

| Score | Security Level | Description | Action Required |
|-------|----------------|-------------|-----------------|
| 90-100 | Excellent | Very low security risk | Maintain current practices |
| 80-89 | Good | Low security risk | Monitor for trends |
| 60-79 | Fair | Moderate security risk | Plan security improvements |
| 40-59 | Poor | High security risk | Immediate attention needed |
| 0-39 | Critical | Very high security risk | Urgent remediation required |

#### Trend Indicators

The SHS includes trend information showing security evolution:

- **🟢 Positive Trend** (+2.1): Security is improving
- **🔴 Negative Trend** (-1.5): Security is deteriorating
- **⚪ Stable** (0.0): Security posture is unchanged

### Using SHS in Practice

#### For Development Teams

1. **Set Security Goals**: Aim for SHS > 80 for production code
2. **Track Improvements**: Monitor SHS trends over time
3. **Prioritize Fixes**: Focus on critical and high-severity vulnerabilities
4. **Code Reviews**: Use SHS as a quality gate for new code

#### For Management

1. **Portfolio Overview**: Compare SHS across all repositories
2. **Resource Allocation**: Direct security efforts to low-scoring repositories
3. **Progress Tracking**: Monitor security improvement initiatives
4. **Risk Assessment**: Identify high-risk codebases

#### For Security Teams

1. **Vulnerability Prioritization**: Focus on repositories with low SHS
2. **Trend Analysis**: Identify improving or deteriorating security posture
3. **Compliance Monitoring**: Track security metrics for reporting
4. **Incident Response**: Use SHS to assess impact of new vulnerabilities

## CodeQL Integration

### What is CodeQL?

CodeQL is GitHub's semantic code analysis engine that finds vulnerabilities and errors in your code. GitPulse integrates with CodeQL to provide:

- **Automated Vulnerability Detection**: Finds security issues in your code
- **Severity Classification**: Categorizes vulnerabilities by risk level
- **Detailed Analysis**: Provides context and remediation guidance
- **Continuous Monitoring**: Tracks vulnerabilities over time

### Setting Up CodeQL

#### 1. Enable CodeQL in Your Repository

1. Go to your repository on GitHub
2. Navigate to **Settings** → **Security & analysis**
3. Enable **Code scanning** with CodeQL
4. Commit the generated workflow file

#### 2. Configure GitPulse Integration

1. Ensure your GitHub token has `security_events` permission
2. Index your repository in GitPulse
3. CodeQL data will be automatically imported

### Understanding CodeQL Data

#### Vulnerability Types

CodeQL detects various security issues:

- **SQL Injection**: Database query vulnerabilities
- **Cross-Site Scripting (XSS)**: Web application vulnerabilities
- **Path Traversal**: File access vulnerabilities
- **Insecure Deserialization**: Object injection vulnerabilities
- **And many more...**

#### Severity Levels

- **Critical**: Immediate security risk, requires urgent attention
- **High**: Significant security risk, should be addressed quickly
- **Medium**: Moderate security risk, plan for remediation
- **Low**: Minimal security risk, consider for future updates

## Security Dashboard

### Repository Security View

Each repository displays security metrics:

- **Security Health Score**: Primary security metric
- **Vulnerability Count**: Total open vulnerabilities
- **Severity Breakdown**: Distribution by risk level
- **Trend Information**: Security improvement/deterioration

### Detailed Analysis

Click on the Security Health Score card to see:

- **Vulnerability Details**: List of all detected issues
- **Severity Distribution**: Breakdown by risk level
- **Historical Trends**: SHS evolution over time
- **Remediation Guidance**: Links to GitHub security advisories

## Best Practices

### Improving Your SHS

1. **Fix Critical Vulnerabilities First**: Address the highest-risk issues
2. **Regular Code Reviews**: Catch security issues early
3. **Automated Testing**: Include security tests in CI/CD
4. **Dependency Management**: Keep dependencies updated
5. **Security Training**: Educate team on secure coding practices

### Monitoring Security Trends

1. **Weekly Reviews**: Check SHS trends regularly
2. **Monthly Reports**: Track security improvement progress
3. **Quarterly Assessments**: Evaluate overall security posture
4. **Annual Planning**: Set security goals for the year

### Team Collaboration

1. **Security Champions**: Designate team members for security focus
2. **Knowledge Sharing**: Share security best practices
3. **Code Reviews**: Include security in review processes
4. **Training Programs**: Regular security awareness training

## Troubleshooting

### Common Issues

#### SHS Not Available
- **Cause**: CodeQL not enabled or no analysis data
- **Solution**: Enable CodeQL in repository settings

#### Missing Vulnerability Data
- **Cause**: GitHub token lacks security permissions
- **Solution**: Update token with `security_events` scope

#### Incorrect Scores
- **Cause**: Outdated KLOC or vulnerability data
- **Solution**: Re-run repository indexing

### Getting Help

- **Documentation**: Check technical documentation
- **GitHub Issues**: Report bugs or feature requests
- **Community**: Join discussions for help and tips

## Advanced Features

### Custom Scoring

Future versions will support:
- Customizable vulnerability weights
- Repository-specific scoring rules
- Industry benchmark comparisons

### Integration Options

- **CI/CD Integration**: Automated security gates
- **Alert Systems**: Security threshold notifications
- **Reporting Tools**: Export security metrics
- **API Access**: Programmatic access to security data

## 📚 Related Documentation

- **[Analytics Guide](analytics.md)** - Comprehensive analytics overview
- **[GitHub Setup](github-setup.md)** - Configure GitHub integration
- **[Technical SHS Documentation](../technical/security-health-score.md)** - Technical implementation details 