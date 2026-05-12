"""
Enhanced SQL Agent
With Schema-Accurate KPI Query Library (v2 — grounded in actual store_data.db schema)

Tables in store_data.db:
  user_master         — username, employee_id, full_name, designation, position_code,
                        user_type, city, state, region, status
  user_attendance     — username, date, check_in_time, check_out_time,
                        working_hours, attendance_type, is_audited
  store_master        — LISStoreCode, store_name, region, city, state, store_type, status
  store_attendance    — LISStoreCode, username, date, is_open, open_time, close_time, is_audited
  store_user_mapping  — LISStoreCode, username, day_of_month  (beat plan / PJP)
  pjp_deviation       — username, date, planned_store_code, actual_store_code, deviation_reason
  sales               — LISStoreCode, username, product_code, date, quantity_sold, sales_value
  sku_master          — product_code, product_name, brand, category, sub_category, pack_size, status
  primary_shelf       — LISStoreCode, product_code, date, closing_stock, availability_status
"""

import os
import json
import time
import sqlite3
import traceback
from datetime import datetime
from typing import Dict, Tuple, Any, Optional, List
from collections import OrderedDict
import hashlib
import re
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# KPI QUERY LIBRARY — STARTER TIER  (Schema-Accurate v2)
#
# NL query strings are grounded in actual table/column names so the LLM SQL
# generator produces reliable SQL without hallucinating column names.
#
# Placeholder types:
#   month_select  → dropdown: Jan–Dec  → resolves to e.g. "March"
#   date_input    → date picker        → resolves to "YYYY-MM-DD"
#   number_input  → integer spinner
#   text_input    → free text field
#   username      → auto-injected from sidebar (never shown as a form field)
# ============================================================================

