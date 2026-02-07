#!/usr/bin/env python3
"""
Run evaluation with 50 test queries and display accuracy scores.
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
from db_chatbot.rag.knowledge_graph_rag import KnowledgeGraphRAG
from db_chatbot.db_clients.neo4j_client import Neo4jClient
from db_chatbot.query_intent.classifier import QueryClassifier
from collections import Counter
import pandas as pd

logger = get_logger(__name__)


def print_accuracy_summary(results, config_name="Evaluation"):
    """Print formatted accuracy summary."""
    total = len(results)
    if total == 0:
        print(f"\n{config_name}: No results to display")
        return
    
    results_matches = sum(1 for r in results if r.results_match and r.execution_success)
    execution_successes = sum(1 for r in results if r.execution_success)
    sql_generated = sum(1 for r in results if r.generated_sql is not None)
    
    results_match_rate = (results_matches / total * 100) if total > 0 else 0.0
    execution_success_rate = (execution_successes / total * 100) if total > 0 else 0.0
    sql_generated_rate = (sql_generated / total * 100) if total > 0 else 0.0
    
    print("\n" + "=" * 80)
    print(f"{config_name.upper()} - ACCURACY SUMMARY")
    print("=" * 80)
    print(f"\nTotal Test Cases: {total}")
    print(f"\n📊 Overall Accuracy Metrics:")
    print(f"  ✅ Results Match Rate:     {results_match_rate:.2f}% ({results_matches}/{total})")
    print(f"  ⚙️  Execution Success Rate: {execution_success_rate:.2f}% ({execution_successes}/{total})")
    print(f"  🔧 SQL Generated Rate:     {sql_generated_rate:.2f}% ({sql_generated}/{total})")
    
    # By complexity
    print(f"\n📈 Accuracy by Complexity:")
    complexity_counter = Counter([r.test_case.complexity for r in results])
    for complexity in ["simple", "medium", "complex", "very_complex"]:
        comp_results = [r for r in results if r.test_case.complexity == complexity]
        if comp_results:
            comp_total = len(comp_results)
            comp_matches = sum(1 for r in comp_results if r.results_match and r.execution_success)
            comp_rate = (comp_matches / comp_total * 100) if comp_total > 0 else 0.0
            print(f"  {complexity.capitalize():15} {comp_rate:6.2f}% ({comp_matches:2}/{comp_total:2} correct)")
    
    # By category
    print(f"\n📋 Accuracy by Category:")
    category_counter = Counter([r.test_case.category for r in results])
    for category in sorted(category_counter.keys()):
        cat_results = [r for r in results if r.test_case.category == category]
        if cat_results:
            cat_total = len(cat_results)
            cat_matches = sum(1 for r in cat_results if r.results_match and r.execution_success)
            cat_rate = (cat_matches / cat_total * 100) if cat_total > 0 else 0.0
            print(f"  {category:20} {cat_rate:6.2f}% ({cat_matches:2}/{cat_total:2} correct)")
    
    # Failed queries
    failed = [r for r in results if not (r.results_match and r.execution_success)]
    if failed:
        print(f"\n❌ Failed Queries ({len(failed)}):")
        for r in failed[:10]:  # Show first 10 failures
            error_msg = r.error_message or r.execution_error or "Unknown error"
            print(f"  - {r.test_case.id}: {r.test_case.natural_language[:60]}...")
            print(f"    Error: {error_msg[:80]}")
        if len(failed) > 10:
            print(f"  ... and {len(failed) - 10} more")
    
    print("\n" + "=" * 80)


def create_accuracy_table(results_list, config_names):
    """Create a comparison table of accuracy scores."""
    rows = []
    for results, name in zip(results_list, config_names):
        total = len(results)
        if total == 0:
            continue
        
        results_matches = sum(1 for r in results if r.results_match and r.execution_success)
        execution_successes = sum(1 for r in results if r.execution_success)
        sql_generated = sum(1 for r in results if r.generated_sql is not None)
        
        # By complexity
        complexity_rates = {}
        for comp in ["simple", "medium", "complex", "very_complex"]:
            comp_results = [r for r in results if r.test_case.complexity == comp]
            if comp_results:
                comp_matches = sum(1 for r in comp_results if r.results_match and r.execution_success)
                complexity_rates[comp] = (comp_matches / len(comp_results) * 100) if comp_results else 0.0
        
        rows.append({
            "Configuration": name,
            "Overall Accuracy (%)": round(results_matches / total * 100, 2),
            "Execution Success (%)": round(execution_successes / total * 100, 2),
            "SQL Generated (%)": round(sql_generated / total * 100, 2),
            "Simple (%)": round(complexity_rates.get("simple", 0.0), 2),
            "Medium (%)": round(complexity_rates.get("medium", 0.0), 2),
            "Complex (%)": round(complexity_rates.get("complex", 0.0), 2),
            "Very Complex (%)": round(complexity_rates.get("very_complex", 0.0), 2),
        })
    
    return pd.DataFrame(rows)


def main():
    """Main evaluation function."""
    parser = argparse.ArgumentParser(description="Evaluate SQL query generation with 50 test cases")
    parser.add_argument("--host", type=str, default="localhost", help="PostgreSQL host")
    parser.add_argument("--port", type=int, default=5432, help="PostgreSQL port")
    parser.add_argument("--database", type=str, default="customer_orders_and_reviews_db", help="Database name")
    parser.add_argument("--user", type=str, default="postgres", help="Database user")
    parser.add_argument("--password", type=str, default="postgres", help="Database password")
    parser.add_argument("--neo4j-uri", type=str, default="bolt://localhost:7687", help="Neo4j URI")
    parser.add_argument("--neo4j-user", type=str, default="neo4j", help="Neo4j user")
    parser.add_argument("--neo4j-password", type=str, default="password", help="Neo4j password")
    parser.add_argument("--model", type=str, help="Ollama model name")
    parser.add_argument("--config", type=str, choices=["baseline", "rag", "enhanced", "all"], 
                       default="all", help="Configuration to evaluate")
    parser.add_argument("--output-dir", type=str, default="all_test/result", help="Output directory")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(level=log_level)
    
    logger.info("=" * 80)
    logger.info("SQL Query Generation Evaluation - 50 Test Cases")
    logger.info("=" * 80)
    
    # Verify test case count
    logger.info(f"Total test cases available: {len(TEST_CASES)}")
    complexity_dist = Counter([tc.complexity for tc in TEST_CASES])
    logger.info(f"Complexity distribution: {dict(complexity_dist)}")
    
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
    
    # Connect to Neo4j if needed
    neo4j_client = None
    if args.config in ["rag", "enhanced", "all"]:
        logger.info("Connecting to Neo4j...")
        neo4j_client = Neo4jClient()
        neo4j_success = neo4j_client.connect(
            uri=args.neo4j_uri,
            user=args.neo4j_user,
            password=args.neo4j_password
        )
        if not neo4j_success:
            logger.warning("Failed to connect to Neo4j. RAG evaluations will be skipped.")
            neo4j_client = None
    
    # Initialize components
    logger.info("Initializing components...")
    sql_generator = SQLGenerator(model_name=args.model)
    logger.info(f"SQL Generator initialized with model: {sql_generator.model_name}")
    
    # Run evaluations
    all_results = []
    all_config_names = []
    
    # Baseline evaluation
    if args.config in ["baseline", "all"]:
        logger.info("\n" + "=" * 80)
        logger.info("RUNNING BASELINE EVALUATION")
        logger.info("=" * 80)
        
        schema_rag = SchemaRAG()
        schema_rag.load_schema(schema_info, database_name=args.database, host=args.host, port=args.port)
        
        evaluator = SQLQueryEvaluator(
            db_client=db_client,
            sql_generator=sql_generator,
            schema_rag=schema_rag,
            response_generator=None,
            query_classifier=None
        )
        
        results = evaluator.evaluate_all()
        all_results.append(results)
        all_config_names.append("Baseline")
        print_accuracy_summary(results, "Baseline")
    
    # RAG evaluation
    if args.config in ["rag", "enhanced", "all"] and neo4j_client:
        logger.info("\n" + "=" * 80)
        logger.info("RUNNING RAG-ENHANCED EVALUATION")
        logger.info("=" * 80)
        
        kg_rag = KnowledgeGraphRAG(neo4j_client)
        kg_rag.build_graph_from_schema(
            schema_info=schema_info,
            database_name=args.database,
            host=args.host,
            port=args.port
        )
        
        schema_rag = SchemaRAG(knowledge_graph_rag=kg_rag)
        schema_rag.load_schema(schema_info, database_name=args.database, host=args.host, port=args.port)
        
        evaluator = SQLQueryEvaluator(
            db_client=db_client,
            sql_generator=sql_generator,
            schema_rag=schema_rag,
            response_generator=None,
            query_classifier=None
        )
        
        results = evaluator.evaluate_all()
        all_results.append(results)
        all_config_names.append("RAG Enhanced")
        print_accuracy_summary(results, "RAG Enhanced")
    
    # Comparison table
    if len(all_results) > 1:
        print("\n" + "=" * 80)
        print("ACCURACY COMPARISON TABLE")
        print("=" * 80)
        df = create_accuracy_table(all_results, all_config_names)
        print("\n" + df.to_string(index=False))
        print("\n" + "=" * 80)
        
        # Save to CSV
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_file = output_dir / "accuracy_comparison.csv"
        df.to_csv(csv_file, index=False)
        logger.info(f"\nAccuracy comparison table saved to: {csv_file}")
    
    logger.info("\n" + "=" * 80)
    logger.info("Evaluation complete!")
    logger.info("=" * 80)
    
    # Close connections
    db_client.close()
    if neo4j_client:
        neo4j_client.close()


if __name__ == "__main__":
    main()
