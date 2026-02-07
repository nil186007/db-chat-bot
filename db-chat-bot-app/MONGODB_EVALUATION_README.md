# MongoDB Query Generation Evaluation Framework

This evaluation framework tests the accuracy of MongoDB query generation from natural language queries. It includes test cases of varying complexity and provides comprehensive metrics and reports.

## Overview

The MongoDB evaluation framework consists of:

1. **Test Cases** (`src/db_chatbot/evaluation/mongodb_test_cases.py`): A comprehensive set of natural language queries with expected MongoDB queries, organized by complexity levels:
   - **Simple**: Basic find queries, filtering, sorting, pagination
   - **Medium**: Aggregations, complex filters, GROUP BY operations
   - **Complex**: $lookup operations, multiple aggregations, complex pipelines
   - **Very Complex**: Nested aggregations, multiple lookups, complex calculations

2. **Evaluator** (`src/db_chatbot/evaluation/mongodb_evaluator.py`): Core evaluation logic that:
   - Runs test cases through the MongoDB workflow agent
   - Executes both generated and expected MongoDB queries
   - **Compares actual query results** (primary evaluation metric)
   - Handles document normalization and ordering differences
   - Generates comprehensive reports with result-based metrics

3. **Runner Script** (`run_mongodb_evaluation.py`): Main script to execute MongoDB evaluations

## Test Cases

The framework includes **40 MongoDB test cases** covering:

### Categories:
- **Basic Find**: Simple queries on single collections
- **Filtering**: Filter queries with various conditions ($gt, $lt, $in, $regex, etc.)
- **Sorting**: Sort operations with different directions
- **Pagination**: Limit operations
- **Aggregations**: COUNT, SUM, AVG, GROUP BY operations
- **Joins**: $lookup operations to join collections
- **Complex Queries**: Multi-collection queries with multiple operations

### Complexity Distribution:
- Simple: 8 test cases
- Medium: 14 test cases
- Complex: 12 test cases
- Very Complex: 6 test cases

**Total: 40 test cases**

## Usage

### Basic Usage

Run all MongoDB test cases:

```bash
python run_mongodb_evaluation.py
```

### With Custom MongoDB Connection

```bash
python run_mongodb_evaluation.py \
    --host localhost \
    --port 27017 \
    --database vendor_supply_chain_db \
    --user admin \
    --password adminpassword
```

### Filter by Complexity

Test only simple queries:

```bash
python run_mongodb_evaluation.py --complexity simple
```

Test complex queries:

```bash
python run_mongodb_evaluation.py --complexity complex
```

### Filter by Category

Test only aggregation queries:

```bash
python run_mongodb_evaluation.py --category aggregation
```

Test join queries:

```bash
python run_mongodb_evaluation.py --category joins
```

### Specify Ollama Model

```bash
python run_mongodb_evaluation.py --model llama2
```

### Verbose Logging

```bash
python run_mongodb_evaluation.py --verbose
```

### Custom Output Directory

```bash
python run_mongodb_evaluation.py --output-dir my_mongodb_results
```

## Combined Evaluation

Run evaluations for both PostgreSQL and MongoDB:

```bash
python run_combined_evaluation.py
```

This will:
- Run PostgreSQL evaluation (50 test cases)
- Run MongoDB evaluation (40 test cases)
- Generate a combined comparison report
- Save results to `all_test/result/`

### Skip Specific Database

```bash
# Only MongoDB
python run_combined_evaluation.py --skip-postgres

# Only PostgreSQL
python run_combined_evaluation.py --skip-mongodb
```

## Command Line Options

```
--host HOST              MongoDB host (default: localhost)
--port PORT              MongoDB port (default: 27017)
--database DATABASE      Database name (default: vendor_supply_chain_db)
--user USER              Database user (default: admin)
--password PASSWORD      Database password (default: adminpassword)
--neo4j-uri URI          Neo4j URI (default: bolt://localhost:7687)
--neo4j-user USER        Neo4j user (default: neo4j)
--neo4j-password PASS    Neo4j password (default: password)
--complexity {simple,medium,complex,very_complex}
                         Filter test cases by complexity level
--category CATEGORY      Filter test cases by category
--output-dir OUTPUT_DIR  Output directory for reports (default: all_test/result)
--model MODEL            Ollama model name (default: auto-detect)
--verbose                Enable verbose logging
```

## Output

The evaluation generates:

1. **JSON Report** (`mongodb_evaluation_report_YYYYMMDD_HHMMSS.json`):
   - Summary metrics
   - Metrics by complexity level
   - Metrics by category
   - Detailed results for each test case

2. **CSV Results** (`mongodb_evaluation_results_YYYYMMDD_HHMMSS.csv`):
   - Tabular format with all test case results
   - Easy to import into Excel or other tools

