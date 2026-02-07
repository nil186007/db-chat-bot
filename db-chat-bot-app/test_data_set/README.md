# All Test Results

This folder contains all evaluation test results and reports.

## Folder Structure

```
all_test/
├── README.md          # This file
└── result/            # All evaluation results and reports
    ├── accuracy_comparison.csv
    ├── overall_comparison.csv
    ├── complexity_comparison.csv
    ├── category_comparison.csv
    ├── mtech_evaluation_report.md
    ├── evaluation_data.json
    ├── accuracy_comparison.png
    ├── accuracy_by_complexity.png
    ├── improvement_analysis.png
    └── evaluation_report_*.json (from run_evaluation.py)
```

## Running Evaluations

### Quick Evaluation (50 queries with accuracy scores)

```bash
python run_evaluation_50_queries.py
```

Results will be saved to: `all_test/result/accuracy_comparison.csv`

### Comprehensive Report Generation

```bash
python generate_report.py
```

This generates:
- Markdown report (`mtech_evaluation_report.md`)
- CSV comparison tables
- JSON data files
- Visualization charts (PNG)

All files are saved to: `all_test/result/`

### Standard Evaluation (with detailed JSON reports)

```bash
python run_evaluation.py
```

Results are saved to: `all_test/result/evaluation_report_*.json` and `evaluation_results_*.csv`

## Output Files

### CSV Files
- **`accuracy_comparison.csv`**: Overall accuracy comparison across configurations
- **`overall_comparison.csv`**: Detailed overall metrics
- **`complexity_comparison.csv`**: Accuracy breakdown by query complexity
- **`category_comparison.csv`**: Accuracy breakdown by query category

### Markdown Report
- **`mtech_evaluation_report.md`**: Comprehensive evaluation report ready for MTech submission

### JSON Files
- **`evaluation_data.json`**: Complete evaluation data in JSON format
- **`evaluation_report_*.json`**: Detailed evaluation reports with timestamps

### Visualizations
- **`accuracy_comparison.png`**: Bar chart comparing configurations
- **`accuracy_by_complexity.png`**: Chart showing accuracy by complexity level
- **`improvement_analysis.png`**: Chart showing accuracy improvements

## Test Cases

The evaluation uses **50 test cases** with the following distribution:

- **Simple**: 10 queries (20%)
- **Medium**: 17 queries (34%)
- **Complex**: 15 queries (30%)
- **Very Complex**: 8 queries (16%)

## Using Results in Your Report

1. **Copy accuracy scores** from the CSV files or console output
2. **Include visualizations** (PNG files) in your report
3. **Reference the markdown report** for detailed analysis
4. **Use comparison tables** to show improvements across configurations

## Notes

- All evaluation scripts default to saving results in `all_test/result/`
- You can override the output directory using `--output-dir` parameter
- Previous results are not automatically overwritten (timestamps in filenames)
- For clean results, delete old files before running new evaluations
