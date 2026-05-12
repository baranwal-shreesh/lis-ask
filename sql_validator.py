"""
SQL Validator
Comprehensive SQL query validation with security checks and detailed reporting.

Changes from previous version:
  ✅ FIX: Removed '--' and '/*' from DANGEROUS_PATTERNS
         (valid SQL comment syntax was causing false-positive validation failures
          on every LLM-generated query that included inline comments)
  ✅ FIX: Removed MAX_WILDCARD_COUNT check
         (COUNT(*) in complex aggregations was incorrectly flagged as a threat)
"""

import sqlite3
import logging
import traceback
from datetime import datetime
from typing import Tuple, Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────
MAX_QUERY_LENGTH      = 10000
MAX_SELECT_COUNT      = 10
MAX_VALIDATION_HISTORY = 100

# Security: genuinely dangerous DDL / injection patterns only
# NOTE: '--' and '/*' intentionally excluded — they are valid SQL comment syntax
#       used routinely in LLM-generated queries and CTEs.
DANGEROUS_PATTERNS = {
    "drop table"          : "Attempting to drop table",
    "drop database"       : "Attempting to drop database",
    "drop schema"         : "Attempting to drop schema",
    "delete from"         : "Attempting to delete data",
    "truncate table"      : "Attempting to truncate table",
    "truncate"            : "Attempting to truncate",
    "exec "               : "Attempting to execute code",
    "execute "            : "Attempting to execute code",
    "xp_"                 : "Attempting to use system procedures",
    "sp_"                 : "Attempting to use stored procedures",
    "union select"        : "UNION-based injection detected",
    "' or '1'='1"     : "Tautology-based injection detected",
    "\" or \"1\"=\"1" : "Tautology-based injection detected",
    "' or 1=1"           : "OR-based injection detected",
    "\" or 1=1"          : "OR-based injection detected",
    "; drop"              : "Statement termination attack detected",
    "version()"           : "Attempting to access version info",
    "information_schema"  : "Attempting to access schema info",
    "sys.objects"         : "Attempting to access system objects",
}

VALID_COMMANDS = ["SELECT", "WITH", "INSERT", "UPDATE", "DELETE"]


