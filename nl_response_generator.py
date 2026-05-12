"""
Natural Language Response Generator
Converts query results to human-readable, context-aware responses.

Changes from previous version:
  ✅ FIX: _format_value() was applying ₹ to ALL numeric values.
          Now uses col_name to detect monetary vs count vs hours vs plain numbers.
          Call-site in _generate_ranked_list_response() updated to pass col_name.
"""

import os
import json
import logging
import re
import statistics
from datetime import datetime
from typing import Dict, Any, List

from groq import Groq
import config

logger = logging.getLogger(__name__)


# =============================================================================
# DATA ANALYZER
# =============================================================================

class DataAnalyzer:
    """Analyzes query results to extract numeric insights."""

    @staticmethod
    def analyze_numeric_data(values: List[float]) -> Dict[str, Any]:
        if not values:
            return {}
        try:
            return {
                "min"   : min(values),
                "max"   : max(values),
                "avg"   : statistics.mean(values),
                "median": statistics.median(values),
                "total" : sum(values),
                "count" : len(values),
                "stdev" : statistics.stdev(values) if len(values) > 1 else 0,
            }
        except Exception as e:
            logger.warning(f"Error analyzing numeric data: {e}")
            return {}


# =============================================================================
# SYSTEM PROMPT
# =============================================================================

ANSWER_SYSTEM_PROMPT = """
You are a senior retail analytics analyst.

You will receive:
- the user's natural-language question,
- the executed SQL query text,
- metadata about the tabular result,
- a small preview of the result rows.

Your job is to write a clear, business-friendly answer.

STRICT RULES:
1. Never mention SQL, tables, columns, schemas, or any technical implementation details.
2. Do not invent numbers that are not present in the data or clearly implied.
3. If a preformatted_answer is provided, preserve its structure and ordering; you may slightly
   refine the wording of the intro but do NOT change the list contents or values.
4. For small result sets (<= 20 rows) WITHOUT a preformatted_answer, describe the key items.
5. For large result sets, summarize key aggregates or comparisons rather than listing every row.
6. Use the same currency and units as in the data (₹ for rupees if present).
7. Keep answer to at most 2 short paragraphs OR 1 short paragraph plus a bullet list.
8. If there is no data (row_count = 0), clearly say that and suggest what the user can try.
"""


# =============================================================================
# MONETARY COLUMN DETECTION
# =============================================================================

# Column name keywords that indicate a monetary / rupee value
MONETARY_KEYWORDS = {
    "sales", "revenue", "value", "amount", "price",
    "income", "cost", "earning", "turnover", "spend",
}

# Column name keywords that indicate hours / duration
HOURS_KEYWORDS = {"hour", "hrs", "duration", "working"}

# Column name keywords that indicate a percentage / rate
RATE_KEYWORDS = {"rate", "pct", "percent", "percentage", "ratio", "share"}


def _format_value(value: Any, col_name: str = "") -> str:
    """
    Format a numeric value based on the column it came from.

      Monetary columns  → ₹1,23,456
      Rate/% columns    → 42.3%
      Hours columns     → 8.5 hrs
      Everything else   → plain integer with comma separator (1,234)
    """
    try:
        num       = float(value)
        col_lower = col_name.lower()

        if any(kw in col_lower for kw in MONETARY_KEYWORDS):
            return f"₹{num:,.0f}"

        if any(kw in col_lower for kw in RATE_KEYWORDS):
            return f"{num:.1f}%"

        if any(kw in col_lower for kw in HOURS_KEYWORDS):
            return f"{num:.1f} hrs"

        # Plain number — integer-like or decimal
        if num == int(num):
            return f"{int(num):,}"
        return f"{num:,.2f}"

    except (ValueError, TypeError):
        return str(value)


# =============================================================================
# MAIN RESPONSE GENERATOR
# =============================================================================

