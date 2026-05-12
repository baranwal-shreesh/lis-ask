"""
Configuration file for SQL Agent MVP - FIXED VERSION
Set your API keys and database paths here

Changes:
- CRIT-002 FIXED: Removed DB_PATH double assignment
- Added environment variable support for all config
- Centralized logging configuration
- Added cache and performance settings
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

# ============================================================================
# GROQ LLM CONFIGURATION
# ============================================================================
GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')
GROQ_MODEL = os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')

# Validation
if not GROQ_API_KEY or GROQ_API_KEY == '__API-Key__':
    print("⚠️  WARNING: GROQ_API_KEY not set. Please set it in .env file or environment variables")

# ============================================================================
# DATABASE CONFIGURATION - FIXED
# ============================================================================
# CRIT-002 FIXED: Single DB_PATH assignment with env variable support
DB_PATH = os.getenv('DB_PATH', 'store_data.db')

# Schema configuration path
SCHEMA_CONFIG_PATH = os.getenv('SCHEMA_CONFIG_PATH', './config/schema_config.json')

# Ensure paths exist
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
Path(SCHEMA_CONFIG_PATH).parent.mkdir(parents=True, exist_ok=True)

# ============================================================================
# STREAMLIT CONFIGURATION
# ============================================================================
PAGE_TITLE = os.getenv('PAGE_TITLE', 'SQL Agent MVP')
PAGE_ICON = os.getenv('PAGE_ICON', '🚀')
LAYOUT = os.getenv('LAYOUT', 'wide')
INITIAL_SIDEBAR_STATE = os.getenv('INITIAL_SIDEBAR_STATE', 'expanded')

# ============================================================================
# VALIDATION CONFIGURATION
# ============================================================================
ENABLE_SQL_VALIDATION = os.getenv('ENABLE_SQL_VALIDATION', 'True').lower() == 'true'
ENABLE_SECURITY_CHECK = os.getenv('ENABLE_SECURITY_CHECK', 'True').lower() == 'true'
MAX_QUERY_LENGTH = int(os.getenv('MAX_QUERY_LENGTH', '5000'))

# ============================================================================
# LOGGING CONFIGURATION - STANDARDIZED
# ============================================================================
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = os.getenv('LOG_FILE', './logs/app.log')
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# Create logs directory if it doesn't exist
Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)

# Configure root logger (MED-003 fix: centralized logging)
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FORMAT,
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# ============================================================================
# CACHE CONFIGURATION
# ============================================================================
ENABLE_QUERY_CACHE = os.getenv('ENABLE_QUERY_CACHE', 'True').lower() == 'true'
CACHE_MAX_SIZE = int(os.getenv('CACHE_MAX_SIZE', '100'))
CACHE_TTL_SECONDS = int(os.getenv('CACHE_TTL_SECONDS', '3600'))  # 1 hour

# ============================================================================
# PERFORMANCE CONFIGURATION
# ============================================================================
MAX_WORKERS = int(os.getenv('MAX_WORKERS', '4'))
QUERY_TIMEOUT_SECONDS = int(os.getenv('QUERY_TIMEOUT_SECONDS', '30'))
LLM_TIMEOUT_SECONDS = int(os.getenv('LLM_TIMEOUT_SECONDS', '60'))

# ============================================================================
# ERROR HANDLING CONFIGURATION (MED-004 fix)
# ============================================================================
# Standardized error response format
ERROR_RESPONSE_FORMAT = {
    "success": False,
    "error_type": None,
    "message": None,
    "details": None,
    "timestamp": None
}

# ============================================================================
# FEATURE FLAGS
# ============================================================================
ENABLE_PLACEHOLDER_RESOLUTION = os.getenv('ENABLE_PLACEHOLDER_RESOLUTION', 'True').lower() == 'true'
ENABLE_NATURAL_LANGUAGE_RESPONSE = os.getenv('ENABLE_NATURAL_LANGUAGE_RESPONSE', 'True').lower() == 'true'
ENABLE_QUERY_HISTORY = os.getenv('ENABLE_QUERY_HISTORY', 'True').lower() == 'true'

# ============================================================================
# VALIDATION & STARTUP
# ============================================================================
def validate_config():
    """Validate critical configuration settings"""
    errors = []
    
    # Check API key
    if not GROQ_API_KEY:
        errors.append("GROQ_API_KEY is not set")
    
    # Check database exists (or can be created)
    if not Path(DB_PATH).exists():
        print(f"⚠️  Database not found at: {DB_PATH}")
        print(f"   It will be created when you run the application")
    
    # Check schema config
    if not Path(SCHEMA_CONFIG_PATH).exists():
        print(f"⚠️  Schema config not found at: {SCHEMA_CONFIG_PATH}")
        print(f"   Run: python extract_schema.py to generate it")
    
    return errors

# Run validation on import
_validation_errors = validate_config()

if _validation_errors:
    print("\n❌ Configuration Errors:")
    for error in _validation_errors:
        print(f"   - {error}")
    print()
else:
    print("✅ Configuration loaded successfully")
    print(f"   Database: {DB_PATH}")
    print(f"   Schema Config: {SCHEMA_CONFIG_PATH}")
    print(f"   Log Level: {LOG_LEVEL}")

# ============================================================================
# CONFIGURATION SUMMARY (for debugging)
# ============================================================================
def print_config():
    """Print current configuration (useful for debugging)"""
    print("\n" + "="*80)
    print("CURRENT CONFIGURATION")
    print("="*80)
    print(f"\n🤖 LLM:")
    print(f"   Model: {GROQ_MODEL}")
    print(f"   API Key Set: {'Yes' if GROQ_API_KEY else 'No'}")
    print(f"\n💾 Database:")
    print(f"   DB Path: {DB_PATH}")
    print(f"   Schema Config: {SCHEMA_CONFIG_PATH}")
    print(f"\n📊 Validation:")
    print(f"   SQL Validation: {ENABLE_SQL_VALIDATION}")
    print(f"   Security Check: {ENABLE_SECURITY_CHECK}")
    print(f"   Max Query Length: {MAX_QUERY_LENGTH}")
    print(f"\n📝 Logging:")
    print(f"   Level: {LOG_LEVEL}")
    print(f"   File: {LOG_FILE}")
    print(f"\n🚀 Performance:")
    print(f"   Cache Enabled: {ENABLE_QUERY_CACHE}")
    print(f"   Cache Size: {CACHE_MAX_SIZE}")
    print(f"   Query Timeout: {QUERY_TIMEOUT_SECONDS}s")
    print(f"\n✨ Features:")
    print(f"   Placeholder Resolution: {ENABLE_PLACEHOLDER_RESOLUTION}")
    print(f"   Natural Language Response: {ENABLE_NATURAL_LANGUAGE_RESPONSE}")
    print(f"   Query History: {ENABLE_QUERY_HISTORY}")
    print("="*80 + "\n")

# Uncomment to see config on import
# print_config()
