"""
LLM SQL Generator — v2 (Business-Grounded Prompt)
Fixes inconsistent SQL for presence/attendance queries by adding:
  • TABLE PURPOSE guide
  • BUSINESS GLOSSARY
  • FIELD SEMANTICS
  • FORBIDDEN PATTERNS
  • CANONICAL QUERY PATTERNS
"""

import os, re, json, traceback, logging
from datetime import datetime
from typing import Dict, Tuple, Any, Optional, List, Set

import config
from groq import Groq

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# BUSINESS CONTEXT CONSTANTS
# These teach the LLM what each table/field MEANS in business terms.
# ═══════════════════════════════════════════════════════════════════════════════

TABLE_PURPOSE_GUIDE = """
=== TABLE PURPOSE GUIDE (read this before choosing tables) ===

user_master          → WHO is in the system. Profile data: name, role, region.
                       created_at = when account was created (NOT an attendance date).
                       NEVER use user_master alone to determine presence/attendance.

user_attendance      → DID the user show up for work on a given date?
                       One row per (username, date). attendance_type = Present / Absent / Leave.
                       USE THIS TABLE for: "how many were present", "who was absent",
                       "attendance rate", "check-in time", "working hours".
                       CANONICAL FILTER for "present" → attendance_type != 'Absent'
                                                     OR just EXISTS in this table for that date.

store_attendance     → DID the user visit a specific store on a given date?
                       One row per (LISStoreCode, username, date).
                       is_open = 1 means the visit was recorded as completed.
                       USE THIS TABLE for: "which stores were visited", "store coverage",
                       "stores not visited", "store visit count".
                       DO NOT use this to count user-level attendance (user_attendance is correct).

store_user_mapping   → WHICH stores is a user PLANNED/ASSIGNED to visit on which day_of_month?
                       This is the BEAT PLAN / PJP schedule. It is NOT attendance.
                       day_of_month = 1-31 (day number in month, not a full date).
                       NEVER use this to check if someone was "present" or "attended".
                       USE THIS TABLE for: "planned stores", "beat plan", "PJP schedule",
                       "assigned stores", "which stores should user visit".

store_master         → Store profile: name, region, city, state, store_type.
                       USE THIS for region/city/state filters on store-level queries.

user_master.region   → The region the USER is assigned to (home region).
store_master.region  → The region the STORE is located in.
                       When filtering "by region" for store visits → use store_master.region.
                       When filtering "by region" for user headcount → use user_master.region.

pjp_deviation        → Records where user visited a different store than planned.
sales                → Actual sales transactions per store per product per date.
primary_shelf        → Stock / availability data per store per product per date.
sku_master           → Product master: name, brand, category.
"""

FIELD_SEMANTICS = """
=== FIELD SEMANTICS ===

user_master.user_type    → PRIMARY role identifier. NOT NULL. ALWAYS use this for role filtering.
                           Typical values: 'Promoter', 'Sales Promoter', 'Merchandiser',
                           'Team Leader', 'Area Manager'.
                           Use LIKE '%Promoter%' if unsure of exact value.

user_master.designation  → Secondary/display title. NULLABLE. Do NOT use as primary role filter.

user_master.created_at   → Timestamp when user account was created. NEVER use for attendance date.
user_master.updated_at   → Timestamp when user profile was last edited. NEVER use for attendance date.
user_master.status       → 'Active' or 'Inactive'. Always filter WHERE um.status = 'Active'.

user_attendance.date            → The actual attendance date (YYYY-MM-DD). USE THIS for date filters.
user_attendance.attendance_type → 'Present', 'Absent', 'Leave', 'Half Day', etc.
user_attendance.check_in_time   → Datetime of check-in. Only present when user clocked in.

store_attendance.is_open → 1 = store visit completed, 0 = not completed.
                           Always add is_open = 1 when querying "visited stores".

store_user_mapping.day_of_month → Integer 1-31. NOT a date. 
                                   To use with "today": CAST(STRFTIME('%d', 'now') AS INTEGER).
"""

