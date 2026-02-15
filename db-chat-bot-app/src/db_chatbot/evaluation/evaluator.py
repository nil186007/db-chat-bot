"""
Evaluation runner for SQL query generation accuracy testing.
"""
import json
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
import pandas as pd

from db_chatbot.config.settings import get_logger
from db_chatbot.evaluation.test_cases import TestCase, get_test_cases_by_complexity, TEST_CASES
from db_chatbot.agents.workflow_agent import WorkflowAgent
from db_chatbot.query_generator.sql_generator import SQLGenerator
from db_chatbot.query_generator.response_generator import ResponseGenerator
from db_chatbot.db_clients.postgres_client import PostgresClient
from db_chatbot.rag.schema_rag import SchemaRAG
from db_chatbot.query_intent.classifier import QueryClassifier

logger = get_logger(__name__)


class SQLNormalizer:
    """Normalize SQL queries for comparison."""
    
    @staticmethod
    def normalize(sql: str) -> str:
        """
        Normalize SQL query for comparison.
        - Remove extra whitespace
        - Convert to lowercase
        - Remove semicolons
        - Normalize whitespace
        """
        if not sql:
            return ""
        
        # Remove semicolons
        sql = sql.rstrip(';')
        
        # Convert to lowercase
        sql = sql.lower()
        
        # Remove extra whitespace and newlines
        sql = re.sub(r'\s+', ' ', sql)
        
        # Remove leading/trailing whitespace
        sql = sql.strip()
        
        return sql
    
    @staticmethod
    def extract_key_elements(sql: str) -> Dict[str, List[str]]:
        """
        Extract key elements from SQL query for semantic comparison.
        Returns dict with: tables, columns, conditions, aggregations
        """
        normalized = SQLNormalizer.normalize(sql)
        
        # Extract table names (FROM and JOIN clauses)
        tables = []
        from_match = re.search(r'from\s+(\w+)', normalized)
        if from_match:
            tables.append(from_match.group(1))
        
        join_matches = re.findall(r'join\s+(\w+)', normalized)
        tables.extend(join_matches)
        
        # Extract column names (SELECT clause)
        select_match = re.search(r'select\s+(.+?)\s+from', normalized, re.DOTALL)
        columns = []
        if select_match:
            select_clause = select_match.group(1)
            # Simple extraction - split by comma
            cols = [col.strip().split()[0] for col in select_clause.split(',')]
            columns = [col for col in cols if col and col != '*']
        
        # Extract WHERE conditions
        where_match = re.search(r'where\s+(.+?)(?:\s+group\s+by|\s+order\s+by|\s+having|\s+limit|$)', normalized, re.DOTALL)
        conditions = []
        if where_match:
            conditions.append(where_match.group(1).strip())
        
        # Extract aggregations
        aggregations = []
        agg_patterns = ['count', 'sum', 'avg', 'max', 'min']
        for pattern in agg_patterns:
            if pattern in normalized:
                aggregations.append(pattern)
        
        return {
            "tables": list(set(tables)),
            "columns": list(set(columns)),
            "conditions": conditions,
            "aggregations": list(set(aggregations))
        }


class EvaluationResult:
    """Represents the result of evaluating a single test case."""
    
    def __init__(self, test_case: TestCase):
        self.test_case = test_case
        self.generated_sql: Optional[str] = None
        self.execution_success: bool = False
        self.execution_error: Optional[str] = None
        self.expected_results: Optional[Dict] = None
        self.actual_results: Optional[Dict] = None
        self.sql_match: bool = False
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
            "expected_sql": self.test_case.expected_sql,
            "generated_sql": self.generated_sql,
            "complexity": self.test_case.complexity,
            "category": self.test_case.category,
            "sql_match": self.sql_match,
            "results_match": self.results_match,
            "semantic_similarity": self.semantic_similarity,
            "execution_success": self.execution_success,
            "execution_error": self.execution_error,
            "execution_time_ms": self.execution_time_ms,
            "retry_count": self.retry_count,
            "validation_passed": self.validation_passed,
            "error_message": self.error_message
        }


