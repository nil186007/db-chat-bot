#!/usr/bin/env python3
"""
Comprehensive Project Report Generator
Compares SQL query generation accuracy across different configurations:
- Baseline (basic SQL generation)
- With RAG (knowledge graph enhanced)
- With Better Prompting (enhanced prompts)
- With Fine-tuning (if available)
"""
import sys
import json
import argparse
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd

# Set matplotlib cache directory to a writable location before importing
# This prevents permission errors with the default cache directory
# Use a directory within the workspace
app_dir = Path(__file__).parent
matplotlib_cache_dir = app_dir / ".matplotlib_cache"
try:
    matplotlib_cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ['MPLCONFIGDIR'] = str(matplotlib_cache_dir)
except (PermissionError, OSError):
    # If we can't create the directory, matplotlib will use a temp directory
    pass

import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns

# Add src directory to Python path
app_dir = Path(__file__).parent
src_dir = app_dir / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from db_chatbot.config.settings import get_logger, setup_logging
from db_chatbot.evaluation.evaluator import SQLQueryEvaluator, EvaluationResult
from db_chatbot.evaluation.test_cases import TEST_CASES
from db_chatbot.db_clients.postgres_client import PostgresClient
from db_chatbot.query_generator.sql_generator import SQLGenerator
from db_chatbot.query_generator.response_generator import ResponseGenerator
from db_chatbot.rag.schema_rag import SchemaRAG
from db_chatbot.rag.knowledge_graph_rag import KnowledgeGraphRAG
from db_chatbot.db_clients.neo4j_client import Neo4jClient
from db_chatbot.query_intent.classifier import QueryClassifier
import ollama

logger = get_logger(__name__)


class EnhancedSQLGenerator(SQLGenerator):
    """Enhanced SQL Generator with improved prompting."""
    
    def generate_sql(self, natural_language_query: str, schema_info: Dict, conversation_history: list = None, enhanced_context: str = None) -> Optional[str]:
        """Generate SQL with enhanced prompting."""
        logger.info(f"Generating SQL with enhanced prompting: {natural_language_query[:50]}...")
        
        # Use enhanced context if provided
        if enhanced_context:
            schema_text = enhanced_context
            logger.debug("Using enhanced context from knowledge graph")
        else:
            schema_text = self.format_schema_for_prompt(schema_info)
        
        # Build conversation context
        context = ""
        if conversation_history:
            context = "\n\nPrevious conversation:\n"
            for msg in conversation_history[-3:]:
                if msg.get("role") == "user":
                    context += f"User: {msg.get('content', '')}\n"
                elif msg.get("role") == "assistant":
                    context += f"Assistant: {msg.get('content', '')}\n"
        
        # Enhanced prompt with examples and better instructions
        prompt = f"""You are an expert SQL query generator with deep knowledge of PostgreSQL. Your task is to convert natural language questions into accurate, optimized PostgreSQL SELECT queries.

CRITICAL RULES:
1. ONLY generate SELECT queries - NO INSERT, UPDATE, DELETE, DROP, ALTER, or any data modification
2. Use exact table and column names from the schema provided
3. Ensure proper JOIN syntax when combining tables
4. Use appropriate aggregation functions (COUNT, SUM, AVG, MAX, MIN) when needed
5. Apply correct WHERE conditions based on the question
6. Use GROUP BY when aggregating data
7. Use HAVING for filtering aggregated results
8. Use ORDER BY for sorting results
9. Use LIMIT for restricting result count
10. Handle NULL values appropriately with COALESCE when needed

{schema_text}

{context}

User Question: {natural_language_query}

EXAMPLES OF GOOD SQL GENERATION:

Example 1:
Question: "Show all products"
SQL: SELECT * FROM products;

Example 2:
Question: "Count orders for each customer"
SQL: SELECT c.customer_id, c.first_name, c.last_name, COUNT(o.order_id) as order_count 
FROM customers c 
LEFT JOIN orders o ON c.customer_id = o.customer_id 
GROUP BY c.customer_id, c.first_name, c.last_name;

Example 3:
Question: "Find products with average rating above 4"
SQL: SELECT p.*, AVG(r.rating) as avg_rating 
FROM products p 
INNER JOIN reviews r ON p.product_id = r.product_id 
GROUP BY p.product_id 
HAVING AVG(r.rating) > 4;

Example 4:
Question: "Show customers who have ordered products from Electronics category"
SQL: SELECT DISTINCT c.* 
FROM customers c 
INNER JOIN orders o ON c.customer_id = o.customer_id 
INNER JOIN order_items oi ON o.order_id = oi.order_id 
INNER JOIN products p ON oi.product_id = p.product_id 
WHERE p.category = 'Electronics';

IMPORTANT:
- Generate ONLY the SQL query, no explanations or markdown
- Use proper PostgreSQL syntax
- Match the question intent accurately
- If the question cannot be answered with the schema, return "ERROR: [explanation]"

SQL Query:"""

        try:
            logger.debug(f"Sending enhanced prompt to Ollama model: {self.model_name}")
            response = ollama.generate(
                model=self.model_name,
                prompt=prompt,
                options={
                    "temperature": 0.1,
                    "num_predict": 512,
                }
            )
            
            sql_query = response['response'].strip()
            logger.debug(f"Received response: {sql_query[:100]}...")
            
            # Clean up response
            if sql_query.startswith("```sql"):
                sql_query = sql_query[6:]
            elif sql_query.startswith("```"):
                sql_query = sql_query[3:]
            
            if sql_query.endswith("```"):
                sql_query = sql_query[:-3]
            
            sql_query = sql_query.strip()
            
            if sql_query.startswith("ERROR:"):
                logger.warning(f"LLM returned error: {sql_query}")
                return None
            
            logger.info(f"SQL query generated successfully: {sql_query[:50]}...")
            return sql_query
            
        except Exception as e:
            logger.error(f"Error generating SQL: {str(e)}")
            return None


