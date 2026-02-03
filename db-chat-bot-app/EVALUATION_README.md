# SQL Query Generation Evaluation Framework

This evaluation framework tests the accuracy of SQL query generation from natural language queries. It includes test cases of varying complexity and provides comprehensive metrics and reports.

## Overview

The evaluation framework consists of:

1. **Test Cases** (`src/db_chatbot/evaluation/test_cases.py`): A comprehensive set of natural language queries with expected SQL queries, organized by complexity levels:
   - **Simple**: Basic SELECT queries, WHERE clauses, ORDER BY, LIMIT
   - **Medium**: JOINs, aggregations (COUNT, SUM, AVG), GROUP BY, HAVING
   - **Complex**: Multiple JOINs, subqueries, complex aggregations
   - **Very Complex**: Nested subqueries, correlated subqueries, complex multi-table queries

2. **Evaluator** (`src/db_chatbot/evaluation/evaluator.py`): Core evaluation logic that:
   - Runs test cases through the workflow agent
   - Executes both generated and expected SQL queries
   - **Compares actual query results** (primary evaluation metric)
   - Handles data type normalization and ordering differences
   - Generates comprehensive reports with result-based metrics

3. **Runner Script** (`run_evaluation.py`): Main script to execute evaluations

## Test Cases

The framework includes **40 test cases** covering:

### Categories:
- **Basic SELECT**: Simple queries on single tables
- **Filtering**: WHERE clauses with various conditions
- **Sorting**: ORDER BY with different directions
- **Pagination**: LIMIT clauses
- **Joins**: INNER JOIN, LEFT JOIN, multiple JOINs
- **Aggregation**: COUNT, SUM, AVG, GROUP BY, HAVING
- **Subqueries**: Simple and nested subqueries
- **Complex Queries**: Multi-table queries with multiple operations

### Complexity Distribution:
- Simple: 8 test cases
- Medium: 14 test cases
- Complex: 12 test cases
- Very Complex: 6 test cases

**Total: 40 test cases**

## Usage

### Basic Usage

Run all test cases:

```bash
python run_evaluation.py
```

### With Custom Database Connection

```bash
python run_evaluation.py \
    --host localhost \
    --port 5432 \
    --database ecommerce_db \
    --user postgres \
    --password postgres
```

### Filter by Complexity

Test only simple queries:

```bash
python run_evaluation.py --complexity simple
```

Test complex queries:

```bash
python run_evaluation.py --complexity complex
```

### Filter by Category

Test only JOIN queries:

```bash
python run_evaluation.py --category joins
```

Test aggregation queries:

```bash
python run_evaluation.py --category aggregation
```

### Specify Ollama Model

```bash
python run_evaluation.py --model llama2
```

### Verbose Logging

```bash
python run_evaluation.py --verbose
```

### Custom Output Directory

```bash
python run_evaluation.py --output-dir my_evaluation_results
```

## Command Line Options

```
--host HOST              PostgreSQL host (default: localhost)
--port PORT              PostgreSQL port (default: 5432)
--database DATABASE      Database name (default: ecommerce_db)
--user USER              Database user (default: postgres)
--password PASSWORD      Database password (default: postgres)
--complexity {simple,medium,complex,very_complex}
                         Filter test cases by complexity level
--category CATEGORY      Filter test cases by category
--output-dir OUTPUT_DIR  Output directory for reports (default: evaluation_results)
--model MODEL            Ollama model name (default: auto-detect)
--verbose                Enable verbose logging
```

## Output

The evaluation generates:

1. **JSON Report** (`evaluation_report_YYYYMMDD_HHMMSS.json`):
   - Summary metrics
   - Metrics by complexity level
   - Metrics by category
   - Detailed results for each test case

2. **CSV Results** (`evaluation_results_YYYYMMDD_HHMMSS.csv`):
   - Tabular format with all test case results
   - Easy to import into Excel or other tools

## Metrics