KPI_QUERY_LIBRARY = {
    "🗓️ User Attendance": [
        {
            "id": "ua_001",
            "label": "My attendance this month",
            "query": "Show all attendance records from user_attendance for username {username} in {month} — include date, check_in_time, check_out_time, working_hours, attendance_type",
            "placeholders": [
                {"key": "month", "label": "Month", "type": "month_select"}
            ],
            "intent": "GET_USERS",
            "icon": "🗓️"
        },
        {
            "id": "ua_002",
            "label": "My working hours this week",
            "query": "Show total working_hours per day from user_attendance for username {username} for this week — order by date",
            "placeholders": [],
            "intent": "GET_USERS",
            "icon": "⏱️"
        },
        {
            "id": "ua_003",
            "label": "My check-in / check-out today",
            "query": "Show check_in_time, check_out_time, working_hours from user_attendance for username {username} for today",
            "placeholders": [],
            "intent": "GET_USERS",
            "icon": "📍"
        },
        {
            "id": "ua_004",
            "label": "Team attendance on a date",
            "query": "Show full_name, attendance_type, check_in_time, working_hours from user_attendance joined with user_master on username for date {date} — order by full_name",
            "placeholders": [
                {"key": "date", "label": "Date", "type": "date_input"}
            ],
            "intent": "GET_USERS",
            "icon": "👥"
        },
        {
            "id": "ua_005",
            "label": "Users absent on a date",
            "query": "Show full_name, username from user_master where username is NOT present in user_attendance on date {date} and status is Active — order by full_name",
            "placeholders": [
                {"key": "date", "label": "Date", "type": "date_input"}
            ],
            "intent": "GET_USERS",
            "icon": "❌"
        },
        {
            "id": "ua_006",
            "label": "Monthly attendance summary for team",
            "query": "Show username, full_name, count of working days, total working_hours, average working_hours from user_attendance joined with user_master for {month} — group by username",
            "placeholders": [
                {"key": "month", "label": "Month", "type": "month_select"}
            ],
            "intent": "GET_USERS",
            "icon": "📊"
        }
    ],

    "🏪 Store Coverage": [
        {
            "id": "sc_001",
            "label": "Stores I visited today",
            "query": "Show LISStoreCode, store_name, open_time, close_time, is_audited from store_attendance joined with store_master for username {username} on today where is_open = 1",
            "placeholders": [],
            "intent": "GET_STORES",
            "icon": "📍"
        },
        {
            "id": "sc_002",
            "label": "Stores I visited this month",
            "query": "Show count of distinct LISStoreCode visited and list of store_name from store_attendance joined with store_master for username {username} in {month} where is_open = 1",
            "placeholders": [
                {"key": "month", "label": "Month", "type": "month_select"}
            ],
            "intent": "GET_STORES",
            "icon": "🗺️"
        },
        {
            "id": "sc_003",
            "label": "My planned stores for today (Beat Plan)",
            "query": "Show LISStoreCode, store_name from store_user_mapping joined with store_master for username {username} where day_of_month = today's day number",
            "placeholders": [],
            "intent": "GET_STORES",
            "icon": "📋"
        },
        {
            "id": "sc_004",
            "label": "Stores planned but not visited today",
            "query": "Show store_name, LISStoreCode from store_user_mapping for username {username} on today's day_of_month that are NOT present in store_attendance for username {username} today with is_open = 1",
            "placeholders": [],
            "intent": "GET_STORES",
            "icon": "⏳"
        },
        {
            "id": "sc_005",
            "label": "Stores not visited in last N days",
            "query": "Show store_name, LISStoreCode, max(date) as last_visited from store_attendance joined with store_master for username {username} where is_open = 1 — filter to stores whose last visit was more than {days} days ago or never visited",
            "placeholders": [
                {"key": "days", "label": "Days threshold", "type": "number_input", "min": 1, "max": 90, "default": 7}
            ],
            "intent": "GET_STORES",
            "icon": "🚨"
        },
        {
            "id": "sc_006",
            "label": "My visit count per store this month",
            "query": "Show store_name, count(date) as visit_count from store_attendance joined with store_master for username {username} in {month} where is_open = 1 — group by LISStoreCode order by visit_count desc",
            "placeholders": [
                {"key": "month", "label": "Month", "type": "month_select"}
            ],
            "intent": "GET_STORES",
            "icon": "🔢"
        }
    ],

    "📊 PJP & Beat Adherence": [
        {
            "id": "pjp_001",
            "label": "My PJP deviations this month",
            "query": "Show date, planned_store_code, actual_store_code, deviation_reason from pjp_deviation for username {username} in {month} — order by date",
            "placeholders": [
                {"key": "month", "label": "Month", "type": "month_select"}
            ],
            "intent": "GET_STORES",
            "icon": "⚠️"
        },
        {
            "id": "pjp_002",
            "label": "My PJP deviation count vs planned",
            "query": "Show count of total planned visits and count of deviations from pjp_deviation for username {username} in {month}",
            "placeholders": [
                {"key": "month", "label": "Month", "type": "month_select"}
            ],
            "intent": "GET_STORES",
            "icon": "📉"
        },
        {
            "id": "pjp_003",
            "label": "Top deviation reasons this month",
            "query": "Show deviation_reason, count(*) as occurrences from pjp_deviation for {month} group by deviation_reason order by occurrences desc",
            "placeholders": [
                {"key": "month", "label": "Month", "type": "month_select"}
            ],
            "intent": "GET_STORES",
            "icon": "📋"
        },
        {
            "id": "pjp_004",
            "label": "Beat adherence % this month",
            "query": "Calculate beat adherence for username {username} in {month}: count of store_attendance records where is_open = 1 divided by count of planned visits from store_user_mapping — express as percentage",
            "placeholders": [
                {"key": "month", "label": "Month", "type": "month_select"}
            ],
            "intent": "GET_STORES",
            "icon": "✅"
        }
    ],

    "💰 Sales": [
        {
            "id": "sal_001",
            "label": "My total sales this month",
            "query": "Show sum(sales_value) as total_sales and sum(quantity_sold) as total_units from sales for username {username} in {month}",
            "placeholders": [
                {"key": "month", "label": "Month", "type": "month_select"}
            ],
            "intent": "GET_SALES",
            "icon": "💰"
        },
        {
            "id": "sal_002",
            "label": "My sales today",
            "query": "Show LISStoreCode, product_code, quantity_sold, sales_value from sales for username {username} for today — order by sales_value desc",
            "placeholders": [],
            "intent": "GET_SALES",
            "icon": "📈"
        },
        {
            "id": "sal_003",
            "label": "Top N products by sales value",
            "query": "Show product_name, sum(sales_value) as total_sales, sum(quantity_sold) as total_units from sales joined with sku_master for username {username} in {month} — group by product_code, order by total_sales desc, limit {n}",
            "placeholders": [
                {"key": "n", "label": "Top N products", "type": "number_input", "min": 1, "max": 20, "default": 5},
                {"key": "month", "label": "Month", "type": "month_select"}
            ],
            "intent": "TOP_PERFORMERS",
            "icon": "🏆"
        },
        {
            "id": "sal_004",
            "label": "My sales by store this month",
            "query": "Show store_name, sum(sales_value) as total_sales from sales joined with store_master for username {username} in {month} — group by LISStoreCode order by total_sales desc",
            "placeholders": [
                {"key": "month", "label": "Month", "type": "month_select"}
            ],
            "intent": "GET_SALES",
            "icon": "🏪"
        },
        {
            "id": "sal_005",
            "label": "My daily sales trend this month",
            "query": "Show date, sum(sales_value) as daily_sales from sales for username {username} in {month} — group by date order by date",
            "placeholders": [
                {"key": "month", "label": "Month", "type": "month_select"}
            ],
            "intent": "TIME_SERIES",
            "icon": "📊"
        },
        {
            "id": "sal_006",
            "label": "Sales by product category this month",
            "query": "Show category, sum(sales_value) as total_sales, sum(quantity_sold) as total_units from sales joined with sku_master for username {username} in {month} — group by category order by total_sales desc",
            "placeholders": [
                {"key": "month", "label": "Month", "type": "month_select"}
            ],
            "intent": "DISTRIBUTION",
            "icon": "📦"
        }
    ],

    "🛒 Primary Shelf & Stock": [
        {
            "id": "ps_001",
            "label": "Out of stock products today",
            "query": "Show store_name, product_name, closing_stock from primary_shelf joined with sku_master and store_master where availability_status = 'OOS' for today — order by store_name",
            "placeholders": [],
            "intent": "GET_PRODUCTS",
            "icon": "🚨"
        },
        {
            "id": "ps_002",
            "label": "Low stock products (closing stock below threshold)",
            "query": "Show store_name, product_name, closing_stock, availability_status from primary_shelf joined with store_master and sku_master where closing_stock < {threshold} and closing_stock is not null for today — order by closing_stock asc",
            "placeholders": [
                {"key": "threshold", "label": "Stock threshold", "type": "number_input", "min": 1, "max": 100, "default": 10}
            ],
            "intent": "GET_PRODUCTS",
            "icon": "⚠️"
        },
        {
            "id": "ps_003",
            "label": "Stock status for a product",
            "query": "Show store_name, closing_stock, availability_status, date from primary_shelf joined with store_master and sku_master where product_name like '%{product}%' for today — order by closing_stock desc",
            "placeholders": [
                {"key": "product", "label": "Product name (partial OK)", "type": "text_input"}
            ],
            "intent": "GET_PRODUCTS",
            "icon": "🔍"
        },
        {
            "id": "ps_004",
            "label": "OOS count by store today",
            "query": "Show store_name, count(*) as oos_count from primary_shelf joined with store_master where availability_status = 'OOS' for today — group by LISStoreCode order by oos_count desc",
            "placeholders": [],
            "intent": "GET_PRODUCTS",
            "icon": "📊"
        },
        {
            "id": "ps_005",
            "label": "Availability trend for a product this month",
            "query": "Show date, store_name, closing_stock, availability_status from primary_shelf joined with store_master and sku_master where product_name like '%{product}%' in {month} — order by date",
            "placeholders": [
                {"key": "product", "label": "Product name (partial OK)", "type": "text_input"},
                {"key": "month", "label": "Month", "type": "month_select"}
            ],
            "intent": "TIME_SERIES",
            "icon": "📈"
        }
    ]
}