class SQLQueryEvaluator:
    """Evaluator for SQL query generation accuracy."""
    
    def __init__(
        self,
        db_client: PostgresClient,
        sql_generator: SQLGenerator,
        schema_rag: SchemaRAG,
        response_generator: Optional[ResponseGenerator] = None,
        query_classifier: Optional[QueryClassifier] = None
    ):
        """
        Initialize the evaluator.
        
        Args:
            db_client: PostgreSQL client instance
            sql_generator: SQL generator instance
            schema_rag: Schema RAG instance
            response_generator: Response generator (optional)
            query_classifier: Query classifier (optional)
        """
        self.db_client = db_client
        self.sql_generator = sql_generator
        self.schema_rag = schema_rag
        self.response_generator = response_generator
        self.query_classifier = query_classifier
        
        # Initialize workflow agent
        self.workflow_agent = WorkflowAgent(
            sql_generator=sql_generator,
            db_client=db_client,
            schema_rag=schema_rag,
            response_generator=response_generator,
            query_classifier=query_classifier,
            max_retries=3
        )
        
        logger.info("SQLQueryEvaluator initialized")
    
    def normalize_sql(self, sql: str) -> str:
        """Normalize SQL for comparison."""
        return SQLNormalizer.normalize(sql)
    
    def compare_sql_queries(self, generated: str, expected: str) -> Tuple[bool, float]:
        """
        Compare generated SQL with expected SQL.
        
        Returns:
            Tuple of (exact_match: bool, similarity_score: float)
        """
        if not generated:
            return False, 0.0
        
        gen_norm = self.normalize_sql(generated)
        exp_norm = self.normalize_sql(expected)
        
        # Exact match
        if gen_norm == exp_norm:
            return True, 1.0
        
        # Semantic similarity
        gen_elements = SQLNormalizer.extract_key_elements(generated)
        exp_elements = SQLNormalizer.extract_key_elements(expected)
        
        # Calculate similarity based on key elements
        similarity = 0.0
        
        # Tables similarity (40% weight)
        gen_tables = set(gen_elements["tables"])
        exp_tables = set(exp_elements["tables"])
        if exp_tables:
            table_sim = len(gen_tables & exp_tables) / len(exp_tables)
            similarity += table_sim * 0.4
        
        # Columns similarity (30% weight)
        gen_cols = set(gen_elements["columns"])
        exp_cols = set(exp_elements["columns"])
        if exp_cols:
            col_sim = len(gen_cols & exp_cols) / len(exp_cols)
            similarity += col_sim * 0.3
        
        # Aggregations similarity (20% weight)
        gen_aggs = set(gen_elements["aggregations"])
        exp_aggs = set(exp_elements["aggregations"])
        if exp_aggs:
            agg_sim = len(gen_aggs & exp_aggs) / len(exp_aggs)
            similarity += agg_sim * 0.2
        
        # Conditions similarity (10% weight)
        # Simple check if WHERE clause exists
        has_where_gen = "where" in gen_norm
        has_where_exp = "where" in exp_norm
        if has_where_exp:
            cond_sim = 1.0 if has_where_gen == has_where_exp else 0.0
            similarity += cond_sim * 0.1
        
        return False, similarity
    
    def normalize_value(self, value) -> str:
        """Normalize a value for comparison (handles different data types)."""
        if value is None:
            return "NULL"
        if isinstance(value, (int, float)):
            # Round floats to 2 decimal places for comparison
            if isinstance(value, float):
                return f"{value:.2f}"
            return str(value)
        if isinstance(value, str):
            return value.strip().lower()
        return str(value)
    
    def normalize_row(self, row: tuple, columns: List[str]) -> tuple:
        """Normalize a row for comparison."""
        return tuple(self.normalize_value(val) for val in row)
    
    def compare_results(self, actual: Dict, expected: Dict, ignore_order: bool = True) -> Tuple[bool, str]:
        """
        Compare actual query results with expected results.
        
        Args:
            actual: Actual query results from database
            expected: Expected query results (from executing expected SQL)
            ignore_order: If True, ignore row order when comparing
        
        Returns:
            Tuple of (match: bool, message: str)
        """
        if not actual or not expected:
            return False, "Missing results (actual or expected is None)"
        
        # Compare row counts
        actual_rows = actual.get("rows", [])
        expected_rows = expected.get("rows", [])
        
        if len(actual_rows) != len(expected_rows):
            return False, f"Row count mismatch: actual={len(actual_rows)}, expected={len(expected_rows)}"
        
        # Compare columns
        actual_cols = list(actual.get("columns", []))
        expected_cols = list(expected.get("columns", []))
        
        # Normalize column names (case-insensitive)
        actual_cols_norm = [col.lower() for col in actual_cols]
        expected_cols_norm = [col.lower() for col in expected_cols]
        
        if set(actual_cols_norm) != set(expected_cols_norm):
            return False, f"Column mismatch: actual={set(actual_cols_norm)}, expected={set(expected_cols_norm)}"
        
        # Reorder columns if needed to match expected order
        if actual_cols_norm != expected_cols_norm:
            col_mapping = {actual_cols_norm[i]: i for i in range(len(actual_cols_norm))}
            reordered_actual = []
            for row in actual_rows:
                reordered_row = tuple(row[col_mapping[col]] for col in expected_cols_norm)
                reordered_actual.append(reordered_row)
            actual_rows = reordered_actual
        
        # Normalize rows for comparison
        actual_normalized = [self.normalize_row(row, expected_cols) for row in actual_rows]
        expected_normalized = [self.normalize_row(row, expected_cols) for row in expected_rows]
        
        if ignore_order:
            # Compare as sets (ignores order)
            actual_set = set(actual_normalized)
            expected_set = set(expected_normalized)
            
            if actual_set != expected_set:
                missing = expected_set - actual_set
                extra = actual_set - expected_set
                msg = f"Data mismatch (order ignored): missing {len(missing)} rows, extra {len(extra)} rows"
                if missing:
                    msg += f"\nMissing rows: {list(missing)[:3]}"
                if extra:
                    msg += f"\nExtra rows: {list(extra)[:3]}"
                return False, msg
            
            return True, "Results match (order ignored)"
        else:
            # Compare in order
            for i, (act_row, exp_row) in enumerate(zip(actual_normalized, expected_normalized)):
                if act_row != exp_row:
                    return False, f"Row {i} mismatch: actual={act_row}, expected={exp_row}"
            
            return True, "Results match (order preserved)"
    
    def execute_expected_sql(self, sql: str) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """Execute the expected SQL to get reference results."""
        return self.db_client.execute_query(sql)
    
    def evaluate_test_case(self, test_case: TestCase) -> EvaluationResult:
        """
        Evaluate a single test case.
        
        Args:
            test_case: Test case to evaluate
        
        Returns:
            EvaluationResult object
        """
        result = EvaluationResult(test_case)
        logger.info(f"Evaluating test case: {test_case.id} - {test_case.natural_language}")
        
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
            
            # Extract generated SQL
            result.generated_sql = agent_result.get("sql_query")
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
            
            # Compare SQL queries
            if result.generated_sql:
                sql_match, similarity = self.compare_sql_queries(
                    result.generated_sql,
                    test_case.expected_sql
                )
                result.sql_match = sql_match
                result.semantic_similarity = similarity
            
            # Execute expected SQL and compare results
            if result.execution_success and result.generated_sql:
                exp_success, exp_results, exp_error = self.execute_expected_sql(test_case.expected_sql)
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
                    result.error_message = f"Failed to execute expected SQL: {exp_error}"
            elif result.execution_success and not result.generated_sql:
                result.error_message = "No SQL generated by agent"
            
        except Exception as e:
            logger.error(f"Error evaluating test case {test_case.id}: {str(e)}")
            result.error_message = f"Evaluation error: {str(e)}"
            result.execution_success = False
        
        return result
    
    def evaluate_all(
        self,
        complexity_filter: Optional[str] = None,
        category_filter: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[EvaluationResult]:
        """
        Evaluate all test cases (or filtered subset).
        
        Args:
            complexity_filter: Filter by complexity level (simple, medium, complex, very_complex)
            category_filter: Filter by category
            limit: Max number of test cases to run (for quick testing). None = run all.
        
        Returns:
            List of EvaluationResult objects
        """
        # Get test cases
        if complexity_filter:
            test_cases = get_test_cases_by_complexity(complexity_filter)
        else:
            test_cases = TEST_CASES
        
        if category_filter:
            test_cases = [tc for tc in test_cases if tc.category == category_filter]
        
        if limit is not None and limit > 0:
            test_cases = test_cases[:limit]
            logger.info(f"Quick test mode: evaluating first {len(test_cases)} test case(s)")
        
        logger.info(f"Evaluating {len(test_cases)} test case(s)")
        
        results = []
        for i, test_case in enumerate(test_cases, 1):
            logger.info(f"Progress: {i}/{len(test_cases)}")
            result = self.evaluate_test_case(test_case)
            results.append(result)
        
        return results
    
    def generate_report(
        self,
        results: List[EvaluationResult],
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
        sql_generated = sum(1 for r in results if r.generated_sql is not None)
        
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
                "sql_generated_count": sql_generated,
                "sql_generated_rate": sql_generated / total if total > 0 else 0.0,
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
            json_file = output_dir / f"evaluation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(json_file, 'w') as f:
                json.dump(report, f, indent=2)
            logger.info(f"JSON report saved to {json_file}")
            
            # Save CSV summary
            csv_file = output_dir / f"evaluation_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            df = pd.DataFrame([r.to_dict() for r in results])
            df.to_csv(csv_file, index=False)
            logger.info(f"CSV results saved to {csv_file}")
        
        return report