class SQLValidator:
    """Comprehensive SQL query validator with security checks."""

    def __init__(self, db_path: str):
        self.db_path          = db_path
        self.validation_history: List[Dict[str, Any]] = []
        logger.info(f"SQLValidator initialized with database: {db_path}")

    # ── Main entry point ─────────────────────────────────────────────────────

    def validate_sql(self, sql_query: str) -> Tuple[bool, str]:
        """
        Three-stage validation: syntax → security → structure.

        Returns:
            (True,  "SQL validation passed") on success
            (False, "<reason>")              on failure
        """
        if not sql_query:
            logger.warning("Empty SQL query received")
            return False, "Empty SQL query"

        if not isinstance(sql_query, str):
            logger.warning(f"Invalid type: {type(sql_query).__name__}")
            return False, f"SQL query must be string, got {type(sql_query).__name__}"

        if len(sql_query) > MAX_QUERY_LENGTH:
            logger.warning(f"Query too long: {len(sql_query)} chars")
            return False, f"Query exceeds maximum length of {MAX_QUERY_LENGTH} characters"

        for check, stage in [
            (self.check_syntax,         "syntax"),
            (self.check_security,       "security"),
            (self.check_query_structure,"structure"),
        ]:
            ok, msg = check(sql_query)
            if not ok:
                logger.warning(f"{stage.title()} check failed: {msg}")
                self._log_validation(sql_query, False, stage, msg)
                return False, msg

        logger.info("SQL validation passed")
        self._log_validation(sql_query, True, "complete", "All checks passed")
        return True, "SQL validation passed"

    def validate_sql_syntax(self, sql_query: str) -> Tuple[bool, str]:
        """Alias for validate_sql — backward compatibility."""
        return self.validate_sql(sql_query)

    # ── Stage 1: Syntax ──────────────────────────────────────────────────────

    def check_syntax(self, sql_query: str) -> Tuple[bool, str]:
        """Validate basic SQL syntax (command, parentheses, quotes)."""
        sql_upper = sql_query.upper().strip()

        if not any(sql_upper.startswith(cmd) for cmd in VALID_COMMANDS):
            return False, f"Invalid SQL command — must start with {', '.join(VALID_COMMANDS)}"

        if sql_query.count("(") != sql_query.count(")"):
            o, c = sql_query.count("("), sql_query.count(")")
            return False, f"Unbalanced parentheses (open: {o}, close: {c})"

        sq = sql_query.count("'") - sql_query.count("\\'")
        if sq % 2 != 0:
            return False, f"Unbalanced single quotes (count: {sq})"

        dq = sql_query.count('"') - sql_query.count('\\"')
        if dq % 2 != 0:
            return False, f"Unbalanced double quotes (count: {dq})"

        if sql_query.strip().endswith(","):
            return False, "Query ends with comma — incomplete statement"

        return True, "Syntax valid"

    # ── Stage 2: Security ────────────────────────────────────────────────────

    def check_security(self, sql_query: str) -> Tuple[bool, str]:
        """
        Detect SQL injection and dangerous DDL patterns.

        NOTE: SQL comments ('--', '/*') are NOT flagged here.
              They are standard syntax produced by CTEs and LLM-generated queries.
              Wildcard counting is also removed — SELECT COUNT(*) is legitimate.
        """
        sql_lower = sql_query.lower()
        for pattern, description in DANGEROUS_PATTERNS.items():
            if pattern in sql_lower:
                return False, f"Security threat: {description} (pattern: '{pattern}')"
        return True, "Security check passed"

    # ── Stage 3: Structure ───────────────────────────────────────────────────

    def check_query_structure(self, sql_query: str) -> Tuple[bool, str]:
        """Validate logical query structure (FROM/WHERE/JOIN consistency)."""
        sql_upper = sql_query.upper().strip()

        if sql_upper.startswith("SELECT"):
            if "WHERE" in sql_upper and "FROM" not in sql_upper:
                if "(" not in sql_query and "SELECT 1" not in sql_upper:
                    return False, "WHERE clause without FROM clause"

            if "JOIN" in sql_upper and "ON" not in sql_upper:
                if "CROSS JOIN" not in sql_upper and "NATURAL JOIN" not in sql_upper:
                    return False, "JOIN clause without ON condition"

            select_count  = sql_upper.count("SELECT")
            union_count   = sql_upper.count("UNION")
            subquery_count = sql_query.count("(SELECT")

            if select_count > 1 and union_count == 0 and subquery_count < (select_count - 1):
                if select_count > MAX_SELECT_COUNT:
                    return False, (
                        f"Too many SELECT statements "
                        f"({select_count} found, max {MAX_SELECT_COUNT})"
                    )
                logger.warning(f"Multiple SELECT statements detected: {select_count}")

        return True, "Structure valid"

    # ── Detailed analysis ────────────────────────────────────────────────────

    def get_validation_details(self, sql_query: str) -> Dict[str, Any]:
        """Return detailed breakdown of query characteristics."""
        sql_upper = sql_query.upper()
        return {
            "query_length"       : len(sql_query),
            "query_preview"      : sql_query.strip()[:100] + ("..." if len(sql_query) > 100 else ""),
            "line_count"         : sql_query.count("\n") + 1,
            "query_type"         : self._detect_query_type(sql_query),
            "has_subqueries"     : sql_upper.count("SELECT") > 1,
            "has_joins"          : "JOIN" in sql_upper,
            "has_where"          : "WHERE" in sql_upper,
            "has_group_by"       : "GROUP BY" in sql_upper,
            "has_having"         : "HAVING" in sql_upper,
            "has_order_by"       : "ORDER BY" in sql_upper,
            "has_limit"          : "LIMIT" in sql_upper,
            "has_union"          : "UNION" in sql_upper,
            "has_aggregates"     : any(f in sql_upper for f in ["SUM(", "COUNT(", "AVG(", "MAX(", "MIN("]),
            "aggregate_functions": [f for f in ["SUM", "COUNT", "AVG", "MAX", "MIN"] if f in sql_upper],
            "parentheses_balanced": sql_query.count("(") == sql_query.count(")"),
            "quotes_balanced"    : (sql_query.count("'") - sql_query.count("\\'")) % 2 == 0,
            "join_count"         : sql_upper.count("JOIN"),
            "subquery_count"     : sql_upper.count("SELECT") - 1,
            "table_count_estimate": sql_upper.count("FROM") + sql_upper.count("JOIN"),
            "has_wildcards"      : "*" in sql_query,
            "wildcard_count"     : sql_query.count("*"),
            "validated_at"       : datetime.now().isoformat(),
        }

    def _detect_query_type(self, sql_query: str) -> str:
        s = sql_query.upper().strip()
        if s.startswith("SELECT"): return "SELECT"
        if s.startswith("INSERT"): return "INSERT"
        if s.startswith("UPDATE"): return "UPDATE"
        if s.startswith("DELETE"): return "DELETE"
        if s.startswith("WITH"):   return "CTE (Common Table Expression)"
        return "UNKNOWN"

    # ── Safe execution ───────────────────────────────────────────────────────

    def execute_query(self, sql_query: str) -> Tuple[bool, Any, str]:
        """
        Validate then execute a query.

        Returns:
            (True,  {'data': [...], 'columns': [...], 'row_count': int}, None)
            (False, None, "<error message>")
        """
        try:
            ok, msg = self.validate_sql(sql_query)
            if not ok:
                logger.error(f"Validation failed: {msg}")
                return False, None, msg

            conn   = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql_query)
            rows    = cursor.fetchall()
            columns = [d[0] for d in cursor.description] if cursor.description else []
            data    = [dict(row) for row in rows]
            conn.close()

            logger.info(f"Query executed: {len(data)} rows returned")
            return True, {"data": data, "columns": columns, "row_count": len(data)}, None

        except sqlite3.Error as e:
            err = f"Database error: {str(e)}"
            logger.error(err)
            logger.debug(traceback.format_exc())
            return False, None, err
        except Exception as e:
            err = f"Execution error: {str(e)}"
            logger.error(err)
            logger.debug(traceback.format_exc())
            return False, None, err

    # ── Convenience ──────────────────────────────────────────────────────────

    def validate_and_explain(self, sql_query: str) -> Dict[str, Any]:
        """Combined validation report (standardised format)."""
        ok, message = self.validate_sql(sql_query)
        return {
            "is_valid"         : ok,
            "message"          : message,
            "details"          : self.get_validation_details(sql_query),
            "timestamp"        : datetime.now().isoformat(),
            "validator_version": "2.1",
        }

    def _log_validation(self, sql: str, success: bool, stage: str, msg: str) -> None:
        self.validation_history.append({
            "timestamp"    : datetime.now().isoformat(),
            "query_preview": sql[:50] + "..." if len(sql) > 50 else sql,
            "success"      : success,
            "stage"        : stage,
            "message"      : msg,
        })
        if len(self.validation_history) > MAX_VALIDATION_HISTORY:
            self.validation_history = self.validation_history[-MAX_VALIDATION_HISTORY:]

    def get_validation_history(self) -> List[Dict[str, Any]]:
        return self.validation_history.copy()

    def clear_history(self) -> None:
        self.validation_history.clear()
        logger.info("Validation history cleared")


# ── Module-level convenience ──────────────────────────────────────────────────

def quick_validate(sql_query: str) -> bool:
    """Quick validation without creating a validator instance."""
    ok, _ = SQLValidator(":memory:").validate_sql(sql_query)
    return ok


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python sql_validator.py 'SELECT * FROM table'")
        sys.exit(1)
    query  = " ".join(sys.argv[1:])
    report = SQLValidator("store_data.db").validate_and_explain(query)
    if report["is_valid"]:
        print(f"✅ VALID — {report['message']}")
    else:
        print(f"❌ INVALID — {report['message']}")
    for k, v in report["details"].items():
        print(f"  {k}: {v}")