FORBIDDEN_PATTERNS = """
=== FORBIDDEN PATTERNS — NEVER generate these ===

❌ STRFTIME('%Y-%m-%d', um.created_at) = '...'
   REASON: created_at is account creation time, not attendance date.
   FIX   : Use user_attendance.date instead.

❌ JOIN store_user_mapping ... WHERE [date field] = '...'
   REASON: store_user_mapping has no date column. It has day_of_month (integer).
   FIX   : Use user_attendance for presence. Use store_user_mapping ONLY for beat plan.

❌ COUNT(*) FROM user_master WHERE [date condition]
   REASON: user_master has no attendance records.
   FIX   : COUNT DISTINCT user_attendance.username for a given date.

❌ WHERE sm.region IS NOT NULL  (when user asked "all regions")
   REASON: "all regions" means no region filter — omit the WHERE clause for region.
   FIX   : Simply remove the region filter when region = 'All'.

❌ um.designation = 'Promoter'  (as primary role filter)
   REASON: designation is nullable and inconsistently populated.
   FIX   : um.user_type LIKE '%Promoter%' OR um.user_type = 'Promoter'.
"""

CANONICAL_PATTERNS = """
=== CANONICAL QUERY PATTERNS ===

[A] How many users/promoters/staff were PRESENT on DATE?
    SELECT COUNT(DISTINCT ua.username)
    FROM user_attendance ua
    JOIN user_master um ON ua.username = um.username
    WHERE DATE(ua.date) = 'YYYY-MM-DD'
      AND um.user_type LIKE '%Promoter%'   -- adjust role as needed
      AND um.status = 'Active'

[B] Who was ABSENT on DATE?
    SELECT um.full_name, um.region
    FROM user_master um
    WHERE um.status = 'Active'
      AND um.user_type LIKE '%Promoter%'
      AND um.username NOT IN (
          SELECT username FROM user_attendance WHERE DATE(date) = 'YYYY-MM-DD'
      )

[C] How many STORES were visited on DATE?
    SELECT COUNT(DISTINCT sa.LISStoreCode)
    FROM store_attendance sa
    WHERE DATE(sa.date) = 'YYYY-MM-DD'
      AND sa.is_open = 1

[D] Headcount by region on DATE:
    SELECT um.region, COUNT(DISTINCT ua.username) AS headcount
    FROM user_attendance ua
    JOIN user_master um ON ua.username = um.username
    WHERE DATE(ua.date) = 'YYYY-MM-DD'
      AND um.status = 'Active'
    GROUP BY um.region

[E] Planned stores for user on today (beat plan):
    SELECT sm.store_name, sm.region
    FROM store_user_mapping sum
    JOIN store_master sm ON sum.LISStoreCode = sm.LISStoreCode
    WHERE sum.username = 'USERNAME'
      AND sum.day_of_month = CAST(STRFTIME('%d', 'now') AS INTEGER)
"""


