# MTech Project Report Generator

This script generates a comprehensive evaluation report for your MTech project, comparing SQL query generation accuracy across different configurations.

## Overview

The report generator evaluates three different configurations:

1. **Baseline**: Basic SQL generation without RAG enhancements
2. **RAG Enhanced**: SQL generation with knowledge graph RAG for enhanced context
3. **Enhanced Prompting**: SQL generation with improved prompts and RAG

## Features

- **Comprehensive Evaluation**: Tests all 40 test cases across different configurations
- **Detailed Metrics**: Calculates accuracy by complexity level and query category
- **Visualizations**: Generates charts comparing configurations
- **Formatted Reports**: Creates Markdown, CSV, and JSON outputs
- **Improvement Analysis**: Shows accuracy improvements from each enhancement

## Prerequisites

1. **PostgreSQL Database**: Must be running with the `customer_orders_and_reviews_db` database loaded
2. **Neo4j Database**: Must be running for RAG-enhanced evaluations
3. **Ollama**: Must be running with a model installed (e.g., `llama2`, `mistral`)
4. **Python Dependencies**: Install with `poetry install`

## Installation

```bash
# Install dependencies
poetry install

# Ensure databases are running
docker-compose up -d  # If using Docker Compose
```

## Usage

### Basic Usage

Run all evaluations and generate the complete report:

```bash
python generate_mtech_report.py
```

### Custom Database Connections

```bash
python generate_mtech_report.py \
    --host localhost \
    --port 5432 \
    --database customer_orders_and_reviews_db \
    --user postgres \
    --password postgres \
    --neo4j-uri bolt://localhost:7687 \
    --neo4j-user neo4j \
    --neo4j-password password
```

### Specify Ollama Model

```bash
python generate_mtech_report.py --model llama2
```

### Skip Specific Evaluations

If you only want to run certain evaluations:

```bash
# Skip baseline evaluation
python generate_mtech_report.py --skip-baseline

# Skip RAG evaluation
python generate_mtech_report.py --skip-rag

# Skip enhanced prompting evaluation
python generate_mtech_report.py --skip-enhanced
```

### Custom Output Directory

```bash
python generate_mtech_report.py --output-dir my_report
```

## Output Files

The script generates the following files in the output directory:

1. **`mtech_evaluation_report.md`**: Comprehensive Markdown report with:
   - Executive summary
   - Overall accuracy comparison
   - Accuracy by complexity level
   - Accuracy by query category
   - Detailed analysis and recommendations

2. **`overall_comparison.csv`**: Comparison table across all configurations

3. **`complexity_comparison.csv`**: Accuracy comparison by query complexity

4. **`category_comparison.csv`**: Accuracy comparison by query category

5. **`evaluation_data.json`**: Complete evaluation data in JSON format

6. **`accuracy_comparison.png`**: Bar chart comparing overall accuracy

7. **`accuracy_by_complexity.png`**: Bar chart showing accuracy by complexity level

8. **`improvement_analysis.png`**: Chart showing accuracy improvements

## Report Structure

The generated report includes:

### 1. Executive Summary
- Overview of all configurations
- Key findings and improvements

### 2. Overall Accuracy Comparison
- Results match rate (primary metric)
- Execution success rate
- SQL generation rate
- Average execution time
- Average retry count

### 3. Accuracy by Query Complexity
- Simple queries
- Medium complexity queries
- Complex queries
- Very complex queries

### 4. Accuracy by Query Category
- Basic SELECT queries
- Filtering queries
- JOIN queries
- Aggregation queries
- Subquery queries
- etc.

### 5. Detailed Analysis
- RAG enhancement impact
- Enhanced prompting impact
- Complexity analysis
- Category analysis

### 6. Recommendations
- Suggestions for further improvements
- Fine-tuning recommendations
- Error analysis guidance

## Metrics Explained

### Results Match Rate (Primary Metric)
- **Definition**: Percentage of queries that produce the same results as expected SQL
- **Why Important**: This is the most accurate measure of query correctness, as it compares actual data rather than SQL syntax
- **Calculation**: (Number of queries with matching results) / (Total test cases) × 100

### Execution Success Rate
- **Definition**: Percentage of queries that execute successfully without errors
- **Why Important**: Indicates whether generated SQL is syntactically correct

### SQL Generated Rate
- **Definition**: Percentage of queries for which SQL was successfully generated
- **Why Important**: Shows the LLM's ability to generate SQL from natural language

## Example Output

```
================================================================================
MTech Project Report Generator
================================================================================
Connecting to PostgreSQL...
Fetching schema...
Schema loaded: 5 table(s)
Connecting to Neo4j...
Running baseline evaluation...
Running RAG-enhanced evaluation...
Running enhanced prompting evaluation...
Generating report...
Report generation complete! Files saved to: /path/to/mtech_report
================================================================================
```

## Troubleshooting

### Database Connection Issues
- Ensure PostgreSQL is running: `docker-compose ps`
- Check connection credentials
- Verify database exists and has data

### Neo4j Connection Issues
- Ensure Neo4j is running: `docker-compose ps`
- Check Neo4j credentials
- If Neo4j is not available, use `--skip-rag` and `--skip-enhanced`

### Ollama Issues
- Ensure Ollama is running: `ollama serve`
- Check available models: `ollama list`
- Install a model if needed: `ollama pull llama2`

### Missing Dependencies
- Install all dependencies: `poetry install`
- Ensure matplotlib and seaborn are installed for visualizations

## Integration with MTech Report

The generated report can be directly used in your MTech project report:

1. **Copy Tables**: Use the CSV files or copy tables from the Markdown report
2. **Include Visualizations**: Add the PNG charts to your report
3. **Use Analysis**: Reference the detailed analysis section
4. **Cite Metrics**: Use the accuracy percentages in your results section

## Fine-tuning Support

While the script doesn't directly support fine-tuned models, you can:

1. **Use Fine-tuned Model**: Specify your fine-tuned model with `--model your-fine-tuned-model`
2. **Compare Results**: Run evaluations with and without fine-tuning
3. **Add Configuration**: Extend the script to include a "fine-tuned" configuration

## Future Enhancements

Potential improvements:
- Support for fine-tuned model evaluation
- More detailed error analysis
- Query execution time comparison
- Cost analysis (for cloud LLMs)
- Support for multiple databases (MongoDB, etc.)

## Citation

If using this in your MTech report, you can cite it as:

```
Evaluation Framework for SQL Query Generation from Natural Language
Using RAG and Enhanced Prompting Techniques
```
