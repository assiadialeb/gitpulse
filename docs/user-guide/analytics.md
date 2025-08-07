# Analytics Guide

This guide explains how to understand and use the analytics features in GitPulse, including repository analysis, developer metrics, and security health scoring.

## Repository Analysis

GitPulse provides comprehensive analytics for your repositories, helping you understand code quality, development patterns, and security posture.

### Security Health Score (SHS)

The **Security Health Score (SHS)** is a sophisticated metric that evaluates the security posture of your codebase by analyzing CodeQL vulnerability data and normalizing it against repository size.

#### What is SHS in the Industry?

Security Health Score is a concept widely used in the software industry to provide a standardized way of measuring and communicating security risk. Unlike simple vulnerability counts, SHS considers:

- **Vulnerability Severity**: Critical vulnerabilities have more impact than low-severity ones
- **Codebase Size**: Larger codebases naturally have more potential vulnerabilities
- **Risk Normalization**: Comparing security across repositories of different sizes
- **Trend Analysis**: Tracking security improvements over time

#### How GitPulse Calculates SHS

Our SHS implementation uses a weighted scoring system:

1. **Vulnerability Weighting**:
   - Critical: 1.0 (highest impact)
   - High: 0.7
   - Medium: 0.4
   - Low: 0.1 (lowest impact)

2. **Size Normalization**:
   - Score = Weighted vulnerabilities ÷ KLOC (Kilo Lines of Code)
   - This normalizes risk across repositories of different sizes

3. **Saturation Function**:
   - SHS = 100 × (1 – exp(–0.5 × score))
   - Converts raw scores to a 0-100 scale
   - Provides intuitive interpretation

#### SHS Score Interpretation

| Score Range | Security Level | Description |
|-------------|----------------|-------------|
| 90-100 | Excellent | Very low security risk |
| 80-89 | Good | Low security risk |
| 60-79 | Fair | Moderate security risk |
| 40-59 | Poor | High security risk |
| 0-39 | Critical | Very high security risk |

#### Understanding SHS Trends

The SHS includes trend indicators showing improvement or deterioration:

- **Positive delta** (+2.1): Security is improving
- **Negative delta** (-1.5): Security is deteriorating
- **No delta**: Security posture is stable

### Code Quality Metrics

#### SonarCloud Integration

GitPulse integrates with SonarCloud to provide comprehensive code quality analysis:

- **Maintainability**: Code complexity and technical debt
- **Reliability**: Bug density and reliability rating
- **Security**: Security hotspots and vulnerabilities
- **Coverage**: Test coverage percentage

#### Quality Gate Status

Each repository shows a quality gate status:
- **PASS**: Meets all quality thresholds
- **FAIL**: Below quality standards

### Development Activity Metrics

#### Commit Analysis

- **Commit Frequency**: Development activity patterns
- **Commit Types**: Distribution of feature, fix, and maintenance commits
- **Developer Activity**: Individual contributor metrics

#### Pull Request Health

- **PR Velocity**: Time from creation to merge
- **Review Coverage**: Percentage of PRs with reviews
- **Merge Success Rate**: Percentage of PRs successfully merged

### Repository Size Metrics

#### KLOC (Kilo Lines of Code)

- **Current Size**: Total lines of code in the repository
- **Language Breakdown**: Lines of code by programming language
- **Historical Tracking**: Size evolution over time

## Developer Analytics

### Individual Developer Metrics

- **Activity Score**: Overall contribution level
- **Commit Frequency**: Regular development patterns
- **Code Quality**: Average quality of contributions
- **Collaboration**: Team interaction patterns

### Team Analytics

- **Developer Distribution**: Activity across team members
- **Knowledge Sharing**: Cross-repository contributions
- **Skill Mapping**: Expertise areas identification

## Project Analytics

### Multi-Repository Analysis

- **Portfolio Overview**: Combined metrics across projects
- **Cross-Project Trends**: Patterns across multiple repositories
- **Resource Allocation**: Development effort distribution

### Performance Tracking

- **Velocity Metrics**: Development speed indicators
- **Quality Trends**: Code quality evolution
- **Security Posture**: Overall security health

## Using Analytics Data

### Dashboard Navigation

1. **Repository Detail Page**: Click on any repository to see detailed analytics
2. **Slide-over Panels**: Click on metric cards for detailed breakdowns
3. **Date Range Selection**: Filter data by time periods
4. **Export Options**: Download data for external analysis

### Interpreting Trends

- **Green indicators**: Positive trends (improvements)
- **Red indicators**: Negative trends (deterioration)
- **Stable indicators**: No significant change
- **Missing data**: Analysis not available or not configured

### Best Practices

1. **Regular Monitoring**: Check analytics weekly for trends
2. **Actionable Insights**: Use metrics to guide development decisions
3. **Team Communication**: Share insights with development teams
4. **Continuous Improvement**: Use trends to identify improvement areas

## Configuration

### Enabling Analytics

1. **GitHub Integration**: Ensure repositories are properly indexed
2. **SonarCloud Setup**: Configure SonarCloud for code quality analysis
3. **CodeQL Activation**: Enable CodeQL for security analysis
4. **Token Permissions**: Ensure proper API access for all services

### Data Refresh

- **Automatic Updates**: Analytics refresh daily
- **Manual Refresh**: Use indexing commands for immediate updates
- **Historical Data**: Past data is preserved for trend analysis

## Troubleshooting

### Common Issues

- **Missing Data**: Check repository indexing status
- **Outdated Metrics**: Run manual indexing commands
- **Permission Errors**: Verify GitHub token permissions
- **Integration Issues**: Check service configuration

### Getting Help

- **Documentation**: Refer to technical documentation
- **Logs**: Check application logs for error details
- **Support**: Contact support for persistent issues

## 📚 Related Documentation

- **[Overview](overview.md)** - GitPulse overview and features
- **[Projects Guide](projects.md)** - Manage and analyze repositories
- **[Developers Guide](developers.md)** - Manage team analytics
- **[GitHub Setup](github-setup.md)** - Configure GitHub integration 