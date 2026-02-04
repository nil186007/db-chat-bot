#!/usr/bin/env python3
"""
Main script to run SQL query generation evaluation tests.
"""
import sys
from pathlib import Path

# Add src directory to Python path
app_dir = Path(__file__).parent
src_dir = app_dir / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

import argparse
from db_chatbot.config.settings import get_logger, setup_logging
from db_chatbot.evaluation.evaluator import SQLQueryEvaluator
from db_chatbot.evaluation.test_cases import TEST_CASES, get_test_cases_by_complexity
from db_chatbot.db_clients.postgres_client import PostgresClient
from db_chatbot.query_generator.sql_generator import SQLGenerator
from db_chatbot.query_generator.response_generator import ResponseGenerator
from db_chatbot.rag.schema_rag import SchemaRAG
from db_chatbot.query_intent.classifier import QueryClassifier

logger = get_logger(__name__)


def main():
    """Main evaluation function."""
    parser = argparse.ArgumentParser(description="Evaluate SQL query generation accuracy")
    parser.add_argument(
        "--host",
        type=str,
        default="localhost",
        help="PostgreSQL host (default: localhost)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5432,
        help="PostgreSQL port (default: 5432)"
    )
    parser.add_argument(
        "--database",
        type=str,
        default="customer_orders_and_reviews_db",
        help="Database name (default: customer_orders_and_reviews_db)"
    )
    parser.add_argument(
        "--user",
        type=str,
        default="postgres",
        help="Database user (default: postgres)"
    )
    parser.add_argument(
        "--password",
        type=str,
        default="postgres",
        help="Database password (default: postgres)"
    )
    parser.add_argument(
        "--complexity",
        type=str,
        choices=["simple", "medium", "complex", "very_complex"],
        help="Filter test cases by complexity level"
    )
    parser.add_argument(
        "--category",
        type=str,
        help="Filter test cases by category"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="evaluation_results",
        help="Output directory for evaluation reports (default: evaluation_results)"
    )
    parser.add_argument(
        "--model",
        type=str,
        help="Ollama model name (default: auto-detect)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Set up logging
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(level=log_level)
    
    logger.info("=" * 80)
    logger.info("SQL Query Generation Evaluation")
    logger.info("=" * 80)
    
    # Connect to database
    logger.info(f"Connecting to database: {args.host}:{args.port}/{args.database}")
    db_client = PostgresClient()
    success, message = db_client.connect(
        host=args.host,
        port=args.port,
        database=args.database,
        user=args.user,
        password=args.password
    )
    
    if not success:
        logger.error(f"Failed to connect to database: {message}")
        sys.exit(1)
    
    logger.info("Database connection established")
    
    # Fetch schema
    logger.info("Fetching database schema...")
    schema_info = db_client.fetch_schema()
    if not schema_info:
        logger.error("Failed to fetch database schema")
        db_client.close()
        sys.exit(1)
    
    logger.info(f"Schema loaded: {len(schema_info.get('tables', []))} table(s)")
    
    # Initialize components
    logger.info("Initializing components...")
    
    # SQL Generator
    sql_generator = SQLGenerator(model_name=args.model)
    logger.info(f"SQL Generator initialized with model: {sql_generator.model_name}")
    
    # Schema RAG
    schema_rag = SchemaRAG()
    schema_rag.load_schema(schema_info, database_name=args.database, host=args.host, port=args.port)
    logger.info("Schema RAG initialized")
    
    # Response Generator (optional)
    try:
        response_generator = ResponseGenerator()
        logger.info("Response Generator initialized")
    except Exception as e:
        logger.warning(f"Response Generator not available: {e}")
        response_generator = None
    
    # Query Classifier (optional)
    try:
        query_classifier = QueryClassifier()
        logger.info("Query Classifier initialized")
    except Exception as e:
        logger.warning(f"Query Classifier not available: {e}")
        query_classifier = None
    
    # Initialize evaluator
    evaluator = SQLQueryEvaluator(
        db_client=db_client,
        sql_generator=sql_generator,
        schema_rag=schema_rag,
        response_generator=response_generator,
        query_classifier=query_classifier
    )
    
    # Show test case summary
    if args.complexity:
        test_cases = get_test_cases_by_complexity(args.complexity)
        logger.info(f"Filtering by complexity: {args.complexity}")
    else:
        test_cases = TEST_CASES
    
    if args.category:
        test_cases = [tc for tc in test_cases if tc.category == args.category]
        logger.info(f"Filtering by category: {args.category}")
    
    logger.info(f"Total test cases to evaluate: {len(test_cases)}")
    
    # Run evaluation
    logger.info("Starting evaluation...")
    results = evaluator.evaluate_all(
        complexity_filter=args.complexity,
        category_filter=args.category
    )
    
    # Generate report
    logger.info("Generating evaluation report...")
    output_dir = Path(args.output_dir)
    report = evaluator.generate_report(results, output_dir=output_dir)
    
    # Print summary
    logger.info("=" * 80)
    logger.info("EVALUATION SUMMARY")
    logger.info("=" * 80)
    summary = report.get("summary", {})
    logger.info(f"Total Test Cases: {summary.get('total_test_cases', 0)}")
    logger.info(f"SQL Generated Rate: {summary.get('sql_generated_rate', 0.0):.2%}")
    logger.info(f"Results Match Rate: {summary.get('results_match_rate', 0.0):.2%} ⭐ (PRIMARY METRIC)")
    logger.info(f"Execution Success Rate: {summary.get('execution_success_rate', 0.0):.2%}")
    logger.info(f"Validation Pass Rate: {summary.get('validation_pass_rate', 0.0):.2%}")
    logger.info(f"Average Execution Time: {summary.get('avg_execution_time_ms', 0.0):.2f} ms")
    logger.info(f"Average Retry Count: {summary.get('avg_retry_count', 0.0):.2f}")
    
    # Print by complexity
    if report.get("by_complexity"):
        logger.info("\n" + "-" * 80)
        logger.info("METRICS BY COMPLEXITY")
        logger.info("-" * 80)
        for complexity, metrics in report["by_complexity"].items():
            logger.info(f"\n{complexity.upper()}:")
            logger.info(f"  Total: {metrics['total']}")
            logger.info(f"  Results Match Rate: {metrics['results_match_rate']:.2%} ({metrics['results_match_count']}/{metrics['total']})")
            logger.info(f"  Execution Success Rate: {metrics['execution_success_rate']:.2%}")
    
    # Print by category
    if report.get("by_category"):
        logger.info("\n" + "-" * 80)
        logger.info("METRICS BY CATEGORY")
        logger.info("-" * 80)
        for category, metrics in report["by_category"].items():
            logger.info(f"\n{category}:")
            logger.info(f"  Total: {metrics['total']}")
            logger.info(f"  Results Match Rate: {metrics['results_match_rate']:.2%} ({metrics['results_match_count']}/{metrics['total']})")
            logger.info(f"  Execution Success Rate: {metrics['execution_success_rate']:.2%}")
    
    logger.info("=" * 80)
    logger.info(f"Evaluation complete! Reports saved to: {output_dir.absolute()}")
    logger.info("=" * 80)
    
    # Close database connection
    db_client.close()
    
    # Exit with appropriate code
    if summary.get('execution_success_rate', 0.0) < 0.5:
        logger.warning("Low execution success rate - check errors in report")
        sys.exit(1)
    
    sys.exit(0)


if __name__ == "__main__":
    main()