def get_all_kpi_queries() -> List[Dict]:
    """Flat list of all KPI queries with their category."""
    all_queries = []
    for category, queries in KPI_QUERY_LIBRARY.items():
        for q in queries:
            all_queries.append({**q, "category": category})
    return all_queries


def get_kpi_query_by_id(query_id: str) -> Optional[Dict]:
    """Fetch a single KPI query definition by its ID."""
    for queries in KPI_QUERY_LIBRARY.values():
        for q in queries:
            if q["id"] == query_id:
                return q
    return None


def resolve_kpi_query(query_id: str, user_inputs: Dict[str, str]) -> Optional[str]:
    """
    Given a KPI query ID and a dict of placeholder values (including
    auto-injected username from session), returns the fully resolved
    NL query string ready for agent.process_query().
    """
    kpi = get_kpi_query_by_id(query_id)
    if not kpi:
        return None
    resolved = kpi["query"]
    for key, value in user_inputs.items():
        resolved = resolved.replace(f"{{{key}}}", str(value))
    return resolved


# ============================================================================
# UTILITY CLASSES
# ============================================================================

class QueryAuditLog:
    def __init__(self, max_entries: int = 1000):
        self.logs: List[Dict[str, Any]] = []
        self.max_entries = max_entries

    def log_event(self, event_type: str, details: Dict[str, Any]) -> None:
        entry = {'timestamp': datetime.now().isoformat(), 'event_type': event_type, 'details': details}
        self.logs.append(entry)
        if len(self.logs) > self.max_entries:
            self.logs = self.logs[-self.max_entries:]

    def get_logs(self, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
        if event_type:
            return [log for log in self.logs if log['event_type'] == event_type]
        return self.logs


class PerformanceMonitor:
    def __init__(self):
        self.metrics: Dict[str, List[float]] = {}

    def record(self, operation: str, duration: float) -> None:
        if operation not in self.metrics:
            self.metrics[operation] = []
        self.metrics[operation].append(duration)
        if duration > 2.0:
            logger.warning(f"Slow operation: {operation} took {duration:.2f}s")

    def get_stats(self, operation: str) -> Dict[str, float]:
        if operation not in self.metrics or not self.metrics[operation]:
            return {'count': 0, 'avg': 0, 'min': 0, 'max': 0, 'total': 0}
        times = self.metrics[operation]
        return {'count': len(times), 'avg': sum(times) / len(times),
                'min': min(times), 'max': max(times), 'total': sum(times)}


class IntentDetector:
    INTENT_KEYWORDS = {
        'GET_SALES': ['sales', 'revenue', 'earnings', 'income', 'turnover', 'sold', 'sell', 'sales_value', 'quantity_sold'],
        'GET_PRODUCTS': ['product', 'items', 'sku', 'catalog', 'sku_master', 'primary_shelf', 'closing_stock', 'availability', 'oos', 'stock'],
        'GET_STORES': ['store', 'location', 'branch', 'outlet', 'shop', 'address', 'region', 'lisstorecode', 'store_attendance', 'store_master', 'beat', 'pjp', 'deviation'],
        'GET_USERS': ['user', 'staff', 'employee', 'person', 'member', 'team', 'username', 'user_attendance', 'attendance', 'check_in', 'working_hours'],
        'TREND_ANALYSIS': ['trend', 'growth', 'over time', 'progress', 'evolution', 'trajectory', 'daily', 'weekly', 'monthly'],
        'COMPARISON': ['vs', 'versus', 'compare', 'between', 'difference', 'comparison', 'compared'],
        'TOP_PERFORMERS': ['top', 'best', 'highest', 'leading', 'maximum', 'rank', 'limit'],
        'ANOMALY_DETECTION': ['unusual', 'anomaly', 'outlier', 'unexpected', 'deviation', 'abnormal', 'pjp_deviation'],
        'TIME_SERIES': ['daily', 'weekly', 'monthly', 'yearly', 'historical', 'annually', 'trend'],
        'MULTI_METRIC': ['and', 'plus', 'also', 'along with', 'together', 'with'],
        'DISTRIBUTION': ['distribution', 'breakdown', 'across', 'by', 'per', 'group by', 'category'],
        'FORECAST': ['forecast', 'predict', 'project', 'future', 'expected'],
    }

    def detect(self, query: str) -> Tuple[str, List[str]]:
        query_lower = query.lower()
        detected_keywords = []
        intent_scores = {}
        for intent, keywords in self.INTENT_KEYWORDS.items():
            matching_keywords = [kw for kw in keywords if kw in query_lower]
            if matching_keywords:
                intent_scores[intent] = len(matching_keywords)
                detected_keywords.extend(matching_keywords)
        detected_intent = max(intent_scores, key=intent_scores.get) if intent_scores else 'GET_SALES'
        return detected_intent, detected_keywords


class ParameterExtractor:
    PARAMETER_PATTERNS = {
        'time_period': [
            r'(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)',
            r'(\d{4})',
            r'(this year|last year|this month|last month|today|yesterday|week|month|year)',
        ],
        'store_name': [r'store[s]?\s+(?:named|called)?\s+([\'"]?)([^\'"]+)\1'],
        'product_name': [r'product[s]?\s+(?:named|called)?\s+([\'"]?)([^\'"]+)\1'],
        'region': [r'region[s]?\s+(?:named|called)?\s+([\'"]?)([^\'"]+)\1'],
        'limit': [r'top\s+(\d+)', r'limit\s+(\d+)', r'(\d+)\s+(?:product|store|user|item)'],
        'date_range': [r'from\s+([^,]+)\s+to\s+([^,]+)', r'between\s+([^,]+)\s+and\s+([^,]+)']
    }

    def extract(self, query: str) -> Dict[str, Any]:
        query_lower = query.lower()
        parameters = {}
        for param_type, patterns in self.PARAMETER_PATTERNS.items():
            for pattern in patterns:
                matches = re.findall(pattern, query_lower, re.IGNORECASE)
                if matches:
                    if param_type == 'time_period':
                        parameters[param_type] = '&'.join([str(m) for m in matches])
                    elif param_type == 'limit':
                        parameters[param_type] = int(matches[0]) if isinstance(matches[0], str) and matches[0].isdigit() else 10
                    elif param_type == 'date_range':
                        if isinstance(matches[0], tuple) and len(matches[0]) == 2:
                            parameters['date_from'] = matches[0][0]
                            parameters['date_to'] = matches[0][1]
                        else:
                            parameters[param_type] = matches[0] if matches else None
                    else:
                        parameters[param_type] = matches[0][-1] if isinstance(matches[0], tuple) else matches[0]
        return parameters


class QueryCache:
    def __init__(self, max_size: int = 100):
        self.cache: OrderedDict = OrderedDict()
        self.max_size = max_size
        self.hits = 0
        self.misses = 0

    def get(self, query_hash: str) -> Optional[Dict[str, Any]]:
        if query_hash in self.cache:
            self.cache.move_to_end(query_hash)
            self.hits += 1
            return self.cache[query_hash]
        self.misses += 1
        return None

    def put(self, query_hash: str, result: Dict[str, Any]) -> None:
        if query_hash in self.cache:
            self.cache.move_to_end(query_hash)
        self.cache[query_hash] = result
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)

    def clear(self) -> None:
        self.cache.clear()
        self.hits = 0
        self.misses = 0

    def get_size(self) -> int:
        return len(self.cache)

    def get_hit_rate(self) -> str:
        total = self.hits + self.misses
        return "0%" if total == 0 else f"{(self.hits / total * 100):.1f}%"


