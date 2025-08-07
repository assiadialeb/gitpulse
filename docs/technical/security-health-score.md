# Security Health Score (SHS) Technical Documentation

This document provides technical details about GitPulse's Security Health Score (SHS) implementation, including the mathematical model, data structures, and implementation details.

## Overview

The Security Health Score (SHS) is a sophisticated metric that evaluates the security posture of codebases by analyzing CodeQL vulnerability data and normalizing it against repository size. This provides a standardized way to compare security across repositories of different sizes and complexity.

## Mathematical Model

### Core Formula

The SHS calculation follows this mathematical model:

```
SHS = 100 × (1 – exp(–α × score_surface))
```

Where:
- `α` = 0.5 (saturation parameter)
- `score_surface` = total_weighted_vulnerabilities ÷ KLOC

### Vulnerability Weighting

Vulnerabilities are weighted by severity to reflect their relative impact:

| Severity | Weight | Description |
|----------|--------|-------------|
| Critical | 1.0 | Highest security risk |
| High | 0.7 | Significant security risk |
| Medium | 0.4 | Moderate security risk |
| Low | 0.1 | Minimal security risk |

### Size Normalization

The score is normalized by repository size (KLOC) to enable fair comparison across repositories of different sizes:

```
score_surface = Σ(vulnerability_count × severity_weight) ÷ KLOC
```

### Saturation Function

The exponential saturation function ensures:
- Scores are bounded between 0-100
- Intuitive interpretation (higher = better)
- Diminishing returns for very high vulnerability counts

## Implementation Details

### Data Model

#### SecurityHealthHistory (MongoDB)

```python
class SecurityHealthHistory(Document):
    repository_full_name = StringField(required=True)
    repository_id = IntField(required=True)
    shs_score = FloatField(required=True)  # 0-100
    delta_shs = FloatField(default=0.0)  # Change from previous
    calculated_at = DateTimeField(required=True)
    month = StringField(required=True)  # YYYY-MM format
    
    # Metadata
    total_vulnerabilities = IntField(default=0)
    critical_count = IntField(default=0)
    high_count = IntField(default=0)
    medium_count = IntField(default=0)
    low_count = IntField(default=0)
    kloc = FloatField(default=0.0)
```

### Service Architecture

#### SecurityHealthScoreService

The main service responsible for SHS calculations:

```python
class SecurityHealthScoreService:
    def __init__(self):
        self.weights = {
            'critical': 1.0,
            'high': 0.7,
            'medium': 0.4,
            'low': 0.1
        }
        self.alpha = 0.5  # Saturation parameter
    
    def calculate_shs(self, repository_full_name, repository_id, kloc):
        # Main calculation logic
```

### Calculation Process

1. **Data Retrieval**: Fetch open vulnerabilities from CodeQL
2. **Weighting**: Apply severity weights to vulnerability counts
3. **Normalization**: Divide by KLOC for size normalization
4. **Saturation**: Apply exponential function for 0-100 scale
5. **Delta Calculation**: Compare with previous analysis
6. **History Storage**: Save to MongoDB for trend analysis

### Edge Cases

#### No Vulnerabilities
- If CodeQL analysis is available but no vulnerabilities found: SHS = 100
- If CodeQL not available: SHS = "Not available"

#### Zero KLOC
- Repository size not available: SHS = "Not available"
- Prevents division by zero

#### No Previous Analysis
- First-time calculation: delta_shs = 0.0
- No trend information available

## Integration Points

### CodeQL Indexing Service

SHS calculation is integrated into the CodeQL indexing process:

```python
def get_repository_security_metrics(self, repository_full_name, repository_id):
    # Calculate SHS during indexing
    shs_service = SecurityHealthScoreService()
    shs_result = shs_service.calculate_shs(repository_full_name, repository_id, kloc)
```

### Repository Views

SHS data is displayed in repository detail pages and slide-over panels:

```python
def _get_codeql_metrics(repository, user_id):
    # Include SHS in metrics response
    metrics = indexing_service.get_repository_security_metrics(
        repository.full_name, repository.id
    )
```

## Management Commands

### Calculate SHS for All Repositories

```bash
python manage.py calculate_shs_all_repos
```

### Calculate SHS for Specific Repository

```bash
python manage.py calculate_shs_all_repos --repository-id 38
```

### Force Recalculation

```bash
python manage.py calculate_shs_all_repos --force
```

## Performance Considerations

### Database Queries

- Vulnerability queries are optimized with indexes
- Historical data is stored in MongoDB for fast retrieval
- Delta calculations use efficient sorting and limiting

### Caching Strategy

- SHS calculations are cached during indexing
- Historical data is preserved for trend analysis
- Real-time calculations are performed on-demand

### Scalability

- Calculations are performed per repository
- No cross-repository dependencies
- Parallel processing possible for bulk operations

## Monitoring and Alerting

### Calculation Logs

SHS calculations are logged with detailed information:

```
[INFO] Calculated SHS for assiadialeb/gitpulse: 76.0/100 (83 vulnerabilities)
```

### Error Handling

- Graceful handling of missing data
- Fallback values for edge cases
- Detailed error messages for debugging

### Health Checks

- Verify SHS calculation accuracy
- Monitor calculation performance
- Track data quality metrics

## Future Enhancements

### Planned Improvements

1. **Advanced Weighting**: Customizable severity weights
2. **Temporal Analysis**: Time-based vulnerability scoring
3. **Industry Benchmarks**: Compare against industry standards
4. **Predictive Analytics**: Forecast security trends

### Configuration Options

- Adjustable saturation parameter (α)
- Customizable severity weights
- Configurable update frequencies
- Flexible scoring algorithms

## Troubleshooting

### Common Issues

1. **Missing SHS Data**
   - Check if CodeQL analysis is available
   - Verify repository indexing status
   - Run manual SHS calculation

2. **Incorrect Scores**
   - Verify KLOC calculation accuracy
   - Check vulnerability data completeness
   - Review weighting configuration

3. **Performance Issues**
   - Monitor calculation times
   - Check database query performance
   - Review caching strategy

### Debug Commands

```bash
# Check SHS calculation for specific repository
python manage.py calculate_shs_all_repos --repository-id 38

# Verify vulnerability data
python manage.py shell -c "from analytics.models import CodeQLVulnerability; print(CodeQLVulnerability.objects.count())"

# Check historical data
python manage.py shell -c "from analytics.models import SecurityHealthHistory; print(SecurityHealthHistory.objects.count())"
```

## References

- [CodeQL Documentation](https://codeql.github.com/)
- [MongoDB Aggregation](https://docs.mongodb.com/manual/aggregation/)
- [Security Metrics Best Practices](https://owasp.org/www-project-security-metrics/) 