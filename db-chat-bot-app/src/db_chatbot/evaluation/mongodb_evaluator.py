"""
Evaluation runner for MongoDB query generation accuracy testing.
"""
import json
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
import pandas as pd

from db_chatbot.config.settings import get_logger
from db_chatbot.evaluation.mongodb_test_cases import (
    MongoDBTestCase, 
    get_mongodb_test_cases_by_complexity, 
    MONGODB_TEST_CASES
)
from db_chatbot.agents.mongodb_workflow_agent import MongoDBWorkflowAgent
from db_chatbot.query_generator.mongodb_query_generator import MongoDBQueryGenerator
from db_chatbot.query_generator.response_generator import ResponseGenerator
from db_chatbot.db_clients.mongodb_client import MongoDBClient
from db_chatbot.rag.knowledge_graph_rag import KnowledgeGraphRAG

logger = get_logger(__name__)


class MongoDBQueryNormalizer:
    """Normalize MongoDB queries for comparison."""
    
    @staticmethod
    def normalize_query(query: Dict) -> Dict:
        """
        Normalize MongoDB query for comparison.
        - Remove None values
        - Sort keys
        - Normalize filter values
        """
        if not query:
            return {}
        
        normalized = {}
        
        # Collection name
        if "collection" in query:
            normalized["collection"] = query["collection"].lower()
        
        # Filter (normalize empty dict to None)
        if "filter" in query:
            filter_dict = query["filter"]
            if filter_dict and len(filter_dict) > 0:
                normalized["filter"] = MongoDBQueryNormalizer._normalize_filter(filter_dict)
            else:
                normalized["filter"] = None
        
        # Projection
        if "projection" in query:
            normalized["projection"] = query["projection"] if query["projection"] else None
        
        # Sort
        if "sort" in query:
            normalized["sort"] = query["sort"] if query["sort"] else None
        
        # Limit
        if "limit" in query:
            normalized["limit"] = query["limit"] if query["limit"] else None
        
        # Aggregate pipeline
        if "aggregate" in query:
            normalized["aggregate"] = query["aggregate"]
        
        return normalized
    
    @staticmethod
    def _normalize_filter(filter_dict: Dict) -> Dict:
        """Normalize filter dictionary."""
        if not filter_dict:
            return {}
        
        normalized = {}
        for key, value in filter_dict.items():
            if isinstance(value, dict):
                # Handle operators like $gt, $lt, etc.
                normalized[key] = {k: v for k, v in sorted(value.items())}
            elif isinstance(value, list):
                normalized[key] = sorted(value)
            else:
                normalized[key] = value
        
        return {k: normalized[k] for k in sorted(normalized.keys())}
    
    @staticmethod
    def extract_key_elements(query: Dict) -> Dict[str, List[str]]:
        """
        Extract key elements from MongoDB query for semantic comparison.
        Returns dict with: collections, fields, operations, aggregations
        """
        elements = {
            "collections": [],
            "fields": [],
            "operations": [],
            "aggregations": []
        }
        
        if "collection" in query:
            elements["collections"].append(query["collection"])
        
        if "filter" in query and query["filter"]:
            elements["fields"].extend(query["filter"].keys())
            # Check for aggregation operators
            for value in query["filter"].values():
                if isinstance(value, dict):
                    elements["operations"].extend(value.keys())
        
        if "aggregate" in query:
            elements["operations"].append("aggregate")
            # Extract aggregation stages
            for stage in query["aggregate"]:
                if isinstance(stage, dict):
                    elements["operations"].extend(stage.keys())
                    # Check for $group fields
                    if "$group" in stage:
                        group = stage["$group"]
                        if "_id" in group:
                            if isinstance(group["_id"], dict):
                                elements["fields"].extend(group["_id"].keys())
                            elif group["_id"] is not None:
                                elements["fields"].append("_id")
                        # Check aggregation functions
                        for field, expr in group.items():
                            if field != "_id" and isinstance(expr, dict):
                                elements["aggregations"].extend(expr.keys())
        
        return {
            "collections": list(set(elements["collections"])),
            "fields": list(set(elements["fields"])),
            "operations": list(set(elements["operations"])),
            "aggregations": list(set(elements["aggregations"]))
        }