3. **Combined Report** (if using `run_combined_evaluation.py`):
   - `combined_accuracy_comparison.csv`: Side-by-side comparison of PostgreSQL and MongoDB
   - `combined_evaluation_report.json`: Combined metrics

## Metrics

The evaluation calculates metrics based on **actual query results** rather than query syntax matching. This ensures that queries producing correct results are considered successful, even if the query structure differs.

### Overall Metrics:
- **Results Match Rate** ⭐: **PRIMARY METRIC** - Percentage of queries that produce the same results as expected query
- **Queries Generated Rate**: Percentage of queries for which MongoDB query was successfully generated
- **Execution Success Rate**: Percentage of queries that execute successfully without errors
- **Validation Pass Rate**: Percentage of queries that pass security validation
- **Average Execution Time**: Average time to generate and execute queries (ms)
- **Average Retry Count**: Average number of retries needed

### By Complexity:
- Breakdown of results match rate and execution success rate for each complexity level

### By Category:
- Breakdown of results match rate and execution success rate for each query category

## MongoDB Query Structure

MongoDB queries are represented as JSON dictionaries with the following structure:

**Find Query:**
```json
{
  "collection": "vendors",
  "filter": {"country": "USA"},
  "projection": {"vendor_name": 1, "_id": 0},
  "sort": {"rating": -1},
  "limit": 10
}
```

**Aggregate Query:**
```json
{
  "collection": "purchase_orders",
  "aggregate": [
    {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    {"$sort": {"count": -1}}
  ]
}
```

## Example Output

```
================================================================================
EVALUATION SUMMARY
================================================================================
Total Test Cases: 40
Queries Generated Rate: 95.00%
Results Match Rate: 78.00% ⭐ (PRIMARY METRIC)
Execution Success Rate: 90.00%
Validation Pass Rate: 92.50%
Average Execution Time: 1234.56 ms
Average Retry Count: 0.35

--------------------------------------------------------------------------------
METRICS BY COMPLEXITY
--------------------------------------------------------------------------------

SIMPLE:
  Total: 8
  Results Match Rate: 87.50% (7/8)
  Execution Success Rate: 100.00%

MEDIUM:
  Total: 14
  Results Match Rate: 78.57% (11/14)
  Execution Success Rate: 92.86%

COMPLEX:
  Total: 12
  Results Match Rate: 75.00% (9/12)
  Execution Success Rate: 83.33%

VERY_COMPLEX:
  Total: 6
  Results Match Rate: 66.67% (4/6)
  Execution Success Rate: 66.67%
```

## Understanding Results

### Results Match ⭐ (Primary Metric)
- **Most Important**: Generated MongoDB query produces the same results as expected query
- Compares actual documents returned by both queries
- Handles ordering differences (compares as sets)
- Normalizes data types (floats rounded, strings lowercased, NULL handling)
- Even if query structure differs, if results match, the query is considered correct
- This is the primary metric for evaluating agent accuracy

### Execution Success
- Query executed without errors
- Doesn't guarantee correctness, but indicates valid MongoDB query
- Must be true for results match to be evaluated

### Query Generated
- Agent successfully generated MongoDB query dictionary
- If false, evaluation cannot proceed

### Validation Pass
- Generated query passed security validation (only read operations allowed)
- Must be true for execution to proceed

## Troubleshooting

### MongoDB Connection Issues
- Ensure MongoDB is running: `docker-compose ps`
- Check connection credentials
- Verify database exists and has data loaded

### Neo4j Connection Issues
- Ensure Neo4j is running: `docker-compose ps`
- Check Neo4j credentials
- Neo4j is required for MongoDB evaluation (knowledge graph RAG)

### Ollama Connection Issues
- Ensure Ollama is running: `ollama serve`
- Check available models: `ollama list`
- Install required model if needed

### Low Success Rates
- Check logs for specific error messages
- Verify test cases match your database schema
- Consider adjusting model or prompt engineering

## Integration with MTech Report

The generated reports can be directly used in your MTech project report:

1. **Copy Tables**: Use the CSV files or copy tables from the console output
2. **Include Metrics**: Reference the accuracy percentages in your results section
3. **Compare Databases**: Use the combined evaluation to show PostgreSQL vs MongoDB performance
4. **Use Analysis**: Reference the detailed analysis sections

## Comparison with PostgreSQL Evaluation

| Feature | PostgreSQL | MongoDB |
|---------|-----------|---------|
| Test Cases | 50 | 40 |
| Query Format | SQL strings | JSON dictionaries |
| Result Format | Rows/Columns | Documents |
| Comparison | Row-based | Document-based |
| Primary Metric | Results Match Rate | Results Match Rate |
| Output Location | `all_test/result/` | `all_test/result/` |

Both evaluations follow the same pattern and can be run together using `run_combined_evaluation.py`.