class SessionManager:
    def __init__(self, max_history: int = 100):
        self.max_history = max_history
        self.sessions: Dict[str, Dict[str, Any]] = {}

    def create_session(self, session_id: str) -> None:
        self.sessions[session_id] = {
            'created_at': datetime.now(), 'queries': [],
            'total_queries': 0, 'total_time': 0
        }

    def add_query_to_session(self, session_id: str, query_info: Dict[str, Any]) -> None:
        if session_id not in self.sessions:
            self.create_session(session_id)
        session = self.sessions[session_id]
        session['queries'].append(query_info)
        session['total_queries'] += 1
        session['total_time'] += query_info.get('execution_time', 0)
        if len(session['queries']) > self.max_history:
            session['queries'] = session['queries'][-self.max_history:]

    def get_session_history(self, session_id: str) -> List[Dict[str, Any]]:
        return self.sessions.get(session_id, {}).get('queries', [])

    def get_session_stats(self, session_id: str) -> Dict[str, Any]:
        if session_id not in self.sessions:
            return {}
        session = self.sessions[session_id]
        queries = session['queries']
        if not queries:
            return {'total_queries': 0, 'total_time': 0, 'avg_time': 0}
        return {
            'total_queries': session['total_queries'],
            'total_time': session['total_time'],
            'avg_time': session['total_time'] / len(queries),
            'created_at': session['created_at'].isoformat()
        }


