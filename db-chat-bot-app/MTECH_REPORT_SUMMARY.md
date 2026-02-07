# MTech Project Report Generator - Quick Start Guide

## What Was Created

A comprehensive evaluation and report generation system for your MTech project that:

1. **Evaluates SQL Query Generation** across 3 configurations:
   - Baseline (basic SQL generation)
   - RAG Enhanced (with knowledge graph)
   - Enhanced Prompting (better prompts + RAG)

2. **Generates Comprehensive Reports** including:
   - Accuracy tables by configuration
   - Accuracy breakdown by query complexity
   - Accuracy breakdown by query category
   - Visualizations (charts and graphs)
   - Detailed analysis and recommendations

3. **Provides Multiple Output Formats**:
   - Markdown report (ready for documentation)
   - CSV tables (for Excel/analysis)
   - JSON data (for programmatic access)
   - PNG visualizations (for presentations)

## Quick Start

### 1. Install Dependencies

```bash
cd db-chat-bot-app
poetry install
```

This will install:
- pandas (for data analysis)
- matplotlib (for visualizations)
- seaborn (for better charts)
- All existing dependencies

### 2. Ensure Databases Are Running

```bash
# Start PostgreSQL and Neo4j
cd docker-setup
docker-compose up -d

# Verify they're running
docker-compose ps
```

### 3. Run the Report Generator

```bash
cd ..
python generate_mtech_report.py
```

This will:
- Run all 40 test cases across 3 configurations
- Generate comparison tables
- Create visualizations
- Save all reports to `mtech_report/` directory

### 4. View Results

```bash
# View the main report
cat mtech_report/mtech_evaluation_report.md

# Or open in your editor
code mtech_report/mtech_evaluation_report.md
```

## Output Files

After running, you'll find in `mtech_report/`:

1. **mtech_evaluation_report.md** - Main report (use this in your MTech report)
2. **overall_comparison.csv** - Overall accuracy comparison table
3. **complexity_comparison.csv** - Accuracy by complexity level
4. **category_comparison.csv** - Accuracy by query category
5. **accuracy_comparison.png** - Bar chart comparing configurations
6. **accuracy_by_complexity.png** - Chart showing accuracy by complexity
7. **improvement_analysis.png** - Chart showing improvements
8. **evaluation_data.json** - Complete raw data

## Using Results in Your MTech Report

### 1. Copy Tables

From the Markdown report, copy the tables directly into your report:

```markdown
## Overall Accuracy Comparison

| Configuration | Results Match Rate (%) | Execution Success Rate (%) | ... |
|---------------|------------------------|----------------------------|-----|
| Baseline      | 65.00                  | 90.00                      | ... |
| RAG Enhanced  | 75.00                  | 92.50                      | ... |
| Enhanced Prompting | 82.50              | 95.00                      | ... |
```

### 2. Include Visualizations

Add the PNG files to your report:

```markdown
![Accuracy Comparison](mtech_report/accuracy_comparison.png)
```

### 3. Reference Metrics

Use the accuracy percentages in your results section:

```
The baseline configuration achieved 65% accuracy, while the RAG-enhanced 
configuration improved to 75%, and enhanced prompting further improved 
to 82.5%, representing a 17.5 percentage point improvement.
```

### 4. Use Analysis

Copy the detailed analysis sections from the report to explain:
- Why RAG improves accuracy
- How enhanced prompting helps
- Which query types benefit most
- Recommendations for further improvements

## Customization Options

### Run Only Specific Evaluations

```bash
# Only baseline and RAG (skip enhanced prompting)
python generate_mtech_report.py --skip-enhanced

# Only baseline
python generate_mtech_report.py --skip-rag --skip-enhanced
```

### Use Different Model

```bash
python generate_mtech_report.py --model mistral
```

### Custom Output Directory

```bash
python generate_mtech_report.py --output-dir final_report
```

## Understanding the Metrics

### Results Match Rate (Primary Metric)
- **What it means**: Percentage of queries that produce correct results
- **Why it matters**: This is the most accurate measure - it compares actual data, not SQL syntax
- **Example**: 82.5% means 33 out of 40 queries returned correct results

### Execution Success Rate
- **What it means**: Percentage of queries that executed without errors
- **Why it matters**: Shows if generated SQL is syntactically valid
- **Example**: 95% means 38 out of 40 queries executed successfully

### By Complexity
- **Simple**: Basic SELECT queries (8 test cases)
- **Medium**: JOINs and aggregations (14 test cases)
- **Complex**: Multiple JOINs and subqueries (12 test cases)
- **Very Complex**: Nested subqueries (6 test cases)

### By Category
- **basic_select**: Simple SELECT queries
- **filtering**: WHERE clauses
- **joins**: JOIN operations
- **aggregation**: COUNT, SUM, AVG, etc.
- **subqueries**: Nested queries

## Expected Results

Based on typical LLM performance:

- **Baseline**: 60-70% accuracy
- **RAG Enhanced**: 70-80% accuracy (+10-15 percentage points)
- **Enhanced Prompting**: 75-85% accuracy (+5-10 percentage points over RAG)

The actual results will depend on:
- The LLM model used (llama2, mistral, etc.)
- Quality of the knowledge graph
- Complexity of test queries
- Database schema complexity

## Troubleshooting

### "Cannot connect to Ollama"
```bash
# Start Ollama
ollama serve

# Check available models
ollama list

# Install a model if needed
ollama pull llama2
```

### "Failed to connect to PostgreSQL"
```bash
# Check if PostgreSQL is running
docker-compose ps

# Check connection details
# Default: localhost:5432, user: postgres, password: postgres
```

### "Failed to connect to Neo4j"
```bash
# Check if Neo4j is running
docker-compose ps

# Default: bolt://localhost:7687, user: neo4j, password: password
# If Neo4j is not available, skip RAG evaluations:
python generate_mtech_report.py --skip-rag --skip-enhanced
```

### "Module not found: matplotlib"
```bash
# Install dependencies
poetry install
```

## Next Steps

1. **Run the evaluation** to get baseline results
2. **Review the generated report** to understand current performance
3. **Analyze failures** to identify improvement opportunities
4. **Iterate on prompts** or RAG enhancements
5. **Re-run evaluation** to measure improvements
6. **Include results** in your MTech report

## Fine-tuning (Optional)

If you want to evaluate a fine-tuned model:

1. Fine-tune your model on SQL generation tasks
2. Load the fine-tuned model in Ollama
3. Run evaluation with `--model your-fine-tuned-model`
4. Compare results with baseline

## Support

For detailed documentation, see `MTECH_REPORT_README.md`.

For evaluation framework details, see `EVALUATION_README.md`.