class NLResponseGenerator:
    """
    Generate natural language responses from query results.

    Flow:
      • Ranked / top-N with small result set  → deterministic Python bullet list
      • Everything else                       → generic LLM answer agent
      • LLM failure                           → simple rule-based fallback
    """

    def __init__(self):
        self.analyzer      = DataAnalyzer()
        self.response_count = 0

        self.api_key = getattr(config, "GROQ_API_KEY", None) or os.getenv("GROQ_API_KEY")
        self.model   = (
            getattr(config, "GROQ_MODEL", None)
            or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        )
        self.client = Groq(api_key=self.api_key) if self.api_key else None
        logger.info("NLResponseGenerator initialized")

    # ── Public entry point ────────────────────────────────────────────────────

    def generate_response(
        self,
        user_query : str,
        intent     : str,
        data       : Dict[str, Any],
        sql_query  : str,
        style      : str = "balanced",
    ) -> Dict[str, Any]:
        """
        Args:
            user_query : Original user question.
            intent     : Detected intent string.
            data       : Dict with keys — data (rows list), columns, row_count.
            sql_query  : Executed SQL string.
            style      : Reserved for future use.

        Returns:
            Dict with keys: main_answer, insights, recommendations, data_summary.
        """
        self.response_count += 1
        try:
            if not data or not data.get("data"):
                return self._empty_response(user_query)

            rows      : List[Dict[str, Any]] = data.get("data", [])
            row_count : int                  = data.get("row_count", len(rows))
            columns   : List[str]            = data.get("columns", [])

            logger.info(
                f"Generating NL response — intent: {intent}, "
                f"rows: {row_count}, query: {user_query[:60]}"
            )

            # Ranked / top-N → deterministic bullet list (no LLM)
            if self._is_ranked_query(user_query, sql_query) and row_count <= 20:
                logger.info("Ranked/top-N query → bullet list formatter")
                return self._ranked_list_response(rows, columns, user_query)

            # Generic LLM answer agent
            main_answer = self._llm_answer(user_query, intent, sql_query, rows, columns)
            return {
                "main_answer"    : main_answer,
                "insights"       : [f"Total records returned: {row_count}"],
                "recommendations": ["Review the table below for detailed values."],
                "data_summary"   : {"total_rows": row_count, "total_columns": len(columns)},
            }

        except Exception as e:
            logger.error(f"Error generating NL response: {e}")
            return {
                "main_answer"    : f"Query executed successfully. Found {data.get('row_count', 0)} results.",
                "insights"       : [],
                "recommendations": [],
                "data_summary"   : {},
            }

    # ── Ranked / top-N (deterministic, no LLM) ───────────────────────────────

    def _is_ranked_query(self, user_query: str, sql_query: str) -> bool:
        q = user_query.lower()
        s = (sql_query or "").lower()
        patterns = [
            r"top\s+\d+", r"best\s+\d+", r"highest",
            r"lowest",     r"rank",        r"leading",
            r"bottom\s+\d+",
        ]
        has_pattern   = any(re.search(p, q) for p in patterns)
        has_ord_lim   = "order by" in s and "limit" in s
        has_rank_func = any(k in s for k in ["rank()", "row_number()", "dense_rank()"])
        return has_pattern or has_ord_lim or has_rank_func

    def _ranked_list_response(
        self,
        rows   : List[Dict[str, Any]],
        columns: List[str],
        query  : str,
    ) -> Dict[str, Any]:
        """Deterministic bullet list for ranked queries — no LLM call."""
        if not rows or not columns:
            return self._empty_response(query)

        item_col    = columns[0]
        value_col   = columns[-1] if len(columns) > 1 else columns[0]
        time_ctx    = self._temporal_context(query)
        metric      = self._ranking_metric(query, value_col)

        m = re.search(r"top\s+(\d+)|best\s+(\d+)|(\d+)\s+(?:top|best)", query.lower())
        requested   = int(m.group(1) or m.group(2) or m.group(3)) if m else len(rows)
        requested   = min(requested, len(rows))

        intro = f"Here are the top {requested} {self._pluralize(item_col)} by {metric}"
        if time_ctx:
            intro += f" {time_ctx}"
        intro += ":"

        lines = [intro]
        for i, row in enumerate(rows[:requested], 1):
            name  = row.get(item_col, f"Item {i}")
            raw   = row.get(value_col, "N/A")
            # ✅ FIX: pass col_name so formatting matches the data type
            fval  = _format_value(raw, col_name=value_col)
            lines.append(f"{i}. {name}: {fval}")

        main_answer = "\n".join(lines)
        values      = [self._safe_float(r.get(value_col, 0)) for r in rows]
        stats       = self.analyzer.analyze_numeric_data(values) if values else {}

        return {
            "main_answer"    : main_answer,
            "insights"       : self._ranked_insights(values),
            "recommendations": [
                "Analyse what makes these top performers stand out.",
                "Compare with the previous period to spot trends.",
            ],
            "data_summary": {
                "total_items": len(rows),
                "metric"     : metric,
                "max"        : stats.get("max"),
                "min"        : stats.get("min"),
                "total"      : stats.get("total"),
            },
        }

    # ── Generic LLM answer agent ──────────────────────────────────────────────

    def _llm_answer(
        self,
        user_query: str,
        intent    : str,
        sql_query : str,
        rows      : List[Dict[str, Any]],
        columns   : List[str],
    ) -> str:
        if not self.client:
            return self._fallback(user_query, rows, columns)
        try:
            payload = {
                "user_query"    : user_query,
                "intent"        : intent,
                "sql_query"     : sql_query,
                "result_meta"   : {"row_count": len(rows), "columns": columns},
                "result_preview": rows[:20],
            }
            resp = self.client.chat.completions.create(
                model    = self.model,
                messages = [
                    {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
                    {"role": "user",   "content": json.dumps(payload, ensure_ascii=False)},
                ],
                temperature = 0.3,
                max_tokens  = 400,
                top_p       = 0.9,
            )
            text = resp.choices[0].message.content.strip()
            return text if text else self._fallback(user_query, rows, columns)
        except Exception as e:
            logger.warning(f"LLM answer agent failed: {e}")
            return self._fallback(user_query, rows, columns)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _temporal_context(self, query: str) -> str:
        q = query.lower()
        months = {
            "january": "January", "jan": "January",
            "february": "February", "feb": "February",
            "march": "March",    "mar": "March",
            "april": "April",    "apr": "April",
            "may": "May",
            "june": "June",      "jun": "June",
            "july": "July",      "jul": "July",
            "august": "August",  "aug": "August",
            "september": "September", "sep": "September", "sept": "September",
            "october": "October",     "oct": "October",
            "november": "November",   "nov": "November",
            "december": "December",   "dec": "December",
        }
        for mk, name in months.items():
            m = re.search(rf"\b{mk}\b\s*(\d{{4}})?", q)
            if m:
                year = m.group(1) if m.group(1) else datetime.now().year
                return f"in {name} {year}"
        rel = {
            r"last\s+month": "last month",  r"this\s+month": "this month",
            r"last\s+year" : "last year",   r"this\s+year" : "this year",
            r"today"       : "today",        r"yesterday"   : "yesterday",
            r"last\s+week" : "last week",   r"this\s+week" : "this week",
        }
        for pat, phrase in rel.items():
            if re.search(pat, q):
                return phrase
        return ""

    def _ranking_metric(self, query: str, value_col: str) -> str:
        q  = query.lower()
        vc = value_col.lower()
        if "sales" in q or "revenue" in q or "sales" in vc: return "sales"
        if "profit" in q or "profit" in vc:                  return "profit"
        if "quantity" in q or "units" in q:                  return "quantity sold"
        if "inventory" in q or "stock" in q:                 return "stock level"
        if "visit" in q or "visit" in vc:                    return "visits"
        if "hour" in q or "hour" in vc:                      return "working hours"
        metric = vc.replace("_", " ").replace("total", "").strip()
        return metric or "value"

    def _pluralize(self, col: str) -> str:
        name = col.replace("_", " ").replace("name", "").strip().lower()
        if name.endswith("s"):  return name
        if name.endswith("y"):  return name[:-1] + "ies"
        return name + "s"

    def _safe_float(self, value: Any) -> float:
        try:   return float(value)
        except: return 0.0

    def _ranked_insights(self, values: List[float]) -> List[str]:
        if len(values) < 2:
            return []
        stats  = self.analyzer.analyze_numeric_data(values)
        total  = stats.get("total", 0) or 0
        top    = values[0]
        out    = []
        if total > 0:
            out.append(f"The top item contributes about {(top / total * 100):.1f}% of the total.")
        if values[0] > 0:
            gap = ((values[0] - values[-1]) / values[0]) * 100
            out.append(f"The gap between highest and lowest in this list is {gap:.1f}%.")
        return out

    def _fallback(self, query: str, rows: List, columns: List) -> str:
        base = f"Query returned {len(rows)} record{'s' if len(rows) != 1 else ''}"
        if columns:
            base += f" with {len(columns)} column{'s' if len(columns) != 1 else ''}"
        return base + "."

    def _empty_response(self, query: str) -> Dict[str, Any]:
        return {
            "main_answer"    : "No data found matching your query.",
            "insights"       : ["Consider expanding your search criteria."],
            "recommendations": [
                "Verify the filters and time range.",
                "Try removing some conditions or widening the date range.",
            ],
            "data_summary": {"total_rows": 0},
        }


# =============================================================================
# QUICK TEST
# =============================================================================

if __name__ == "__main__":
    gen  = NLResponseGenerator()
    rows = [
        {"store_name": "Delhi Supermarket 1",  "visit_count": 22},
        {"store_name": "Mumbai Hypermarket 3",  "visit_count": 19},
        {"store_name": "Bangalore Supermarket 2","visit_count": 17},
        {"store_name": "Chennai Departmental 1", "visit_count": 14},
        {"store_name": "Kolkata Convenience 4",  "visit_count": 11},
    ]
    resp = gen.generate_response(
        user_query = "Top 5 stores by visit count this month",
        intent     = "GET_STORES",
        data       = {"data": rows, "columns": ["store_name", "visit_count"], "row_count": 5},
        sql_query  = "SELECT store_name, COUNT(*) as visit_count ... ORDER BY visit_count DESC LIMIT 5",
    )
    print(resp["main_answer"])
    # Should show plain numbers like "22", "19" — NOT "₹22", "₹19"