The evaluation calculates metrics based on **actual query results** rather than SQL syntax matching. This ensures that queries producing correct results are considered successful, even if the SQL syntax differs.

### Overall Metrics:
- **Results Match Rate** ⭐: **PRIMARY METRIC** - Percentage of queries that produce the same results as expected SQL
- **SQL Generated Rate**: Percentage of queries for which SQL was successfully generated
- **Execution Success Rate**: Percentage of queries that execute successfully without errors
- **Validation Pass Rate**: Percentage of queries that pass security validation
- **Average Execution Time**: Average time to generate and execute queries (ms)
- **Average Retry Count**: Average number of retries needed

### By Complexity:
- Breakdown of results match rate and execution success rate for each complexity level

### By Category:
- Breakdown of results match rate and execution success rate for each query category

## Example Output

```
================================================================================
EVALUATION SUMMARY
================================================================================
Total Test Cases: 50
SQL Exact Match Rate: 45.00%
Results Match Rate: 78.00%
Execution Success Rate: 92.00%
Validation Pass Rate: 94.00%
Average Semantic Similarity: 0.8234
Average Execution Time: 1234.56 ms
Average Retry Count: 0.32

--------------------------------------------------------------------------------
METRICS BY COMPLEXITY
--------------------------------------------------------------------------------

SIMPLE:
  Total: 8
  SQL Match Rate: 75.00%
  Execution Success Rate: 100.00%
  Avg Similarity: 0.9500

MEDIUM:
  Total: 14
  SQL Match Rate: 50.00%
  Execution Success Rate: 92.86%
  Avg Similarity: 0.8500

COMPLEX:
  Total: 12
  SQL Match Rate: 33.33%
  Execution Success Rate: 83.33%
  Avg Similarity: 0.7500

VERY_COMPLEX:
  Total: 6
  SQL Match Rate: 16.67%
  Execution Success Rate: 66.67%
  Avg Similarity: 0.6500
```

## Adding New Test Cases

To add new test cases, edit `src/db_chatbot/evaluation/test_cases.py`:

```python
TestCase(
    id="new_test_001",
    natural_language="Your natural language query here",
    expected_sql="SELECT * FROM table WHERE condition;",
    complexity="medium",  # or "simple", "complex", "very_complex"
    description="Description of what this test validates",
    category="category_name"  # e.g., "joins", "aggregation", "filtering"
)
```

## Understanding Results

### Results Match ⭐ (Primary Metric)
- **Most Important**: Generated SQL produces the same results as expected SQL
- Compares actual data returned by both queries
- Handles ordering differences (compares as sets)
- Normalizes data types (floats rounded, strings lowercased, NULL handling)
- Even if SQL syntax differs, if results match, the query is considered correct
- This is the primary metric for evaluating agent accuracy

### Execution Success
- Query executed without errors
- Doesn't guarantee correctness, but indicates valid SQL
- Must be true for results match to be evaluated

### SQL Generated
- Agent successfully generated SQL query
- If false, evaluation cannot proceed

### Validation Pass
- Generated SQL passed security validation (only SELECT queries allowed)
- Must be true for execution to proceed

## Troubleshooting

### Database Connection Issues
- Ensure PostgreSQL is running
- Check connection credentials
- Verify database exists and has data loaded

### Ollama Connection Issues
- Ensure Ollama is running: `ollama serve`
- Check available models: `ollama list`
- Install required model if needed

### Low Success Rates
- Check logs for specific error messages
- Verify test cases match your database schema
- Consider adjusting model or prompt engineering

## Integration with CI/CD

You can integrate this evaluation into your CI/CD pipeline:

```bash
# Run evaluation and fail if success rate is too low
python run_evaluation.py --output-dir ci_results
```

Check the exit code and JSON report to determine if tests passed.

## Future Enhancements

Potential improvements:
- More sophisticated SQL comparison (AST-based)
- Result set comparison with tolerance for floating point
- Performance benchmarking
- Query optimization evaluation
- Support for multiple databases
- Interactive test case runner