# ============================================================================
# MAIN AGENT CLASS
# ============================================================================

class EnhancedSQLAgent:
    """Main SQL Agent Orchestrator"""

    def __init__(self, db_path: str, schema_config_path: str, retry_count: int = 3):
        try:
            from llm_sql_generator import LLMSQLGenerator
            from sql_validator import SQLValidator
            from nl_response_generator import NLResponseGenerator
        except ImportError as e:
            logger.error(f"Failed to import required modules: {e}")
            raise

        self.db_path = db_path
        self.schema_config_path = schema_config_path
        self.retry_count = retry_count
        self.start_time = datetime.now()

        try:
            self.llm_sql_gen = LLMSQLGenerator(db_path, schema_config_path)
            self.sql_validator = SQLValidator(db_path)
            self.nl_response_gen = NLResponseGenerator()
            logger.info("✅ Core components initialized")
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
            raise

        self.intent_detector = IntentDetector()
        self.param_extractor = ParameterExtractor()
        self.audit_log = QueryAuditLog()
        self.perf_monitor = PerformanceMonitor()
        self.query_cache = QueryCache(max_size=100)
        self.session_manager = SessionManager(max_history=100)
        self.session_id = hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8]
        self.session_manager.create_session(self.session_id)
        self.cache = self.query_cache
        logger.info(f"✅ EnhancedSQLAgent initialized (Session: {self.session_id})")

    def _compute_query_hash(self, query: str, intent: str) -> str:
        return hashlib.md5(f"{query}_{intent}".encode()).hexdigest()

    def _error_response(self, user_query, intent, extracted_params, error_msg,
                        error_type="UNKNOWN_ERROR", sql_query=None, validation=None):
        return {
            'success': False, 'user_query': user_query, 'intent': intent,
            'parameters': extracted_params, 'sql_query': sql_query,
            'validation': validation, 'error': error_msg, 'error_type': error_type,
            'session_id': self.session_id, 'timestamp': datetime.now().isoformat()
        }

    def process_query(self, user_query: str, use_cache: bool = True) -> Dict[str, Any]:
        """Process a natural language query end-to-end."""
        logger.info(f"Processing query: {user_query}")
        query_start_time = time.time()

        intent, keywords = self.intent_detector.detect(user_query)
        self.audit_log.log_event('INTENT_DETECTED', {'intent': intent, 'keywords': keywords})

        extracted_params = self.param_extractor.extract(user_query)
        self.audit_log.log_event('PARAMETERS_EXTRACTED', extracted_params)

        try:
            is_complex, complexity_reason = self.llm_sql_gen.is_complex_query(
                user_query, intent, extracted_params)
        except Exception:
            is_complex, complexity_reason = False, "Unable to determine"

        query_hash = self._compute_query_hash(user_query, intent)
        if use_cache:
            cached = self.query_cache.get(query_hash)
            if cached:
                cached['cached'] = True
                return cached

        sql_query = None
        last_error = None
        for attempt in range(self.retry_count):
            try:
                sql_result = self.llm_sql_gen.generate_sql(
                    user_query=user_query, intent=intent,
                    extracted_params=extracted_params,
                    context={'current_date': datetime.now().strftime('%Y-%m-%d'),
                             'complexity': complexity_reason, 'session_id': self.session_id}
                )
                if not isinstance(sql_result, dict):
                    last_error = f"Invalid return type: {type(sql_result).__name__}"
                    continue
                if sql_result.get('success') is True and sql_result.get('sql_query'):
                    sql_query = sql_result.get('sql_query')
                    break
                else:
                    last_error = sql_result.get('message', 'SQL generation failed')
            except Exception as e:
                last_error = str(e)
                if attempt < self.retry_count - 1:
                    time.sleep(2 ** attempt)

        if not sql_query:
            return self._error_response(
                user_query=user_query, intent=intent, extracted_params=extracted_params,
                error_msg=f"SQL generation failed after {self.retry_count} attempts: {last_error}",
                error_type="SQL_GENERATION_ERROR"
            )

        valid, validation_msg = self.sql_validator.validate_sql_syntax(sql_query)

        exec_start = time.time()
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql_query)
            rows = cursor.fetchall()
            columns = [d[0] for d in cursor.description] if cursor.description else []
            self.perf_monitor.record('query_execution', time.time() - exec_start)
            results = [dict(row) for row in rows]
            conn.close()
        except Exception as e:
            return self._error_response(
                user_query=user_query, intent=intent, extracted_params=extracted_params,
                error_msg=f"Query execution failed: {str(e)}", error_type="EXECUTION_ERROR",
                sql_query=sql_query, validation={'is_valid': valid, 'message': validation_msg}
            )

        try:
            nl_response = self.nl_response_gen.generate_response(
                user_query=user_query, intent=intent,
                data={'data': results, 'columns': columns, 'row_count': len(results)},
                sql_query=sql_query, style='balanced'
            )
        except Exception:
            nl_response = {'main_answer': f"Query returned {len(results)} records.",
                           'insights': [], 'recommendations': []}

        total_time = time.time() - query_start_time
        result = {
            'success': True, 'user_query': user_query, 'intent': intent,
            'parameters': extracted_params, 'sql_query': sql_query,
            'validation': {'is_valid': valid, 'message': validation_msg},
            'data': {'columns': columns, 'data': results, 'row_count': len(results)},
            'response': nl_response,
            'metadata': {'execution_time': total_time, 'session_id': self.session_id,
                          'timestamp': datetime.now().isoformat(), 'cached': False}
        }

        self.query_cache.put(query_hash, result)
        self.session_manager.add_query_to_session(self.session_id, {
            'query': user_query, 'intent': intent, 'execution_time': total_time,
            'row_count': len(results), 'timestamp': datetime.now().isoformat()
        })
        return result

    def get_session_stats(self) -> Dict[str, Any]:
        session_stats = self.session_manager.get_session_stats(self.session_id)
        duration_minutes = (datetime.now() - self.start_time).total_seconds() / 60
        return {
            'session_id': self.session_id,
            'session_duration_minutes': round(duration_minutes, 2),
            'total_queries': session_stats.get('total_queries', 0),
            'cache_stats': {'hits': self.query_cache.hits, 'misses': self.query_cache.misses,
                             'cache_size': self.query_cache.get_size(),
                             'hit_rate': self.query_cache.get_hit_rate()},
            'performance_stats': {op: self.perf_monitor.get_stats(op)
                                   for op in ['intent_detection', 'sql_generation', 'query_execution']}
        }

    def get_audit_logs(self) -> List[Dict[str, Any]]:
        return self.audit_log.get_logs()

    def get_session_history(self) -> List[Dict[str, Any]]:
        return self.session_manager.get_session_history(self.session_id)

    def clear_cache(self) -> None:
        self.query_cache.clear()

    def reload_schema(self) -> None:
        self.llm_sql_gen.reload_schema()
        self.clear_cache()


def create_agent(db_path: str = "store_data.db",
                 schema_config_path: str = "./config/schema_config.json",
                 retry_count: int = 3) -> EnhancedSQLAgent:
    return EnhancedSQLAgent(db_path, schema_config_path, retry_count)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python enhanced_sql_agent.py 'your query here'")
        sys.exit(1)
    query = " ".join(sys.argv[1:])
    print(f"\n🔍 Processing: {query}\n")
    try:
        agent = create_agent()
        result = agent.process_query(query)
        if result['success']:
            print(f"\n✅ Success! Intent: {result['intent']} | Rows: {result['data']['row_count']} | Time: {result['metadata']['execution_time']:.2f}s\n")
        else:
            print(f"\n❌ Failed: {result['error']}\n")
    except Exception as e:
        print(f"\n❌ Error: {str(e)}\n")
        traceback.print_exc()