class LLMSQLGenerator:
    """Universal SQL Generator with Business-Grounded Prompt"""

    def __init__(self, db_path: str, schema_config_path: str, api_key: Optional[str] = None):
        self.db_path = db_path
        self.schema_config_path = schema_config_path
        self.api_key = api_key or getattr(config, "GROQ_API_KEY", None) or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY not found in config or environment variables")

        self.client = Groq(api_key=self.api_key)
        self.model  = getattr(config, "GROQ_MODEL", None) or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

        self.schema_cache: Dict[str, Any] = {}
        self.schema_info: Dict[str, Any]  = {"tables": {}}
        self.query_cache: Dict[str, Dict[str, Any]] = {}

        self._load_schema_from_config()
        logger.info("✅ LLMSQLGenerator initialized")
        logger.info(f"   Model   : {self.model}")
        logger.info(f"   DB      : {db_path}")
        logger.info(f"   Schema  : {schema_config_path}")

    # ── schema loading (unchanged) ────────────────────────────────────────────
    def _load_schema_from_config(self) -> None:
        if not os.path.exists(self.schema_config_path):
            raise FileNotFoundError(
                f"Schema config not found: {self.schema_config_path}\n"
                "Run: python extract_schema.py"
            )
        with open(self.schema_config_path, "r", encoding="utf-8") as f:
            self.schema_info = json.load(f)
        if not self.schema_info.get("tables"):
            raise ValueError("Schema config is empty or invalid")
        logger.info(f"   Schema tables loaded: {list(self.schema_info['tables'].keys())}")

    def reload_schema(self) -> None:
        self._load_schema_from_config()
        self.schema_cache.clear()
        self.query_cache.clear()

    # ── schema formatter (unchanged) ──────────────────────────────────────────
    def format_schema_for_llm(self, tables_info: Dict[str, Any]) -> str:
        schema_text = ""
        for table_name, table_data in tables_info.items():
            schema_text += f"\n{'='*60}\nTABLE: {table_name.upper()}\n{'='*60}\nColumns:\n"
            columns_raw = table_data.get("columns", [])
            types_map   = table_data.get("types", {})
            for col in columns_raw:
                try:
                    if isinstance(col, dict):
                        col_name    = col.get("name", "unknown")
                        col_type    = col.get("type", "TEXT")
                        is_pk       = " [PRIMARY KEY]" if col.get("pk") else ""
                        is_nullable = " [NULLABLE]" if col.get("notnull") == 0 else ""
                    else:
                        col_name, col_type, is_pk, is_nullable = str(col), types_map.get(str(col), "TEXT"), "", ""
                    schema_text += f"  • {col_name} ({col_type}){is_pk}{is_nullable}\n"
                except Exception:
                    schema_text += f"  • {str(col)} (TEXT)\n"
            fks = table_data.get("foreign_keys", [])
            if fks:
                schema_text += "\nForeign Keys:\n"
                for fk in fks:
                    if isinstance(fk, dict):
                        schema_text += (
                            f"  → {table_name}.{fk.get('from_column')} "
                            f"REFERENCES {fk.get('to_table')}.{fk.get('to_column')}\n"
                        )
            schema_text += "\n"
        return schema_text

    def _build_join_path_guidance(self, tables_info: Dict[str, Any]) -> str:
        join_examples: List[str] = []
        for table_name, table_data in tables_info.items():
            for fk in table_data.get("foreign_keys", []):
                if isinstance(fk, dict):
                    fc, tt, tc = fk.get("from_column"), fk.get("to_table"), fk.get("to_column")
                    if fc and tt and tc:
                        join_examples.append(
                            f"  • {table_name} → {tt}: ON {table_name}.{fc} = {tt}.{tc}"
                        )
        return ("\n=== JOIN PATHS ===\n" + "\n".join(join_examples[:20]) + "\n") if join_examples else ""

    # ── complexity check (unchanged) ──────────────────────────────────────────
    def is_complex_query(self, user_query: str, intent: str, params: Dict[str, Any]) -> Tuple[bool, str]:
        q = user_query.lower()
        score, reasons = 0, []
        if any(w in q for w in ["vs", "versus", "compare"]): score += 2; reasons.append("Comparison")
        if params and "time_period" in params:
            ts = str(params.get("time_period", "")).lower()
            if any(s in ts for s in ["and", "&", "vs", ","]): score += 2; reasons.append("Multi time period")
        agg_n = sum(1 for f in ["sum","count","avg","max","min","total","average"] if f in q)
        if agg_n > 1: score += 1; reasons.append(f"{agg_n} aggregations")
        if intent in ["COMPARISON","TREND_ANALYSIS","MULTI_METRIC"]: score += 2; reasons.append(f"Intent:{intent}")
        return score >= 3, "; ".join(reasons) if reasons else "Simple query"

    # ── IMPROVED PROMPT ───────────────────────────────────────────────────────
    def _build_prompt(
        self,
        user_query     : str,
        intent         : str,
        extracted_params: Dict[str, Any],
        formatted_schema: str,
    ) -> str:
        join_guidance = self._build_join_path_guidance(self.schema_info.get("tables", {}))
        return f"""You are an expert SQL query generator for SQLite databases.
You generate SQL for a FIELD FORCE MANAGEMENT system used by FMCG companies.

{TABLE_PURPOSE_GUIDE}
{FIELD_SEMANTICS}
{FORBIDDEN_PATTERNS}
{CANONICAL_PATTERNS}

=== DATABASE SCHEMA ===
{formatted_schema}
{join_guidance}

=== USER QUESTION ===
"{user_query}"

=== CONTEXT ===
Intent     : {intent}
Parameters : {json.dumps(extracted_params, indent=2)}
Today's date: {datetime.now().strftime('%Y-%m-%d')}

=== GENERATION RULES ===
1. ALWAYS check the TABLE PURPOSE GUIDE above before choosing tables.
2. For "present / attended / showed up" questions → use user_attendance table.
3. For "store visited / store covered" questions → use store_attendance with is_open = 1.
4. NEVER use created_at or updated_at as attendance dates.
5. NEVER use store_user_mapping as a substitute for attendance.
6. Use um.user_type (NOT um.designation) as the primary role filter.
7. When region = 'All' or not specified → do NOT add a region WHERE clause.
8. Always add um.status = 'Active' when joining user_master for headcount.
9. COMPLETE JOIN CHAIN: every alias in SELECT/WHERE must be in FROM/JOIN.
10. Return ONLY the raw SQL query — no markdown, no explanation, no semicolon.

SQL:"""

    # ── JOIN validation (unchanged) ───────────────────────────────────────────
    def _extract_table_aliases_from_sql(self, sql: str) -> Tuple[Set[str], Set[str]]:
        sql_clean = " ".join(sql.split())
        aliases_in: Set[str] = set()
        for m in re.finditer(r"(?:FROM|JOIN)\s+([\w\.]+)(?:\s+(?:AS\s+)?(\w+))?", sql_clean, re.IGNORECASE):
            aliases_in.add((m.group(2) if m.group(2) else m.group(1)).lower())
        aliases_ref: Set[str] = set()
        for m in re.finditer(r"\b([A-Za-z_]\w*)\.(?!\d)", sql_clean):
            aliases_ref.add(m.group(1).lower())
        return aliases_in, aliases_ref

    def _validate_join_completeness(self, sql: str) -> Tuple[bool, str, List[str]]:
        a_in, a_ref = self._extract_table_aliases_from_sql(sql)
        missing = sorted(a_ref - a_in)
        if missing:
            return False, f"Orphaned aliases: {', '.join(missing)}", missing
        return True, "JOIN chain complete", []

    def _suggest_missing_joins(self, missing_aliases: List[str]) -> List[str]:
        suggestions: List[str] = []
        for alias in missing_aliases:
            for table_name, table_data in self.schema_info.get("tables", {}).items():
                if alias.lower() in table_name.lower():
                    for fk in table_data.get("foreign_keys", []):
                        if isinstance(fk, dict):
                            fc, tt, tc = fk.get("from_column"), fk.get("to_table"), fk.get("to_column")
                            if fc and tt and tc:
                                suggestions.append(f"JOIN {table_name} {alias} ON {alias}.{fc} = {tt}.{tc}")
        return suggestions

    # ── generate_sql (unchanged logic, improved logging) ─────────────────────
    def generate_sql(
        self,
        user_query      : str,
        intent          : str,
        extracted_params: Dict[str, Any],
        context         : Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if context is None:
            context = {}

        cache_key = f"{user_query}_{intent}"
        if cache_key in self.query_cache:
            logger.info("📦 SQL cache hit")
            r = self.query_cache[cache_key].copy()
            r["cached"] = True
            return r

        tables_info = self.schema_info.get("tables", {})
        if not tables_info:
            return self._error_response("No schema", "SCHEMA_ERROR", "Schema not loaded")

        if "formatted_schema" not in self.schema_cache:
            self.schema_cache["formatted_schema"] = self.format_schema_for_llm(tables_info)
        formatted_schema = self.schema_cache["formatted_schema"]

        prompt = self._build_prompt(user_query, intent, extracted_params, formatted_schema)
        logger.info(f"   Prompt sections: TABLE_PURPOSE + FIELD_SEMANTICS + FORBIDDEN + CANONICAL + SCHEMA")

        try:
            response = self.client.chat.completions.create(
                model    = self.model,
                messages = [
                    {
                        "role"   : "system",
                        "content": (
                            "You are an expert SQLite SQL generator for a field force management system. "
                            "You have deep knowledge of the table purposes and business rules provided. "
                            "Return ONLY a valid SQL SELECT query. No markdown, no explanation."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature = 0.1,
                max_tokens  = 1500,
                top_p       = 0.9,
            )

            sql_query = self._clean_sql_response(response.choices[0].message.content.strip())

            if not sql_query or "select" not in sql_query.lower():
                return self._error_response("No SELECT in output", "GENERATION_ERROR", "LLM did not produce a SELECT")

            is_valid, val_msg, missing = self._validate_join_completeness(sql_query)
            if not is_valid:
                suggestions = self._suggest_missing_joins(missing)
                return self._error_response(
                    val_msg, "INCOMPLETE_JOIN",
                    f"Orphaned references. Suggested JOINs:\n" + "\n".join(suggestions)
                )

            logger.info(f"   ✅ SQL validated — {len(sql_query)} chars")
            result = {
                "success"   : True,
                "sql_query" : sql_query,
                "message"   : "SQL generated successfully",
                "cached"    : False,
                "validation": "JOIN chain complete",
                "timestamp" : datetime.now().isoformat(),
            }
            self.query_cache[cache_key] = result.copy()
            return result

        except Exception as e:
            logger.error(f"   LLM call failed: {e}")
            logger.debug(traceback.format_exc())
            return self._error_response(str(e), "LLM_ERROR", "Failed to generate SQL")

    # ── helpers ───────────────────────────────────────────────────────────────
    def _clean_sql_response(self, sql: str) -> str:
        sql = sql.replace("```sql", "").replace("```", "").strip()
        for prefix in ["SQL:", "Query:", "Here is", "Result:", "The query:", "Answer:", "Here's", "The SQL", "SQL Query:"]:
            if sql.upper().startswith(prefix.upper()):
                sql = sql[len(prefix):].strip()
        return " ".join(sql.rstrip(";").split())

    def validate_sql_syntax(self, sql_query: str) -> Tuple[bool, str]:
        if not sql_query:
            return False, "Empty SQL"
        if not any(sql_query.upper().strip().startswith(c) for c in ["SELECT", "WITH", "INSERT", "UPDATE", "DELETE"]):
            return False, "Must start with SELECT/WITH/INSERT/UPDATE/DELETE"
        if sql_query.count("(") != sql_query.count(")"):
            return False, "Unbalanced parentheses"
        if getattr(config, "ENABLE_SECURITY_CHECK", False):
            for danger in ["DROP", "TRUNCATE", "ALTER", "CREATE"]:
                if danger in sql_query.upper():
                    return False, f"Dangerous keyword: {danger}"
        return True, "SQL syntax valid"

    def clear_cache(self) -> None:
        n = len(self.query_cache)
        self.query_cache.clear()
        logger.info(f"Cache cleared ({n} entries)")

    def _error_response(self, error: str, error_type: str = "UNKNOWN_ERROR", message: str = "") -> Dict[str, Any]:
        return {
            "success"      : False,
            "sql_query"    : None,
            "message"      : message or error,
            "error_type"   : error_type,
            "error_details": error,
            "timestamp"    : datetime.now().isoformat(),
        }


def generate_sql_quick(
    user_query         : str,
    db_path            : str = "store_data.db",
    schema_config_path : str = "./config/schema_config.json",
) -> Dict[str, Any]:
    return LLMSQLGenerator(db_path, schema_config_path).generate_sql(user_query, "QUERY", {})


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python llm_sql_generator.py 'your query here'")
        sys.exit(1)
    result = generate_sql_quick(" ".join(sys.argv[1:]))
    if result["success"]:
        print(f"\n✅ SQL:\n{result['sql_query']}\n")
    else:
        print(f"\n❌ {result['message']}\n{result.get('error_details','')}\n")
