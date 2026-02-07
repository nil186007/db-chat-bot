#!/usr/bin/env python3
"""
Combined evaluation script for both PostgreSQL and MongoDB query generation.
Runs evaluations for both databases and generates a comprehensive comparison report.
"""
import sys
from pathlib import Path

# Add src directory to Python path
app_dir = Path(__file__).parent
src_dir = app_dir / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

import argparse
from datetime import datetime
from db_chatbot.config.settings import get_logger, setup_logging
from db_chatbot.evaluation.evaluator import SQLQueryEvaluator, EvaluationResult
from db_chatbot.evaluation.mongodb_evaluator import MongoDBQueryEvaluator, MongoDBEvaluationResult
from db_chatbot.evaluation.test_cases import TEST_CASES
from db_chatbot.evaluation.mongodb_test_cases import MONGODB_TEST_CASES
from db_chatbot.db_clients.postgres_client import PostgresClient
from db_chatbot.db_clients.mongodb_client import MongoDBClient
from db_chatbot.db_clients.neo4j_client import Neo4jClient
from db_chatbot.query_generator.sql_generator import SQLGenerator
from db_chatbot.query_generator.mongodb_query_generator import MongoDBQueryGenerator
from db_chatbot.query_generator.response_generator import ResponseGenerator
from db_chatbot.rag.schema_rag import SchemaRAG
from db_chatbot.rag.knowledge_graph_rag import KnowledgeGraphRAG
from db_chatbot.query_intent.classifier import QueryClassifier
import pandas as pd
import json

logger = get_logger(__name__)


def print_accuracy_summary(results, config_name="Evaluation", db_type="Database"):
    """Print formatted accuracy summary."""
    total = len(results)
    if total == 0:
        print(f"\n{config_name}: No results to display")
        return
    
    if db_type == "PostgreSQL":
        results_matches = sum(1 for r in results if r.results_match and r.execution_success)
        execution_successes = sum(1 for r in results if r.execution_success)
        queries_generated = sum(1 for r in results if r.generated_sql is not None)
    else:  # MongoDB
        results_matches = sum(1 for r in results if r.results_match and r.execution_success)
        execution_successes = sum(1 for r in results if r.execution_success)
        queries_generated = sum(1 for r in results if r.generated_query is not None)
    
    results_match_rate = (results_matches / total * 100) if total > 0 else 0.0
    execution_success_rate = (execution_successes / total * 100) if total > 0 else 0.0
    queries_generated_rate = (queries_generated / total * 100) if total > 0 else 0.0
    
    print("\n" + "=" * 80)
    print(f"{config_name.upper()} - {db_type.upper()} ACCURACY SUMMARY")
    print("=" * 80)
    print(f"\nTotal Test Cases: {total}")
    print(f"\n📊 Overall Accuracy Metrics:")
    print(f"  ✅ Results Match Rate:     {results_match_rate:.2f}% ({results_matches}/{total})")
    print(f"  ⚙️  Execution Success Rate: {execution_success_rate:.2f}% ({execution_successes}/{total})")
    print(f"  🔧 Queries Generated Rate:  {queries_generated_rate:.2f}% ({queries_generated}/{total})")
    
    # By complexity
    print(f"\n📈 Accuracy by Complexity:")
    from collections import Counter
    complexity_counter = Counter([r.test_case.complexity for r in results])
    for complexity in ["simple", "medium", "complex", "very_complex"]:
        comp_results = [r for r in results if r.test_case.complexity == complexity]
        if comp_results:
            comp_total = len(comp_results)
            comp_matches = sum(1 for r in comp_results if r.results_match and r.execution_success)
            comp_rate = (comp_matches / comp_total * 100) if comp_total > 0 else 0.0
            print(f"  {complexity.capitalize():15} {comp_rate:6.2f}% ({comp_matches:2}/{comp_total:2} correct)")
    
    print("\n" + "=" * 80)