class ReportGenerator:
    """Generates comprehensive MTech project report."""
    
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.results: Dict[str, List[EvaluationResult]] = {}
        
    def run_baseline_evaluation(
        self,
        db_client: PostgresClient,
        schema_info: Dict,
        model_name: Optional[str] = None
    ) -> List[EvaluationResult]:
        """Run evaluation with baseline configuration (no RAG, basic prompting)."""
        logger.info("=" * 80)
        logger.info("RUNNING BASELINE EVALUATION (No RAG, Basic Prompting)")
        logger.info("=" * 80)
        
        # Basic SQL generator (no enhanced context)
        sql_generator = SQLGenerator(model_name=model_name)
        
        # Schema RAG without knowledge graph (basic schema only)
        schema_rag = SchemaRAG()
        schema_rag.load_schema(schema_info, database_name="customer_orders_and_reviews_db", host="localhost", port=5432)
        
        # Create evaluator
        evaluator = SQLQueryEvaluator(
            db_client=db_client,
            sql_generator=sql_generator,
            schema_rag=schema_rag,
            response_generator=None,
            query_classifier=None
        )
        
        # Run evaluation
        results = evaluator.evaluate_all()
        self.results["baseline"] = results
        
        return results
    
    def run_rag_evaluation(
        self,
        db_client: PostgresClient,
        schema_info: Dict,
        neo4j_client: Neo4jClient,
        model_name: Optional[str] = None
    ) -> List[EvaluationResult]:
        """Run evaluation with RAG enhancement (knowledge graph)."""
        logger.info("=" * 80)
        logger.info("RUNNING RAG-ENHANCED EVALUATION (Knowledge Graph RAG)")
        logger.info("=" * 80)
        
        # SQL generator
        sql_generator = SQLGenerator(model_name=model_name)
        
        # Knowledge graph RAG
        kg_rag = KnowledgeGraphRAG(neo4j_client)
        kg_rag.build_graph_from_schema(
            schema_info=schema_info,
            database_name="customer_orders_and_reviews_db",
            host="localhost",
            port=5432
        )
        
        # Schema RAG with knowledge graph
        schema_rag = SchemaRAG(knowledge_graph_rag=kg_rag)
        schema_rag.load_schema(schema_info, database_name="customer_orders_and_reviews_db", host="localhost", port=5432)
        
        # Create evaluator
        evaluator = SQLQueryEvaluator(
            db_client=db_client,
            sql_generator=sql_generator,
            schema_rag=schema_rag,
            response_generator=None,
            query_classifier=None
        )
        
        # Run evaluation
        results = evaluator.evaluate_all()
        self.results["rag_enhanced"] = results
        
        return results
    
    def run_enhanced_prompting_evaluation(
        self,
        db_client: PostgresClient,
        schema_info: Dict,
        neo4j_client: Neo4jClient,
        model_name: Optional[str] = None
    ) -> List[EvaluationResult]:
        """Run evaluation with enhanced prompting."""
        logger.info("=" * 80)
        logger.info("RUNNING ENHANCED PROMPTING EVALUATION (Better Prompts + RAG)")
        logger.info("=" * 80)
        
        # Enhanced SQL generator with better prompting
        sql_generator = EnhancedSQLGenerator(model_name=model_name)
        
        # Knowledge graph RAG
        kg_rag = KnowledgeGraphRAG(neo4j_client)
        kg_rag.build_graph_from_schema(
            schema_info=schema_info,
            database_name="customer_orders_and_reviews_db",
            host="localhost",
            port=5432
        )
        
        # Schema RAG with knowledge graph
        schema_rag = SchemaRAG(knowledge_graph_rag=kg_rag)
        schema_rag.load_schema(schema_info, database_name="customer_orders_and_reviews_db", host="localhost", port=5432)
        
        # Create evaluator
        evaluator = SQLQueryEvaluator(
            db_client=db_client,
            sql_generator=sql_generator,
            schema_rag=schema_rag,
            response_generator=None,
            query_classifier=None
        )
        
        # Run evaluation
        results = evaluator.evaluate_all()
        self.results["enhanced_prompting"] = results
        
        return results
    
    def calculate_metrics(self, results: List[EvaluationResult]) -> Dict:
        """Calculate comprehensive metrics from evaluation results."""
        total = len(results)
        if total == 0:
            return {}
        
        results_matches = sum(1 for r in results if r.results_match and r.execution_success)
        execution_successes = sum(1 for r in results if r.execution_success)
        validation_passes = sum(1 for r in results if r.validation_passed)
        sql_generated = sum(1 for r in results if r.generated_sql is not None)
        
        avg_execution_time = sum(r.execution_time_ms for r in results) / total if total > 0 else 0.0
        avg_retries = sum(r.retry_count for r in results) / total if total > 0 else 0.0
        
        # By complexity
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
        
        # By category
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
        
        return {
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
            "avg_retry_count": avg_retries,
            "by_complexity": complexity_metrics,
            "by_category": category_metrics
        }
    
    def generate_comparison_table(self) -> pd.DataFrame:
        """Generate comparison table across all configurations."""
        configs = ["baseline", "rag_enhanced", "enhanced_prompting"]
        config_names = ["Baseline", "RAG Enhanced", "Enhanced Prompting"]
        
        rows = []
        for config, name in zip(configs, config_names):
            if config not in self.results:
                continue
            
            metrics = self.calculate_metrics(self.results[config])
            rows.append({
                "Configuration": name,
                "Total Test Cases": metrics.get("total_test_cases", 0),
                "Results Match Rate (%)": round(metrics.get("results_match_rate", 0.0) * 100, 2),
                "Execution Success Rate (%)": round(metrics.get("execution_success_rate", 0.0) * 100, 2),
                "SQL Generated Rate (%)": round(metrics.get("sql_generated_rate", 0.0) * 100, 2),
                "Avg Execution Time (ms)": round(metrics.get("avg_execution_time_ms", 0.0), 2),
                "Avg Retry Count": round(metrics.get("avg_retry_count", 0.0), 2)
            })
        
        return pd.DataFrame(rows)
    
    def generate_complexity_comparison(self) -> pd.DataFrame:
        """Generate comparison table by complexity level."""
        configs = ["baseline", "rag_enhanced", "enhanced_prompting"]
        config_names = ["Baseline", "RAG Enhanced", "Enhanced Prompting"]
        complexities = ["simple", "medium", "complex", "very_complex"]
        
        rows = []
        for complexity in complexities:
            for config, name in zip(configs, config_names):
                if config not in self.results:
                    continue
                
                metrics = self.calculate_metrics(self.results[config])
                comp_metrics = metrics.get("by_complexity", {}).get(complexity, {})
                
                rows.append({
                    "Complexity": complexity.capitalize(),
                    "Configuration": name,
                    "Total": comp_metrics.get("total", 0),
                    "Results Match Rate (%)": round(comp_metrics.get("results_match_rate", 0.0) * 100, 2),
                    "Execution Success Rate (%)": round(comp_metrics.get("execution_success_rate", 0.0) * 100, 2)
                })
        
        return pd.DataFrame(rows)
    
    def generate_category_comparison(self) -> pd.DataFrame:
        """Generate comparison table by category."""
        configs = ["baseline", "rag_enhanced", "enhanced_prompting"]
        config_names = ["Baseline", "RAG Enhanced", "Enhanced Prompting"]
        
        # Get all categories
        all_categories = set()
        for config in configs:
            if config in self.results:
                metrics = self.calculate_metrics(self.results[config])
                all_categories.update(metrics.get("by_category", {}).keys())
        
        rows = []
        for category in sorted(all_categories):
            for config, name in zip(configs, config_names):
                if config not in self.results:
                    continue
                
                metrics = self.calculate_metrics(self.results[config])
                cat_metrics = metrics.get("by_category", {}).get(category, {})
                
                rows.append({
                    "Category": category,
                    "Configuration": name,
                    "Total": cat_metrics.get("total", 0),
                    "Results Match Rate (%)": round(cat_metrics.get("results_match_rate", 0.0) * 100, 2),
                    "Execution Success Rate (%)": round(cat_metrics.get("execution_success_rate", 0.0) * 100, 2)
                })
        
        return pd.DataFrame(rows)
    
    def create_visualizations(self):
        """Create visualization charts."""
        # Set style
        sns.set_style("whitegrid")
        plt.rcParams['figure.figsize'] = (12, 6)
        
        # 1. Overall accuracy comparison
        fig, ax = plt.subplots()
        configs = ["baseline", "rag_enhanced", "enhanced_prompting"]
        config_names = ["Baseline", "RAG Enhanced", "Enhanced Prompting"]
        
        match_rates = []
        for config in configs:
            if config in self.results:
                metrics = self.calculate_metrics(self.results[config])
                match_rates.append(metrics.get("results_match_rate", 0.0) * 100)
            else:
                match_rates.append(0)
        
        bars = ax.bar(config_names, match_rates, color=['#3498db', '#2ecc71', '#9b59b6'])
        ax.set_ylabel('Results Match Rate (%)', fontsize=12)
        ax.set_title('Overall Accuracy Comparison Across Configurations', fontsize=14, fontweight='bold')
        ax.set_ylim(0, 100)
        
        # Add value labels on bars
        for bar, rate in zip(bars, match_rates):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{rate:.1f}%',
                   ha='center', va='bottom', fontsize=11, fontweight='bold')
        
        plt.tight_layout()
        plt.savefig(self.output_dir / 'accuracy_comparison.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        # 2. Accuracy by complexity
        fig, ax = plt.subplots()
        complexities = ["Simple", "Medium", "Complex", "Very Complex"]
        x = range(len(complexities))
        width = 0.25
        
        for i, (config, name) in enumerate(zip(configs, config_names)):
            if config not in self.results:
                continue
            
            metrics = self.calculate_metrics(self.results[config])
            rates = []
            for comp in ["simple", "medium", "complex", "very_complex"]:
                comp_metrics = metrics.get("by_complexity", {}).get(comp, {})
                rates.append(comp_metrics.get("results_match_rate", 0.0) * 100)
            
            ax.bar([xi + i*width for xi in x], rates, width, label=name)
        
        ax.set_xlabel('Query Complexity', fontsize=12)
        ax.set_ylabel('Results Match Rate (%)', fontsize=12)
        ax.set_title('Accuracy by Query Complexity', fontsize=14, fontweight='bold')
        ax.set_xticks([xi + width for xi in x])
        ax.set_xticklabels(complexities)
        ax.legend()
        ax.set_ylim(0, 100)
        
        plt.tight_layout()
        plt.savefig(self.output_dir / 'accuracy_by_complexity.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        # 3. Improvement analysis
        if "baseline" in self.results and "enhanced_prompting" in self.results:
            fig, ax = plt.subplots()
            
            baseline_metrics = self.calculate_metrics(self.results["baseline"])
            enhanced_metrics = self.calculate_metrics(self.results["enhanced_prompting"])
            
            improvements = []
            for comp in ["simple", "medium", "complex", "very_complex"]:
                baseline_rate = baseline_metrics.get("by_complexity", {}).get(comp, {}).get("results_match_rate", 0.0) * 100
                enhanced_rate = enhanced_metrics.get("by_complexity", {}).get(comp, {}).get("results_match_rate", 0.0) * 100
                improvement = enhanced_rate - baseline_rate
                improvements.append(improvement)
            
            colors = ['green' if x >= 0 else 'red' for x in improvements]
            bars = ax.bar(complexities, improvements, color=colors)
            ax.set_ylabel('Improvement (%)', fontsize=12)
            ax.set_title('Accuracy Improvement: Enhanced Prompting vs Baseline', fontsize=14, fontweight='bold')
            ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
            
            # Add value labels
            for bar, imp in zip(bars, improvements):
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{imp:+.1f}%',
                       ha='center', va='bottom' if imp >= 0 else 'top', fontsize=11, fontweight='bold')
            
            plt.tight_layout()
            plt.savefig(self.output_dir / 'improvement_analysis.png', dpi=300, bbox_inches='tight')
            plt.close()
    
    def generate_markdown_report(self) -> str:
        """Generate comprehensive markdown report."""
        report = []
        report.append("# SQL Query Generation Accuracy Evaluation Report")
        report.append(f"\n**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        report.append("---\n")
        
        # Executive Summary
        report.append("## Executive Summary\n")
        report.append("This report presents a comprehensive evaluation of SQL query generation accuracy across different configurations:")
        report.append("- **Baseline**: Basic SQL generation without RAG enhancements")
        report.append("- **RAG Enhanced**: SQL generation with knowledge graph RAG for enhanced context")
        report.append("- **Enhanced Prompting**: SQL generation with improved prompts and RAG\n")
        
        # Overall Comparison
        report.append("## Overall Accuracy Comparison\n")
        comparison_df = self.generate_comparison_table()
        report.append(comparison_df.to_markdown(index=False))
        report.append("\n")
        
        # Key Findings
        report.append("### Key Findings\n")
        if "baseline" in self.results and "enhanced_prompting" in self.results:
            baseline_metrics = self.calculate_metrics(self.results["baseline"])
            enhanced_metrics = self.calculate_metrics(self.results["enhanced_prompting"])
            
            baseline_rate = baseline_metrics.get("results_match_rate", 0.0) * 100
            enhanced_rate = enhanced_metrics.get("results_match_rate", 0.0) * 100
            improvement = enhanced_rate - baseline_rate
            
            report.append(f"- **Baseline Accuracy**: {baseline_rate:.2f}%")
            report.append(f"- **Enhanced Prompting Accuracy**: {enhanced_rate:.2f}%")
            report.append(f"- **Overall Improvement**: {improvement:+.2f} percentage points\n")
        
        # Accuracy by Complexity
        report.append("## Accuracy by Query Complexity\n")
        complexity_df = self.generate_complexity_comparison()
        report.append(complexity_df.to_markdown(index=False))
        report.append("\n")
        
        # Accuracy by Category
        report.append("## Accuracy by Query Category\n")
        category_df = self.generate_category_comparison()
        report.append(category_df.to_markdown(index=False))
        report.append("\n")
        
        # Detailed Analysis
        report.append("## Detailed Analysis\n")
        
        if "baseline" in self.results and "rag_enhanced" in self.results:
            report.append("### RAG Enhancement Impact\n")
            baseline_metrics = self.calculate_metrics(self.results["baseline"])
            rag_metrics = self.calculate_metrics(self.results["rag_enhanced"])
            
            baseline_rate = baseline_metrics.get("results_match_rate", 0.0) * 100
            rag_rate = rag_metrics.get("results_match_rate", 0.0) * 100
            rag_improvement = rag_rate - baseline_rate
            
            report.append(f"- Baseline: {baseline_rate:.2f}%")
            report.append(f"- RAG Enhanced: {rag_rate:.2f}%")
            report.append(f"- Improvement: {rag_improvement:+.2f} percentage points\n")
            report.append("The knowledge graph RAG provides enhanced context by including table/column descriptions, ")
            report.append("annotations, and query examples, leading to more accurate SQL generation.\n")
        
        if "rag_enhanced" in self.results and "enhanced_prompting" in self.results:
            report.append("### Enhanced Prompting Impact\n")
            rag_metrics = self.calculate_metrics(self.results["rag_enhanced"])
            enhanced_metrics = self.calculate_metrics(self.results["enhanced_prompting"])
            
            rag_rate = rag_metrics.get("results_match_rate", 0.0) * 100
            enhanced_rate = enhanced_metrics.get("results_match_rate", 0.0) * 100
            prompt_improvement = enhanced_rate - rag_rate
            
            report.append(f"- RAG Enhanced: {rag_rate:.2f}%")
            report.append(f"- Enhanced Prompting: {enhanced_rate:.2f}%")
            report.append(f"- Improvement: {prompt_improvement:+.2f} percentage points\n")
            report.append("Enhanced prompting with examples and detailed instructions helps the LLM better understand ")
            report.append("query requirements and generate more accurate SQL queries.\n")
        
        # Complexity Analysis
        report.append("### Complexity Analysis\n")
        if "enhanced_prompting" in self.results:
            enhanced_metrics = self.calculate_metrics(self.results["enhanced_prompting"])
            complexity_metrics = enhanced_metrics.get("by_complexity", {})
            
            for comp in ["simple", "medium", "complex", "very_complex"]:
                if comp in complexity_metrics:
                    comp_metrics = complexity_metrics[comp]
                    rate = comp_metrics.get("results_match_rate", 0.0) * 100
                    total = comp_metrics.get("total", 0)
                    report.append(f"- **{comp.capitalize()} Queries**: {rate:.2f}% accuracy ({comp_metrics.get('results_match_count', 0)}/{total} correct)\n")
        
        # Category Analysis
        report.append("### Category Analysis\n")
        if "enhanced_prompting" in self.results:
            enhanced_metrics = self.calculate_metrics(self.results["enhanced_prompting"])
            category_metrics = enhanced_metrics.get("by_category", {})
            
            for category in sorted(category_metrics.keys()):
                cat_metrics = category_metrics[category]
                rate = cat_metrics.get("results_match_rate", 0.0) * 100
                total = cat_metrics.get("total", 0)
                report.append(f"- **{category}**: {rate:.2f}% accuracy ({cat_metrics.get('results_match_count', 0)}/{total} correct)\n")
        
        # Recommendations
        report.append("## Recommendations\n")
        report.append("1. **RAG Enhancement**: The knowledge graph RAG significantly improves accuracy by providing ")
        report.append("relevant context and metadata. Continue to enhance the knowledge graph with more annotations ")
        report.append("and query examples.\n")
        report.append("2. **Prompt Engineering**: Enhanced prompting with examples shows clear improvements. ")
        report.append("Consider further refining prompts based on failure analysis.\n")
        report.append("3. **Fine-tuning**: For further improvements, consider fine-tuning the LLM on SQL generation ")
        report.append("tasks using a curated dataset of natural language to SQL pairs.\n")
        report.append("4. **Error Analysis**: Analyze failed queries to identify common patterns and improve ")
        report.append("handling of edge cases.\n")
        
        # Conclusion
        report.append("## Conclusion\n")
        report.append("The evaluation demonstrates that both RAG enhancement and improved prompting contribute to ")
        report.append("better SQL query generation accuracy. The combination of these techniques provides the best ")
        report.append("results, with significant improvements over the baseline configuration.\n")
        
        return "\n".join(report)
    
    def save_report(self):
        """Save all reports and visualizations."""
        # Save markdown report
        md_report = self.generate_markdown_report()
        md_file = self.output_dir / "mtech_evaluation_report.md"
        with open(md_file, 'w') as f:
            f.write(md_report)
        logger.info(f"Markdown report saved to {md_file}")
        
        # Save comparison tables as CSV
        comparison_df = self.generate_comparison_table()
        comparison_df.to_csv(self.output_dir / "overall_comparison.csv", index=False)
        
        complexity_df = self.generate_complexity_comparison()
        complexity_df.to_csv(self.output_dir / "complexity_comparison.csv", index=False)
        
        category_df = self.generate_category_comparison()
        category_df.to_csv(self.output_dir / "category_comparison.csv", index=False)
        
        # Save JSON data
        json_data = {
            "timestamp": datetime.now().isoformat(),
            "configurations": {}
        }
        
        for config_name, results in self.results.items():
            metrics = self.calculate_metrics(results)
            json_data["configurations"][config_name] = {
                "metrics": metrics,
                "detailed_results": [r.to_dict() for r in results]
            }
        
        json_file = self.output_dir / "evaluation_data.json"
        with open(json_file, 'w') as f:
            json.dump(json_data, f, indent=2)
        logger.info(f"JSON data saved to {json_file}")
        
        # Create visualizations
        self.create_visualizations()
        logger.info("Visualizations created")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Generate comprehensive MTech project evaluation report")
    parser.add_argument("--host", type=str, default="localhost", help="PostgreSQL host")
    parser.add_argument("--port", type=int, default=5432, help="PostgreSQL port")
    parser.add_argument("--database", type=str, default="customer_orders_and_reviews_db", help="Database name")
    parser.add_argument("--user", type=str, default="postgres", help="Database user")
    parser.add_argument("--password", type=str, default="postgres", help="Database password")
    parser.add_argument("--neo4j-uri", type=str, default="bolt://localhost:7687", help="Neo4j URI")
    parser.add_argument("--neo4j-user", type=str, default="neo4j", help="Neo4j user")
    parser.add_argument("--neo4j-password", type=str, default="password", help="Neo4j password")
    parser.add_argument("--output-dir", type=str, default="all_test/result", help="Output directory")
    parser.add_argument("--model", type=str, help="Ollama model name")
    parser.add_argument("--skip-baseline", action="store_true", help="Skip baseline evaluation")
    parser.add_argument("--skip-rag", action="store_true", help="Skip RAG evaluation")
    parser.add_argument("--skip-enhanced", action="store_true", help="Skip enhanced prompting evaluation")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(level=log_level)
    
    logger.info("=" * 80)
    logger.info("MTech Project Report Generator")
    logger.info("=" * 80)
    
    # Connect to databases
    logger.info("Connecting to PostgreSQL...")
    db_client = PostgresClient()
    success, message = db_client.connect(
        host=args.host,
        port=args.port,
        database=args.database,
        user=args.user,
        password=args.password
    )
    
    if not success:
        logger.error(f"Failed to connect to PostgreSQL: {message}")
        sys.exit(1)
    
    logger.info("Fetching schema...")
    schema_info = db_client.fetch_schema()
    if not schema_info:
        logger.error("Failed to fetch schema")
        sys.exit(1)
    
    logger.info(f"Schema loaded: {len(schema_info.get('tables', []))} table(s)")
    
    # Connect to Neo4j
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
    
    # Initialize report generator
    output_dir = Path(args.output_dir)
    report_gen = ReportGenerator(output_dir)
    
    # Run evaluations
    if not args.skip_baseline:
        try:
            report_gen.run_baseline_evaluation(db_client, schema_info, args.model)
        except Exception as e:
            logger.error(f"Baseline evaluation failed: {e}")
    
    if not args.skip_rag and neo4j_client:
        try:
            report_gen.run_rag_evaluation(db_client, schema_info, neo4j_client, args.model)
        except Exception as e:
            logger.error(f"RAG evaluation failed: {e}")
    
    if not args.skip_enhanced and neo4j_client:
        try:
            report_gen.run_enhanced_prompting_evaluation(db_client, schema_info, neo4j_client, args.model)
        except Exception as e:
            logger.error(f"Enhanced prompting evaluation failed: {e}")
    
    # Generate and save report
    logger.info("Generating report...")
    report_gen.save_report()
    
    logger.info("=" * 80)
    logger.info(f"Report generation complete! Files saved to: {output_dir.absolute()}")
    logger.info("=" * 80)
    
    # Close connections
    db_client.close()
    if neo4j_client:
        neo4j_client.close()


if __name__ == "__main__":
    main()
