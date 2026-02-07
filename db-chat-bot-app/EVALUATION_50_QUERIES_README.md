# Evaluation with 50 Test Queries

This document describes how to run the evaluation with 50 test queries and view accuracy scores.

## Test Case Distribution

The evaluation now includes **50 test cases** with the following complexity distribution:

- **Simple**: 10 test cases (20%)
- **Medium**: 17 test cases (34%)
- **Complex**: 15 test cases (30%)
- **Very Complex**: 8 test cases (16%)

**Total: 50 test cases**

## Quick Start

### 1. Run Evaluation with All Configurations

```bash
python run_evaluation_50_queries.py
```

This will:
- Run all 50 test cases
- Evaluate baseline and RAG-enhanced configurations
- Display accuracy scores in a formatted table
- Save results to `evaluation_results_50/` directory

### 2. Run Only Baseline Evaluation

```bash
python run_evaluation_50_queries.py --config baseline
```

### 3. Run Only RAG-Enhanced Evaluation

```bash
python run_evaluation_50_queries.py --config rag
```

### 4. Specify Custom Database Connection

```bash
python run_evaluation_50_queries.py \
    --host localhost \
    --port 5432 \
    --database customer_orders_and_reviews_db \
    --user postgres \
    --password postgres
```

### 5. Use Specific Ollama Model

```bash
python run_evaluation_50_queries.py --model llama2
```

## Output Format

The script displays:

### 1. Overall Accuracy Metrics
- **Results Match Rate**: Primary accuracy metric (percentage of queries with correct results)
- **Execution Success Rate**: Percentage of queries that executed successfully
- **SQL Generated Rate**: Percentage of queries for which SQL was generated

### 2. Accuracy by Complexity
Shows accuracy breakdown for:
- Simple queries
- Medium complexity queries
- Complex queries
- Very complex queries

### 3. Accuracy by Category
Shows accuracy for different query types:
- Basic SELECT
- Filtering
- JOINs
- Aggregations
- Subqueries
- Sorting
- Pagination

### 4. Failed Queries
Lists queries that failed with error messages

### 5. Comparison Table
If multiple configurations are evaluated, shows a side-by-side comparison table.

## Example Output

```
================================================================================
BASELINE - ACCURACY SUMMARY
================================================================================

Total Test Cases: 50

📊 Overall Accuracy Metrics:
  ✅ Results Match Rate:     72.00% (36/50)
  ⚙️  Execution Success Rate: 88.00% (44/50)
  🔧 SQL Generated Rate:     96.00% (48/50)

📈 Accuracy by Complexity:
  Simple          85.00% ( 8/10 correct)
  Medium          75.00% (12/16 correct)
  Complex         65.00% ( 9/14 correct)
  Very_complex    50.00% ( 3/ 6 correct)

📋 Accuracy by Category:
  aggregation           70.00% ( 7/10 correct)
  basic_select         90.00% ( 9/10 correct)
  filtering            75.00% ( 6/ 8 correct)
  joins                68.00% (11/16 correct)
  pagination          100.00% ( 1/ 1 correct)
  sorting              80.00% ( 4/ 5 correct)
  subqueries           60.00% ( 3/ 5 correct)

================================================================================
ACCURACY COMPARISON TABLE
================================================================================

Configuration    Overall Accuracy (%)  Execution Success (%)  SQL Generated (%)  Simple (%)  Medium (%)  Complex (%)  Very Complex (%)
Baseline         72.00                 88.00                  96.00              85.00       75.00       65.00        50.00
RAG Enhanced     80.00                 92.00                  98.00              90.00       82.00       75.00        60.00
```

## Command Line Options

```
--host HOST              PostgreSQL host (default: localhost)
--port PORT              PostgreSQL port (default: 5432)
--database DATABASE      Database name (default: customer_orders_and_reviews_db)
--user USER              Database user (default: postgres)
--password PASSWORD       Database password (default: postgres)
--neo4j-uri URI          Neo4j URI (default: bolt://localhost:7687)
--neo4j-user USER        Neo4j user (default: neo4j)
--neo4j-password PASS    Neo4j password (default: password)
--model MODEL            Ollama model name (default: auto-detect)
--config CONFIG          Configuration to evaluate: baseline, rag, enhanced, or all (default: all)
--output-dir DIR         Output directory (default: evaluation_results_50)
--verbose                Enable verbose logging
```

## Output Files

The evaluation saves:

1. **`accuracy_comparison.csv`**: Comparison table in CSV format
2. **Detailed JSON reports**: Full evaluation data (if using the full report generator)

## Using Results in Your MTech Report

### 1. Copy Accuracy Scores

From the output, copy the accuracy percentages:
- Overall accuracy: 72.00%
- Simple queries: 85.00%
- Medium queries: 75.00%
- Complex queries: 65.00%
- Very complex queries: 50.00%

### 2. Use Comparison Table

If you ran multiple configurations, use the comparison table to show improvements:
- Baseline: 72.00%
- RAG Enhanced: 80.00%
- Improvement: +8.00 percentage points

### 3. Include Category Breakdown

Show which query types perform best:
- Basic SELECT: 90.00%
- Aggregations: 70.00%
- JOINs: 68.00%
- Subqueries: 60.00%

## Troubleshooting

### Database Connection Issues
```bash
# Check if PostgreSQL is running
docker-compose ps

# Verify connection
psql -h localhost -U postgres -d customer_orders_and_reviews_db
```

### Neo4j Connection Issues
```bash
# Check if Neo4j is running
docker-compose ps

# If Neo4j is not available, run baseline only:
python run_evaluation_50_queries.py --config baseline
```

### Ollama Issues
```bash
# Start Ollama
ollama serve

# Check available models
ollama list

# Install a model if needed
ollama pull llama2
```

## Integration with Full Report Generator

For comprehensive reports with visualizations, use the full report generator:

```bash
python generate_report.py
```

This will generate:
- Detailed Markdown report
- Visualizations (charts)
- Comprehensive analysis
- All comparison tables

## Next Steps

1. **Run the evaluation** to get baseline accuracy scores
2. **Analyze failures** to identify improvement opportunities
3. **Compare configurations** to see RAG and enhanced prompting impact
4. **Include results** in your MTech report with accuracy tables and analysis