def create_combined_accuracy_table(postgres_results, mongodb_results):
    """Create a comparison table of accuracy scores for both databases."""
    rows = []
    
    # PostgreSQL results
    if postgres_results:
        total = len(postgres_results)
        results_matches = sum(1 for r in postgres_results if r.results_match and r.execution_success)
        execution_successes = sum(1 for r in postgres_results if r.execution_success)
        queries_generated = sum(1 for r in postgres_results if r.generated_sql is not None)
        
        rows.append({
            "Database": "PostgreSQL",
            "Total Test Cases": total,
            "Results Match Rate (%)": round(results_matches / total * 100, 2) if total > 0 else 0.0,
            "Execution Success Rate (%)": round(execution_successes / total * 100, 2) if total > 0 else 0.0,
            "Queries Generated Rate (%)": round(queries_generated / total * 100, 2) if total > 0 else 0.0
        })
    
    # MongoDB results
    if mongodb_results:
        total = len(mongodb_results)
        results_matches = sum(1 for r in mongodb_results if r.results_match and r.execution_success)
        execution_successes = sum(1 for r in mongodb_results if r.execution_success)
        queries_generated = sum(1 for r in mongodb_results if r.generated_query is not None)
        
        rows.append({
            "Database": "MongoDB",
            "Total Test Cases": total,
            "Results Match Rate (%)": round(results_matches / total * 100, 2) if total > 0 else 0.0,
            "Execution Success Rate (%)": round(execution_successes / total * 100, 2) if total > 0 else 0.0,
            "Queries Generated Rate (%)": round(queries_generated / total * 100, 2) if total > 0 else 0.0
        })
    
    return pd.DataFrame(rows)


