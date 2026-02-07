#!/usr/bin/env python3
"""
Main script to run MongoDB query generation evaluation tests.
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
from db_chatbot.evaluation.mongodb_evaluator import MongoDBQueryEvaluator
from db_chatbot.evaluation.mongodb_test_cases import (
    MONGODB_TEST_CASES, 
    get_mongodb_test_cases_by_complexity
)
from db_chatbot.db_clients.mongodb_client import MongoDBClient
from db_chatbot.query_generator.mongodb_query_generator import MongoDBQueryGenerator
from db_chatbot.query_generator.response_generator import ResponseGenerator
from db_chatbot.rag.knowledge_graph_rag import KnowledgeGraphRAG
from db_chatbot.db_clients.neo4j_client import Neo4jClient

logger = get_logger(__name__)


def main():
    """Main evaluation function."""
    parser = argparse.ArgumentParser(description="Evaluate MongoDB query generation accuracy")
    parser.add_argument(
        "--host",
        type=str,
        default="localhost",
        help="MongoDB host (default: localhost)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=27017,
        help="MongoDB port (default: 27017)"
    )
    parser.add_argument(
        "--database",
        type=str,
        default="vendor_supply_chain_db",
        help="Database name (default: vendor_supply_chain_db)"
    )
    parser.add_argument(
        "--user",
        type=str,
        default="admin",
        help="Database user (default: admin)"
    )
    parser.add_argument(
        "--password",
        type=str,
        default="adminpassword",
        help="Database password (default: adminpassword)"
    )
    parser.add_argument(
        "--neo4j-uri",
        type=str,
        default="bolt://localhost:7687",
        help="Neo4j URI (default: bolt://localhost:7687)"
    )
    parser.add_argument(
        "--neo4j-user",
        type=str,
        default="neo4j",
        help="Neo4j user (default: neo4j)"
    )
    parser.add_argument(
        "--neo4j-password",
        type=str,
        default="password",
        help="Neo4j password (default: password)"
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
        default="all_test/result",
        help="Output directory for evaluation reports (default: all_test/result)"
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
    logger.info("MongoDB Query Generation Evaluation")
    logger.info("=" * 80)
    
    # Connect to MongoDB
    logger.info(f"Connecting to MongoDB: {args.host}:{args.port}/{args.database}")
    mongodb_client = MongoDBClient()
    success, message = mongodb_client.connect(
        host=args.host,
        port=args.port,
        database=args.database,
        username=args.user,
        password=args.password
    )
    
    if not success:
        logger.error(f"Failed to connect to MongoDB: {message}")
        sys.exit(1)
    
    logger.info("MongoDB connection established")
    
    # Fetch schema
    logger.info("Fetching MongoDB schema...")
    schema_info = mongodb_client.fetch_schema()
    if not schema_info:
        logger.error("Failed to fetch MongoDB schema")
        mongodb_client.close()
        sys.exit(1)
    
    logger.info(f"Schema loaded: {len(schema_info.get('collections', []))} collection(s)")
    
    # Connect to Neo4j
    logger.info("Connecting to Neo4j...")
    neo4j_client = Neo4jClient()
    neo4j_success = neo4j_client.connect(
        uri=args.neo4j_uri,
        user=args.neo4j_user,
        password=args.neo4j_password
    )
    
    if not neo4j_success:
        logger.warning("Failed to connect to Neo4j. Knowledge graph RAG will not be available.")
        neo4j_client = None
    
    # Initialize components
    logger.info("Initializing components...")
    
    # MongoDB Query Generator
    mongodb_query_generator = MongoDBQueryGenerator(model_name=args.model)
    logger.info(f"MongoDB Query Generator initialized with model: {mongodb_query_generator.model_name}")
    
    # Knowledge Graph RAG
    knowledge_graph_rag = None
    if neo4j_client:
        knowledge_graph_rag = KnowledgeGraphRAG(neo4j_client)
        knowledge_graph_rag.build_graph_from_schema(
            schema_info=schema_info,
            database_name=args.database,
            host=args.host,
            port=args.port,
            db_type="mongodb"
        )
        logger.info("Knowledge Graph RAG initialized")
    else:
        logger.warning("Knowledge Graph RAG not available (Neo4j not connected)")
    
    # Response Generator (optional)
    try:
        response_generator = ResponseGenerator()
        logger.info("Response Generator initialized")
    except Exception as e:
        logger.warning(f"Response Generator not available: {e}")
        response_generator = None
    
    # Initialize evaluator
    if not knowledge_graph_rag:
        logger.error("Knowledge Graph RAG is required for MongoDB evaluation")
        mongodb_client.close()
        sys.exit(1)
    
    evaluator = MongoDBQueryEvaluator(
        mongodb_client=mongodb_client,
        mongodb_query_generator=mongodb_query_generator,
        knowledge_graph_rag=knowledge_graph_rag,
        response_generator=response_generator
    )
    
    # Show test case summary
    if args.complexity:
        test_cases = get_mongodb_test_cases_by_complexity(args.complexity)
        logger.info(f"Filtering by complexity: {args.complexity}")
    else:
        test_cases = MONGODB_TEST_CASES
    
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
    logger.info(f"Queries Generated Rate: {summary.get('queries_generated_rate', 0.0):.2%}")
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
    
    # Close connections
    mongodb_client.close()
    if neo4j_client:
        neo4j_client.close()
    
    # Exit with appropriate code
    if summary.get('execution_success_rate', 0.0) < 0.5:
        logger.warning("Low execution success rate - check errors in report")
        sys.exit(1)
    
    sys.exit(0)


if __name__ == "__main__":
    main()
