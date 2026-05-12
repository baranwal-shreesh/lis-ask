"""
Placeholder Resolver
Resolves SQL query placeholders with actual parameter values
Handles date ranges, store names, products, and regions
"""

import json
from datetime import datetime, timedelta


class PlaceholderResolver:
    """Resolves placeholders in SQL queries with actual parameter values"""
    
    def __init__(self, db_path="store_data.db", schema_config_path="schema_config.json"):
        """
        Initialize PlaceholderResolver
        
        Args:
            db_path (str): Path to the SQLite database
            schema_config_path (str): Path to schema configuration JSON file
        """
        self.db_path = db_path
        self.schema_config_path = schema_config_path
        self.schema = self._load_schema()
        print("✅ PlaceholderResolver initialized")
    
    def _load_schema(self):
        """
        Load schema configuration from JSON file
        
        Returns:
            dict: Tables schema dictionary, empty dict if file not found
        """
        try:
            with open(self.schema_config_path, 'r') as f:
                schema_data = json.load(f)
                return schema_data.get('tables', {})
        except FileNotFoundError:
            print(f"Warning: Schema config not found at {self.schema_config_path}")
            return {}
    
    def _get_date_range(self, time_period):
        """
        Get date range for a given time period
        
        Args:
            time_period (str): Time period identifier (e.g., 'august', 'last_month', 'today')
            
        Returns:
            tuple: (start_date_sql, end_date_sql) formatted for SQL queries
        """
        today = datetime.now()
        current_year = today.year
        current_month = today.month
        current_day = today.day
        
        time_period_lower = str(time_period).lower().strip()
        
        # Handle specific dates
        if time_period_lower == 'today':
            date_str = today.strftime("%Y-%m-%d")
            return f"'{date_str}'", f"'{date_str}'"
        
        elif time_period_lower == 'yesterday':
            yesterday = today - timedelta(days=1)
            date_str = yesterday.strftime("%Y-%m-%d")
            return f"'{date_str}'", f"'{date_str}'"
        
        # Handle week ranges
        elif time_period_lower == 'last_week':
            start = today - timedelta(days=today.weekday() + 7)
            end = start + timedelta(days=6)
            return f"'{start.strftime('%Y-%m-%d')}'", f"'{end.strftime('%Y-%m-%d')}'"
        
        elif time_period_lower == 'this_week':
            start = today - timedelta(days=today.weekday())
            end = start + timedelta(days=6)
            return f"'{start.strftime('%Y-%m-%d')}'", f"'{end.strftime('%Y-%m-%d')}'"
        
        # Handle month ranges
        elif time_period_lower == 'last_month':
            if current_month == 1:
                first_day = datetime(current_year - 1, 12, 1)
                last_day = datetime(current_year - 1, 12, 31)
            else:
                first_day = datetime(current_year, current_month - 1, 1)
                if current_month - 1 == 12:
                    last_day = datetime(current_year, 12, 31)
                else:
                    last_day = datetime(current_year, current_month, 1) - timedelta(days=1)
            
            return f"'{first_day.strftime('%Y-%m-%d')}'", f"'{last_day.strftime('%Y-%m-%d')}'"
        
        elif time_period_lower == 'this_month':
            first_day = datetime(current_year, current_month, 1)
            if current_month == 12:
                last_day = datetime(current_year + 1, 1, 1) - timedelta(days=1)
            else:
                last_day = datetime(current_year, current_month + 1, 1) - timedelta(days=1)
            
            return f"'{first_day.strftime('%Y-%m-%d')}'", f"'{last_day.strftime('%Y-%m-%d')}'"
        
        # Map month names to numbers
        month_map = {
            'january': 1, 'february': 2, 'march': 3, 'april': 4,
            'may': 5, 'june': 6, 'july': 7, 'august': 8,
            'september': 9, 'october': 10, 'november': 11, 'december': 12,
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
        }
        
        # Check for month names in time period
        for month_name, month_num in month_map.items():
            if month_name in time_period_lower:
                first_day = datetime(current_year, month_num, 1)
                if month_num == 12:
                    last_day = datetime(current_year + 1, 1, 1) - timedelta(days=1)
                else:
                    last_day = datetime(current_year, month_num + 1, 1) - timedelta(days=1)
                
                return f"'{first_day.strftime('%Y-%m-%d')}'", f"'{last_day.strftime('%Y-%m-%d')}'"
        
        # Default: return current month
        first_day = datetime(current_year, current_month, 1)
        if current_month == 12:
            last_day = datetime(current_year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = datetime(current_year, current_month + 1, 1) - timedelta(days=1)
        
        return f"'{first_day.strftime('%Y-%m-%d')}'", f"'{last_day.strftime('%Y-%m-%d')}'"
    
    def resolve(self, sql_query, extracted_params):
        """
        Resolve all placeholders in SQL query with actual values
        
        Args:
            sql_query (str): SQL query potentially containing placeholders
            extracted_params (dict): Dictionary of extracted parameters
            
        Returns:
            dict: Resolution result with success status and resolved query
        """
        if not sql_query:
            return {
                'success': False,
                'message': 'Empty SQL query provided',
                'sql_query': sql_query
            }
        
        if not extracted_params:
            extracted_params = {}
        
        resolved_query = sql_query
        missing_params = []
        
        # Resolve date/time placeholders
        if '{start_date}' in resolved_query or '{end_date}' in resolved_query or '{db_start_date}' in resolved_query:
            if 'time_period' in extracted_params and extracted_params['time_period']:
                start_date, end_date = self._get_date_range(extracted_params['time_period'])
            else:
                # Default to current month if no time period specified
                start_date, end_date = self._get_date_range('this_month')
            
            resolved_query = resolved_query.replace('{start_date}', start_date)
            resolved_query = resolved_query.replace('{end_date}', end_date)
            resolved_query = resolved_query.replace('{db_start_date}', start_date)
            resolved_query = resolved_query.replace('{db_end_date}', end_date)
        
        # Resolve store placeholders
        if '{store_name}' in resolved_query or '{store_id}' in resolved_query:
            if 'store_identifier' in extracted_params and extracted_params['store_identifier']:
                store_val = extracted_params['store_identifier']
                resolved_query = resolved_query.replace('{store_name}', f"'{store_val}'")
                resolved_query = resolved_query.replace('{store_id}', f"'{store_val}'")
            else:
                missing_params.append('store_name')
        
        # Resolve product placeholders
        if '{product_name}' in resolved_query or '{product_code}' in resolved_query:
            if 'product_identifier' in extracted_params and extracted_params['product_identifier']:
                product_val = extracted_params['product_identifier']
                resolved_query = resolved_query.replace('{product_name}', f"'{product_val}'")
                resolved_query = resolved_query.replace('{product_code}', f"'{product_val}'")
            else:
                missing_params.append('product_name')
        
        # Resolve region placeholders
        if '{region}' in resolved_query:
            if 'region_identifier' in extracted_params and extracted_params['region_identifier']:
                region_val = extracted_params['region_identifier']
                resolved_query = resolved_query.replace('{region}', f"'{region_val}'")
            else:
                missing_params.append('region')
        
        # If there are unresolved parameters, return error
        if missing_params:
            return {
                'success': False,
                'message': f'Missing required parameters: {", ".join(missing_params)}',
                'missing_params': missing_params,
                'sql_query': resolved_query
            }
        
        return {
            'success': True,
            'message': 'All placeholders resolved successfully',
            'sql_query': resolved_query
        }