def main():
    """Main evaluation function."""
    parser = argparse.ArgumentParser(description="Evaluate both PostgreSQL and MongoDB query generation accuracy")
    parser.add_argument("--postgres-host", type=str, default="localhost", help="PostgreSQL host")
    parser.add_argument("--postgres-port", type=int, default=5432, help="PostgreSQL port")
    parser.add_argument("--postgres-database", type=str, default="customer_orders_and_reviews_db", help="PostgreSQL database name")
    parser.add_argument("--postgres-user", type=str, default="postgres", help="PostgreSQL user")
    parser.add_argument("--postgres-password", type=str, default="postgres", help="PostgreSQL password")
    parser.add_argument("--mongo-host", type=str, default="localhost", help="MongoDB host")
    parser.add_argument("--mongo-port", type=int, default=27017, help="MongoDB port")
    parser.add_argument("--mongo-database", type=str, default="vendor_supply_chain_db", help="MongoDB database name")
    parser.add_argument("--mongo-user", type=str, default="admin", help="MongoDB user")
    parser.add_argument("--mongo-password", type=str, default="adminpassword", help="MongoDB password")
    parser.add_argument("--neo4j-uri", type=str, default="bolt://localhost:7687", help="Neo4j URI")
    parser.add_argument("--neo4j-user", type=str, default="neo4j", help="Neo4j user")
    parser.add_argument("--neo4j-password", type=str, default="password", help="Neo4j password")
    parser.add_argument("--output-dir", type=str, default="all_test/result", help="Output directory")
    parser.add_argument("--model", type=str, help="Ollama model name")
    parser.add_argument("--skip-postgres", action="store_true", help="Skip PostgreSQL evaluation")
    parser.add_argument("--skip-mongodb", action="store_true", help="Skip MongoDB evaluation")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(level=log_level)
    
    logger.info("=" * 80)
    logger.info("Combined Query Generation Evaluation (PostgreSQL + MongoDB)")
    logger.info("=" * 80)
    
    # Connect to Neo4j (required for both)
    logger.info("Connecting to Neo4j...")
    neo4j_client = Neo4jClient()
    neo4j_success = neo4j_client.connect(
        uri=args.neo4j_uri,
        user=args.neo4j_user,
        password=args.neo4j_password
    )
    
    if not neo4j_success:
        logger.error("Failed to connect to Neo4j. Neo4j is required for evaluations.")
        sys.exit(1)
    
    knowledge_graph_rag = KnowledgeGraphRAG(neo4j_client)
    
    postgres_results = []
    mongodb_results = []
    
    # PostgreSQL Evaluation
    if not args.skip_postgres:
        logger.info("\n" + "=" * 80)
        logger.info("POSTGRESQL EVALUATION")
        logger.info("=" * 80)
        
        logger.info(f"Connecting to PostgreSQL: {args.postgres_host}:{args.postgres_port}/{args.postgres_database}")
        postgres_client = PostgresClient()
        success, message = postgres_client.connect(
            host=args.postgres_host,
            port=args.postgres_port,
            database=args.postgres_database,
            user=args.postgres_user,
            password=args.postgres_password
        )
        
        if not success:
            logger.error(f"Failed to connect to PostgreSQL: {message}")
        else:
            logger.info("PostgreSQL connection established")
            
            # Fetch schema
            logger.info("Fetching PostgreSQL schema...")
            postgres_schema = postgres_client.fetch_schema()
            if postgres_schema:
                logger.info(f"Schema loaded: {len(postgres_schema.get('tables', []))} table(s)")
                
                # Build knowledge graph for PostgreSQL
                knowledge_graph_rag.build_graph_from_schema(
                    schema_info=postgres_schema,
                    database_name=args.postgres_database,
                    host=args.postgres_host,
                    port=args.postgres_port,
                    db_type="postgresql"
                )
                
                # Initialize components
                sql_generator = SQLGenerator(model_name=args.model)
                schema_rag = SchemaRAG(knowledge_graph_rag=knowledge_graph_rag)
                schema_rag.load_schema(postgres_schema, database_name=args.postgres_database, 
                                      host=args.postgres_host, port=args.postgres_port)
                
                # Create evaluator
                evaluator = SQLQueryEvaluator(
                    db_client=postgres_client,
                    sql_generator=sql_generator,
                    schema_rag=schema_rag,
                    response_generator=None,
                    query_classifier=None
                )
                
                logger.info(f"Evaluating {len(TEST_CASES)} PostgreSQL test cases...")
                postgres_results = evaluator.evaluate_all()
                print_accuracy_summary(postgres_results, "PostgreSQL", "PostgreSQL")
                
                postgres_client.close()
            else:
                logger.error("Failed to fetch PostgreSQL schema")
    
    # MongoDB Evaluation
    if not args.skip_mongodb:
        logger.info("\n" + "=" * 80)
        logger.info("MONGODB EVALUATION")
        logger.info("=" * 80)
        
        logger.info(f"Connecting to MongoDB: {args.mongo_host}:{args.mongo_port}/{args.mongo_database}")
        mongodb_client = MongoDBClient()
        success, message = mongodb_client.connect(
            host=args.mongo_host,
            port=args.mongo_port,
            database=args.mongo_database,
            username=args.mongo_user,
            password=args.mongo_password
        )
        
        if not success:
            logger.error(f"Failed to connect to MongoDB: {message}")
        else:
            logger.info("MongoDB connection established")
            
            # Fetch schema
            logger.info("Fetching MongoDB schema...")
            mongodb_schema = mongodb_client.fetch_schema()
            if mongodb_schema:
                logger.info(f"Schema loaded: {len(mongodb_schema.get('collections', []))} collection(s)")
                
                # Build knowledge graph for MongoDB
                knowledge_graph_rag.build_graph_from_schema(
                    schema_info=mongodb_schema,
                    database_name=args.mongo_database,
                    host=args.mongo_host,
                    port=args.mongo_port,
                    db_type="mongodb"
                )
                
                # Initialize components
                mongodb_query_generator = MongoDBQueryGenerator(model_name=args.model)
                
                # Create evaluator
                evaluator = MongoDBQueryEvaluator(
                    mongodb_client=mongodb_client,
                    mongodb_query_generator=mongodb_query_generator,
                    knowledge_graph_rag=knowledge_graph_rag,
                    response_generator=None
                )
                
                logger.info(f"Evaluating {len(MONGODB_TEST_CASES)} MongoDB test cases...")
                mongodb_results = evaluator.evaluate_all()
                print_accuracy_summary(mongodb_results, "MongoDB", "MongoDB")
                
                mongodb_client.close()
            else:
                logger.error("Failed to fetch MongoDB schema")
    
    # Generate combined report
    if postgres_results or mongodb_results:
        logger.info("\n" + "=" * 80)
        logger.info("COMBINED ACCURACY COMPARISON")
        logger.info("=" * 80)
        
        df = create_combined_accuracy_table(postgres_results, mongodb_results)
        print("\n" + df.to_string(index=False))
        
        # Save to CSV
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_file = output_dir / "combined_accuracy_comparison.csv"
        df.to_csv(csv_file, index=False)
        logger.info(f"\nCombined accuracy comparison saved to: {csv_file}")
        
        # Save combined JSON report
        combined_report = {
            "timestamp": datetime.now().isoformat(),
            "postgresql": {
                "total_test_cases": len(postgres_results),
                "results_match_count": sum(1 for r in postgres_results if r.results_match and r.execution_success) if postgres_results else 0,
                "results_match_rate": (sum(1 for r in postgres_results if r.results_match and r.execution_success) / len(postgres_results) * 100) if postgres_results else 0.0
            },
            "mongodb": {
                "total_test_cases": len(mongodb_results),
                "results_match_count": sum(1 for r in mongodb_results if r.results_match and r.execution_success) if mongodb_results else 0,
                "results_match_rate": (sum(1 for r in mongodb_results if r.results_match and r.execution_success) / len(mongodb_results) * 100) if mongodb_results else 0.0
            }
        }
        
        json_file = output_dir / "combined_evaluation_report.json"
        with open(json_file, 'w') as f:
            json.dump(combined_report, f, indent=2)
        logger.info(f"Combined JSON report saved to: {json_file}")
    
    # Close Neo4j connection
    if neo4j_client:
        neo4j_client.close()
    
    logger.info("\n" + "=" * 80)
    logger.info("Combined evaluation complete!")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