class MongoDBEvaluationResult:
    """Represents the result of evaluating a single MongoDB test case."""
    
    def __init__(self, test_case: MongoDBTestCase):
        self.test_case = test_case
        self.generated_query: Optional[Dict] = None
        self.execution_success: bool = False
        self.execution_error: Optional[str] = None
        self.expected_results: Optional[Dict] = None
        self.actual_results: Optional[Dict] = None
        self.query_match: bool = False
        self.results_match: bool = False
        self.semantic_similarity: float = 0.0
        self.execution_time_ms: float = 0.0
        self.retry_count: int = 0
        self.validation_passed: bool = False
        self.error_message: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert result to dictionary."""
        return {
            "test_id": self.test_case.id,
            "natural_language": self.test_case.natural_language,
            "expected_query": json.dumps(self.test_case.expected_query),
            "generated_query": json.dumps(self.generated_query) if self.generated_query else None,
            "complexity": self.test_case.complexity,
            "category": self.test_case.category,
            "query_match": self.query_match,
            "results_match": self.results_match,
            "semantic_similarity": self.semantic_similarity,
            "execution_success": self.execution_success,
            "execution_error": self.execution_error,
            "execution_time_ms": self.execution_time_ms,
            "retry_count": self.retry_count,
            "validation_passed": self.validation_passed,
            "error_message": self.error_message
        }


class MongoDBQueryEvaluator:
    """Evaluator for MongoDB query generation accuracy."""
    
    def __init__(
        self,
        mongodb_client: MongoDBClient,
        mongodb_query_generator: MongoDBQueryGenerator,
        knowledge_graph_rag: KnowledgeGraphRAG,
        response_generator: Optional[ResponseGenerator] = None
    ):
        """
        Initialize the MongoDB evaluator.
        
        Args:
            mongodb_client: MongoDB client instance
            mongodb_query_generator: MongoDB query generator instance
            knowledge_graph_rag: Knowledge Graph RAG instance
            response_generator: Response generator (optional)
        """
        self.mongodb_client = mongodb_client
        self.mongodb_query_generator = mongodb_query_generator
        self.knowledge_graph_rag = knowledge_graph_rag
        self.response_generator = response_generator
        
        # Initialize workflow agent
        self.workflow_agent = MongoDBWorkflowAgent(
            mongodb_query_generator=mongodb_query_generator,
            mongodb_client=mongodb_client,
            knowledge_graph_rag=knowledge_graph_rag,
            response_generator=response_generator,
            max_retries=3
        )
        
        logger.info("MongoDBQueryEvaluator initialized")
    
    def normalize_query(self, query: Dict) -> Dict:
        """Normalize MongoDB query for comparison."""
        return MongoDBQueryNormalizer.normalize_query(query)
    
    def compare_queries(self, generated: Dict, expected: Dict) -> Tuple[bool, float]:
        """
        Compare generated MongoDB query with expected query.
        
        Returns:
            Tuple of (exact_match: bool, similarity_score: float)
        """
        if not generated:
            return False, 0.0
        
        gen_norm = self.normalize_query(generated)
        exp_norm = self.normalize_query(expected)
        
        # Exact match
        if gen_norm == exp_norm:
            return True, 1.0
        
        # Semantic similarity
        gen_elements = MongoDBQueryNormalizer.extract_key_elements(generated)
        exp_elements = MongoDBQueryNormalizer.extract_key_elements(expected)
        
        # Calculate similarity based on key elements
        similarity = 0.0
        
        # Collections similarity (40% weight)
        gen_collections = set(gen_elements["collections"])
        exp_collections = set(exp_elements["collections"])
        if exp_collections:
            coll_sim = len(gen_collections & exp_collections) / len(exp_collections)
            similarity += coll_sim * 0.4
        
        # Fields similarity (30% weight)
        gen_fields = set(gen_elements["fields"])
        exp_fields = set(exp_elements["fields"])
        if exp_fields:
            field_sim = len(gen_fields & exp_fields) / len(exp_fields)
            similarity += field_sim * 0.3
        
        # Aggregations similarity (20% weight)
        gen_aggs = set(gen_elements["aggregations"])
        exp_aggs = set(exp_elements["aggregations"])
        if exp_aggs:
            agg_sim = len(gen_aggs & exp_aggs) / len(exp_aggs)
            similarity += agg_sim * 0.2
        
        # Operations similarity (10% weight)
        gen_ops = set(gen_elements["operations"])
        exp_ops = set(exp_elements["operations"])
        if exp_ops:
            op_sim = len(gen_ops & exp_ops) / len(exp_ops)
            similarity += op_sim * 0.1
        
        return False, similarity
    
    def normalize_value(self, value) -> str:
        """Normalize a value for comparison (handles different data types)."""
        if value is None:
            return "NULL"
        if isinstance(value, (int, float)):
            if isinstance(value, float):
                return f"{value:.2f}"
            return str(value)
        if isinstance(value, str):
            return value.strip().lower()
        if isinstance(value, dict):
            # Sort dict keys for comparison
            return json.dumps({k: self.normalize_value(v) for k, v in sorted(value.items())}, sort_keys=True)
        if isinstance(value, list):
            return json.dumps([self.normalize_value(v) for v in value], sort_keys=True)
        return str(value)
    
    def normalize_document(self, doc: Dict) -> tuple:
        """Normalize a MongoDB document for comparison."""
        # Sort keys and normalize values
        sorted_keys = sorted(doc.keys())
        return tuple(self.normalize_value(doc[key]) for key in sorted_keys)
    
    def compare_results(self, actual: Dict, expected: Dict, ignore_order: bool = True) -> Tuple[bool, str]:
        """
        Compare actual query results with expected results.
        
        Args:
            actual: Actual query results from database
            expected: Expected query results (from executing expected query)
            ignore_order: If True, ignore document order when comparing
        
        Returns:
            Tuple of (match: bool, message: str)
        """
        if not actual or not expected:
            return False, "Missing results (actual or expected is None)"
        
        # Extract documents
        actual_docs = actual.get("documents", [])
        expected_docs = expected.get("documents", [])
        
        if len(actual_docs) != len(expected_docs):
            return False, f"Document count mismatch: actual={len(actual_docs)}, expected={len(expected_docs)}"
        
        # Normalize documents for comparison
        actual_normalized = [self.normalize_document(doc) for doc in actual_docs]
        expected_normalized = [self.normalize_document(doc) for doc in expected_docs]
        
        if ignore_order:
            # Compare as sets (ignores order)
            actual_set = set(actual_normalized)
            expected_set = set(expected_normalized)
            
            if actual_set != expected_set:
                missing = expected_set - actual_set
                extra = actual_set - expected_set
                msg = f"Data mismatch (order ignored): missing {len(missing)} documents, extra {len(extra)} documents"
                if missing:
                    msg += f"\nMissing documents: {list(missing)[:3]}"
                if extra:
                    msg += f"\nExtra documents: {list(extra)[:3]}"
                return False, msg
            
            return True, "Results match (order ignored)"
        else:
            # Compare in order
            for i, (act_doc, exp_doc) in enumerate(zip(actual_normalized, expected_normalized)):
                if act_doc != exp_doc:
                    return False, f"Document {i} mismatch: actual={act_doc}, expected={exp_doc}"
            
            return True, "Results match (order preserved)"
    
    def execute_expected_query(self, query: Dict) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """Execute the expected MongoDB query to get reference results."""
        return self.mongodb_client.execute_query(query)
    
    def evaluate_test_case(self, test_case: MongoDBTestCase) -> MongoDBEvaluationResult:
        """
        Evaluate a single MongoDB test case.
        
        Args:
            test_case: MongoDB test case to evaluate
        
        Returns:
            MongoDBEvaluationResult object
        """
        result = MongoDBEvaluationResult(test_case)
        logger.info(f"Evaluating MongoDB test case: {test_case.id} - {test_case.natural_language}")
        
        try:
            # Run the workflow agent
            import time
            start_time = time.time()
            
            agent_result = self.workflow_agent.run(
                user_query=test_case.natural_language,
                conversation_history=[]
            )
            
            execution_time = (time.time() - start_time) * 1000  # Convert to ms
            result.execution_time_ms = execution_time
            
            # Extract generated query
            result.generated_query = agent_result.get("mongodb_query")
            result.retry_count = agent_result.get("retry_count", 0)
            result.validation_passed = agent_result.get("validation_error") is None
            
            # Check for errors
            if agent_result.get("execution_error"):
                result.execution_error = agent_result.get("execution_error")
                result.error_message = f"Execution error: {result.execution_error}"
            elif agent_result.get("validation_error"):
                result.error_message = f"Validation error: {agent_result.get('validation_error')}"
            
            # Get actual results
            if agent_result.get("query_results"):
                result.actual_results = agent_result.get("query_results")
                result.execution_success = True
            
            # Compare queries
            if result.generated_query:
                query_match, similarity = self.compare_queries(
                    result.generated_query,
                    test_case.expected_query
                )
                result.query_match = query_match
                result.semantic_similarity = similarity
            
            # Execute expected query and compare results
            if result.execution_success and result.generated_query:
                exp_success, exp_results, exp_error = self.execute_expected_query(test_case.expected_query)
                if exp_success and exp_results:
                    result.expected_results = exp_results
                    results_match, match_message = self.compare_results(
                        result.actual_results,
                        exp_results,
                        ignore_order=True
                    )
                    result.results_match = results_match
                    if not results_match:
                        result.error_message = f"{result.error_message or ''}; {match_message}".strip('; ')
                elif not exp_success:
                    result.error_message = f"Failed to execute expected query: {exp_error}"
            elif result.execution_success and not result.generated_query:
                result.error_message = "No MongoDB query generated by agent"
            
        except Exception as e:
            logger.error(f"Error evaluating MongoDB test case {test_case.id}: {str(e)}")
            result.error_message = f"Evaluation error: {str(e)}"
            result.execution_success = False
        
        return result
    
    def evaluate_all(
        self,
        complexity_filter: Optional[str] = None,
        category_filter: Optional[str] = None
    ) -> List[MongoDBEvaluationResult]:
        """
        Evaluate all MongoDB test cases (or filtered subset).
        
        Args:
            complexity_filter: Filter by complexity level (simple, medium, complex, very_complex)
            category_filter: Filter by category
        
        Returns:
            List of MongoDBEvaluationResult objects
        """
        # Get test cases
        if complexity_filter:
            test_cases = get_mongodb_test_cases_by_complexity(complexity_filter)
        else:
            test_cases = MONGODB_TEST_CASES
        
        if category_filter:
            test_cases = [tc for tc in test_cases if tc.category == category_filter]
        
        logger.info(f"Evaluating {len(test_cases)} MongoDB test case(s)")
        
        results = []
        for i, test_case in enumerate(test_cases, 1):
            logger.info(f"Progress: {i}/{len(test_cases)}")
            result = self.evaluate_test_case(test_case)
            results.append(result)
        
        return results
    
    def generate_report(
        self,
        results: List[MongoDBEvaluationResult],
        output_dir: Optional[Path] = None
    ) -> Dict:
        """
        Generate evaluation report with metrics.
        
        Args:
            results: List of evaluation results
            output_dir: Optional directory to save report files
        
        Returns:
            Dictionary containing report data
        """
        if not results:
            logger.warning("No results to generate report from")
            return {}
        
        # Calculate overall metrics - FOCUS ON RESULTS MATCHING
        total = len(results)
        results_matches = sum(1 for r in results if r.results_match and r.execution_success)
        execution_successes = sum(1 for r in results if r.execution_success)
        validation_passes = sum(1 for r in results if r.validation_passed)
        queries_generated = sum(1 for r in results if r.generated_query is not None)
        
        avg_execution_time = sum(r.execution_time_ms for r in results) / total if total > 0 else 0.0
        avg_retries = sum(r.retry_count for r in results) / total if total > 0 else 0.0
        
        # Metrics by complexity
        complexity_metrics = {}
        for complexity in ["simple", "medium", "complex", "very_complex"]:
            comp_results = [r for r in results if r.test_case.complexity == complexity]
            if comp_results:
                comp_total = len(comp_results)
                comp_results_matches = sum(1 for r in comp_results if r.results_match and r.execution_success)
                comp_exec_success = sum(1 for r in comp_results if r.execution_success)
                
                complexity_metrics[complexity] = {
                    "total": comp_total,
                    "results_match_count": comp_results_matches,
                    "results_match_rate": comp_results_matches / comp_total if comp_total > 0 else 0.0,
                    "execution_success_rate": comp_exec_success / comp_total if comp_total > 0 else 0.0
                }
        
        # Metrics by category
        category_metrics = {}
        categories = set(r.test_case.category for r in results)
        for category in categories:
            cat_results = [r for r in results if r.test_case.category == category]
            if cat_results:
                cat_total = len(cat_results)
                cat_results_matches = sum(1 for r in cat_results if r.results_match and r.execution_success)
                cat_exec_success = sum(1 for r in cat_results if r.execution_success)
                
                category_metrics[category] = {
                    "total": cat_total,
                    "results_match_count": cat_results_matches,
                    "results_match_rate": cat_results_matches / cat_total if cat_total > 0 else 0.0,
                    "execution_success_rate": cat_exec_success / cat_total if cat_total > 0 else 0.0
                }
        
        # Build report
        report = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_test_cases": total,
                "queries_generated_count": queries_generated,
                "queries_generated_rate": queries_generated / total if total > 0 else 0.0,
                "results_match_count": results_matches,
                "results_match_rate": results_matches / total if total > 0 else 0.0,
                "execution_success_count": execution_successes,
                "execution_success_rate": execution_successes / total if total > 0 else 0.0,
                "validation_pass_count": validation_passes,
                "validation_pass_rate": validation_passes / total if total > 0 else 0.0,
                "avg_execution_time_ms": avg_execution_time,
                "avg_retry_count": avg_retries
            },
            "by_complexity": complexity_metrics,
            "by_category": category_metrics,
            "detailed_results": [r.to_dict() for r in results]
        }
        
        # Save report if output directory provided
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Save JSON report
            json_file = output_dir / f"mongodb_evaluation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(json_file, 'w') as f:
                json.dump(report, f, indent=2)
            logger.info(f"JSON report saved to {json_file}")
            
            # Save CSV summary
            csv_file = output_dir / f"mongodb_evaluation_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            df = pd.DataFrame([r.to_dict() for r in results])
            df.to_csv(csv_file, index=False)
            logger.info(f"CSV results saved to {csv_file}")
        
        return report
