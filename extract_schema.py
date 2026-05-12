"""
Complete Schema Extraction Tool - FIXED VERSION
Extracts database schema and generates all required config files

CRITICAL FIX: Returns columns as dict objects with full metadata
- OLD: columns = ["id", "name", "price"]  ❌
- NEW: columns = [{"name": "id", "type": "INTEGER", "pk": 1, ...}]  ✅

Usage:
    python extract_schema.py
    OR
    python extract_schema.py store_data.db
    OR
    python extract_schema.py /path/to/database.db

Changes:
- CRIT-001 FIXED: Columns are now dict objects
- CRIT-001 FIXED: Foreign keys are now dict objects
- Schema version bumped to 2.0
- Added format validation
- Backward compatible with old code that expects 'types' dict
"""

import sqlite3
import json
import os
import sys
import logging
from datetime import datetime

# Setup logging - Use config if available
try:
    import config
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
        format=config.LOG_FORMAT
    )
except ImportError:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

logger = logging.getLogger(__name__)


class SchemaExtractor:
    """Extracts schema from SQLite database - FIXED VERSION"""
    
    def __init__(self, db_path="store_data.db"):
        self.db_path = db_path
        logger.info(f"SchemaExtractor initialized with database: {db_path}")
    
    def extract_schema(self):
        """
        Extract complete database schema with STANDARDIZED format
        
        Returns:
            dict: {
                "tables": {
                    "table_name": {
                        "columns": [
                            {
                                "name": "col_name",
                                "type": "INTEGER",
                                "pk": 1,
                                "notnull": 1,
                                "dflt_value": None
                            },
                            ...
                        ],
                        "types": {"col_name": "INTEGER", ...},  # For backward compatibility
                        "primary_key": "id",
                        "foreign_keys": [
                            {
                                "from_column": "store_id",
                                "to_table": "stores",
                                "to_column": "id"
                            },
                            ...
                        ]
                    }
                }
            }
        """
        try:
            # Verify database exists
            if not os.path.exists(self.db_path):
                logger.error(f"Database file not found: {self.db_path}")
                raise FileNotFoundError(f"Database file not found: {self.db_path}")
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            logger.info("Connected to database successfully")
            
            # Get all tables
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
            """)
            tables = [row[0] for row in cursor.fetchall()]
            logger.info(f"Found {len(tables)} tables")
            
            if len(tables) == 0:
                logger.warning("No tables found in database")
                print("⚠️  Warning: No tables found in database")
            
            schema = {"tables": {}}
            
            for table_name in tables:
                logger.info(f"Extracting schema for table: {table_name}")
                table_info = self._extract_table_info(cursor, table_name)
                schema["tables"][table_name] = table_info
            
            conn.close()
            logger.info("Schema extraction completed successfully")
            
            return schema
        
        except FileNotFoundError as e:
            logger.error(f"Database file error: {str(e)}")
            print(f"❌ Error: {str(e)}")
            return {"tables": {}}
        except Exception as e:
            logger.error(f"Error extracting schema: {str(e)}")
            print(f"❌ Error extracting schema: {str(e)}")
            return {"tables": {}}
    
    def _extract_table_info(self, cursor, table_name):
        """
        Extract information for a single table - FIXED VERSION
        
        CRITICAL CHANGE: Returns columns as list of dicts, not strings
        """
        try:
            # Get column information using PRAGMA table_info
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns_raw = cursor.fetchall()
            
            # FIXED: Build list of column DICTS instead of strings
            columns = []
            types = {}  # Keep for backward compatibility
            primary_key = None
            
            for col_info in columns_raw:
                # PRAGMA table_info returns: (cid, name, type, notnull, dflt_value, pk)
                cid = col_info[0]
                col_name = col_info[1]
                col_type = col_info[2] if col_info[2] else "TEXT"  # Default to TEXT
                notnull = col_info[3]
                dflt_value = col_info[4]
                pk = col_info[5]
                
                # NEW FORMAT: Build column dict with full metadata
                column_dict = {
                    "name": col_name,
                    "type": col_type,
                    "pk": pk,
                    "notnull": notnull,
                    "dflt_value": dflt_value
                }
                
                columns.append(column_dict)  # ✅ Append dict, not string
                
                # Keep types dict for backward compatibility
                types[col_name] = col_type
                
                # Track primary key
                if pk:
                    primary_key = col_name
            
            logger.info(f"  → Found {len(columns)} columns in {table_name}")
            
            # Get foreign keys - ALSO FIXED to return dicts
            cursor.execute(f"PRAGMA foreign_key_list({table_name})")
            fk_raw = cursor.fetchall()
            
            foreign_keys = []
            for fk_info in fk_raw:
                # PRAGMA foreign_key_list returns: (id, seq, table, from, to, on_update, on_delete, match)
                
                # NEW FORMAT: Build FK dict
                fk_dict = {
                    "from_column": fk_info[3],
                    "to_table": fk_info[2],
                    "to_column": fk_info[4]
                }
                
                foreign_keys.append(fk_dict)  # ✅ Append dict, not string
            
            if foreign_keys:
                logger.info(f"  → Found {len(foreign_keys)} foreign keys in {table_name}")
            
            return {
                "columns": columns,  # ✅ NOW: List of dicts
                "types": types,      # Kept for backward compatibility
                "primary_key": primary_key,
                "foreign_keys": foreign_keys  # ✅ NOW: List of dicts
            }
        
        except Exception as e:
            logger.error(f"Error extracting table info for {table_name}: {str(e)}")
            return {
                "columns": [],
                "types": {},
                "primary_key": None,
                "foreign_keys": []
            }


class SchemaConfigGenerator:
    """Generates schema configuration files from database"""
    
    def __init__(self, db_path="store_data.db", output_dir="config"):
        self.db_path = db_path
        self.output_dir = output_dir
        self.extractor = SchemaExtractor(db_path)
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"Output directory: {output_dir}")
    
    def run(self):
        """Main execution - extracts schema and generates all config files"""
        print("\n" + "="*80)
        print("🔍 SCHEMA EXTRACTION PROCESS STARTED (STANDARDIZED FORMAT v2.0)")
        print("="*80)
        print(f"\n📂 Database: {self.db_path}")
        print(f"📁 Output Directory: {self.output_dir}")
        print(f"🕐 Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        try:
            # Step 1: Verify database exists
            print("Step 1: Verifying database...")
            if not os.path.exists(self.db_path):
                print(f"❌ FAILED: Database file not found at {self.db_path}")
                logger.error(f"Database file not found: {self.db_path}")
                return False
            print("✅ Database verified\n")
            
            # Step 2: Extract schema
            print("Step 2: Extracting database schema (STANDARDIZED FORMAT)...")
            schema = self.extractor.extract_schema()
            
            if not schema or 'tables' not in schema or len(schema['tables']) == 0:
                print("❌ FAILED: Could not extract schema from database")
                print("  Possible causes:")
                print("  - Database has no tables")
                print("  - Database is corrupted")
                print("  - Insufficient permissions")
                logger.error("No tables found in database")
                return False
            
            table_count = len(schema['tables'])
            print(f"✅ Extracted schema for {table_count} table(s)\n")
            
            # Step 2.5: Verify format is correct
            print("Step 2.5: Verifying schema format...")
            format_valid = self._verify_schema_format(schema)
            if not format_valid:
                print("❌ WARNING: Schema format validation failed")
                return False
            print("✅ Schema format validated (all columns are dicts)\n")
            
            # Step 3: Generate schema_config.json
            print("Step 3: Generating schema_config.json...")
            self._save_schema_config(schema)
            schema_config_path = os.path.join(self.output_dir, 'schema_config.json')
            print(f"✅ schema_config.json created at: {schema_config_path}\n")
            
            # Step 4: Generate column mappings
            print("Step 4: Generating column_mappings.json...")
            column_mappings = self._generate_column_mappings(schema)
            self._save_column_mappings(column_mappings)
            column_mappings_path = os.path.join(self.output_dir, 'column_mappings.json')
            print(f"✅ column_mappings.json created at: {column_mappings_path}\n")
            
            # Step 5: Generate human-readable summary
            print("Step 5: Generating schema_summary.txt...")
            self._generate_summary(schema)
            schema_summary_path = os.path.join(self.output_dir, 'schema_summary.txt')
            print(f"✅ schema_summary.txt created at: {schema_summary_path}\n")
            
            # Step 6: Generate debug info
            print("Step 6: Generating debug information...")
            self._generate_debug_info(schema)
            debug_path = os.path.join(self.output_dir, 'schema_debug.json')
            print(f"✅ schema_debug.json created at: {debug_path}\n")
            
            print("="*80)
            print("✅ SCHEMA EXTRACTION COMPLETE (STANDARDIZED FORMAT v2.0)")
            print("="*80)
            print("\n📦 Generated Files:")
            print(f"  1. {os.path.join(self.output_dir, 'schema_config.json')} - Complete schema (DICT FORMAT)")
            print(f"  2. {os.path.join(self.output_dir, 'column_mappings.json')} - Column lookup")
            print(f"  3. {os.path.join(self.output_dir, 'schema_summary.txt')} - Documentation")
            print(f"  4. {os.path.join(self.output_dir, 'schema_debug.json')} - Debug info")
            
            print("\n📋 Schema Summary:")
            print(f"  Tables: {table_count}")
            for table_name, table_info in schema['tables'].items():
                col_count = len(table_info.get('columns', []))
                fk_count = len(table_info.get('foreign_keys', []))
                print(f"  • {table_name}: {col_count} columns, {fk_count} foreign keys")
            
            print("\n✅ FORMAT VERIFICATION:")
            print("  • All columns are dict objects with keys: name, type, pk, notnull, dflt_value")
            print("  • All foreign keys are dict objects with keys: from_column, to_table, to_column")
            print("  • Backward compatible: 'types' dict still included")
            
            print("\n🚀 Next Steps:")
            print("  1. Verify schema_config.json was generated correctly")
            print("  2. Update config.py with correct paths")
            print("  3. Run: python -m streamlit run app.py\n")
            
            return True
        
        except Exception as e:
            print(f"❌ FAILED: {str(e)}")
            logger.error(f"Schema extraction failed: {str(e)}")
            return False
    
    def _verify_schema_format(self, schema):
        """Verify that schema follows the standardized format"""
        for table_name, table_info in schema.get('tables', {}).items():
            columns = table_info.get('columns', [])
            
            # Verify all columns are dicts
            for col in columns:
                if not isinstance(col, dict):
                    print(f"  ❌ Column in {table_name} is not a dict: {col}")
                    return False
                
                # Verify required keys
                required_keys = ['name', 'type', 'pk', 'notnull']
                for key in required_keys:
                    if key not in col:
                        print(f"  ❌ Column in {table_name} missing key '{key}': {col}")
                        return False
            
            # Verify foreign keys are dicts (if any)
            fks = table_info.get('foreign_keys', [])
            for fk in fks:
                if not isinstance(fk, dict):
                    print(f"  ❌ Foreign key in {table_name} is not a dict: {fk}")
                    return False
                
                required_fk_keys = ['from_column', 'to_table', 'to_column']
                for key in required_fk_keys:
                    if key not in fk:
                        print(f"  ❌ Foreign key in {table_name} missing key '{key}': {fk}")
                        return False
        
        return True
    
    def _save_schema_config(self, schema):
        """Save complete schema to JSON"""
        config = {
            "extracted_at": datetime.now().isoformat(),
            "database": self.db_path,
            "schema_version": "2.0",  # ✅ UPDATED VERSION
            "format": "STANDARDIZED_DICT",  # ✅ NEW: Format indicator
            "tables": schema['tables']
        }
        
        filepath = os.path.join(self.output_dir, 'schema_config.json')
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved schema config to {filepath}")
    
    def _generate_column_mappings(self, schema):
        """Generate quick column name lookup mappings"""
        mappings = {}
        
        for table_name, table_info in schema.get('tables', {}).items():
            columns = table_info.get('columns', [])
            
            # Extract column names from dict format
            column_names = [col['name'] for col in columns]
            
            table_mappings = {}
            for col_dict in columns:
                col_name = col_dict['name']
                table_mappings[col_name] = col_name
                
                # Normalized version (lowercase, no underscores)
                normalized = col_name.lower().replace('_', '').replace('-', '')
                table_mappings[normalized] = col_name
            
            mappings[table_name] = {
                "columns": column_names,
                "column_lookup": table_mappings,
                "primary_key": table_info.get('primary_key'),
                "foreign_keys": table_info.get('foreign_keys', [])
            }
        
        return mappings
    
    def _save_column_mappings(self, mappings):
        """Save column mappings to JSON"""
        config = {
            "extracted_at": datetime.now().isoformat(),
            "mappings": mappings
        }
        
        filepath = os.path.join(self.output_dir, 'column_mappings.json')
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved column mappings to {filepath}")
    
    def _generate_summary(self, schema):
        """Generate human-readable schema documentation"""
        lines = []
        lines.append("="*80)
        lines.append("DATABASE SCHEMA SUMMARY (STANDARDIZED FORMAT v2.0)")
        lines.append("="*80)
        lines.append(f"\nExtracted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Database: {self.db_path}")
        lines.append(f"Tables: {len(schema['tables'])}")
        lines.append(f"Format: DICT (columns are dict objects)\n")
        
        for table_name, table_info in schema.get('tables', {}).items():
            lines.append("\n" + "-"*80)
            lines.append(f"TABLE: {table_name}")
            lines.append("-"*80)
            
            columns = table_info.get('columns', [])
            lines.append(f"\nColumns ({len(columns)}):")
            
            for col_dict in columns:
                col_name = col_dict['name']
                col_type = col_dict['type']
                pk_marker = " [PRIMARY KEY]" if col_dict['pk'] else ""
                notnull_marker = " [NOT NULL]" if col_dict['notnull'] else ""
                default = f" DEFAULT {col_dict['dflt_value']}" if col_dict.get('dflt_value') else ""
                
                lines.append(f"  • {col_name:30s} {col_type:15s}{pk_marker}{notnull_marker}{default}")
            
            pk = table_info.get('primary_key')
            if pk:
                lines.append(f"\nPrimary Key: {pk}")
            
            fks = table_info.get('foreign_keys', [])
            if fks:
                lines.append("\nForeign Keys:")
                for fk_dict in fks:
                    lines.append(f"  • {fk_dict['from_column']} → {fk_dict['to_table']}.{fk_dict['to_column']}")
        
        lines.append("\n" + "="*80)
        lines.append("END OF SCHEMA SUMMARY")
        lines.append("="*80)
        
        filepath = os.path.join(self.output_dir, 'schema_summary.txt')
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        logger.info(f"Saved schema summary to {filepath}")
    
    def _generate_debug_info(self, schema):
        """Generate debug information"""
        debug_info = {
            "extraction_time": datetime.now().isoformat(),
            "database_path": self.db_path,
            "database_exists": os.path.exists(self.db_path),
            "table_count": len(schema.get('tables', {})),
            "schema_version": "2.0",
            "format": "STANDARDIZED_DICT",
            "tables": {},
            "errors": []
        }
        
        for table_name, table_info in schema.get('tables', {}).items():
            columns = table_info.get('columns', [])
            debug_info["tables"][table_name] = {
                "column_count": len(columns),
                "columns_format": "dict" if all(isinstance(c, dict) for c in columns) else "mixed",
                "sample_column": columns[0] if columns else None,
                "primary_key": table_info.get('primary_key'),
                "foreign_key_count": len(table_info.get('foreign_keys', []))
            }
        
        filepath = os.path.join(self.output_dir, 'schema_debug.json')
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(debug_info, f, indent=2)
        
        logger.info(f"Saved debug info to {filepath}")


def main():
    """Main entry point"""
    print("\n")
    
    # Get database path from command line or use default
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        # Try to load from config if available
        db_path = "store_data.db"
        try:
            import config
            db_path = config.DB_PATH
        except:
            pass
    
    print(f"Using database: {db_path}\n")
    
    generator = SchemaConfigGenerator(db_path=db_path, output_dir="config")
    success = generator.run()
    
    if success:
        print("✅ SUCCESS: Schema extraction completed (STANDARDIZED FORMAT v2.0)!\n")
        sys.exit(0)
    else:
        print("❌ FAILED: Schema extraction failed.\n")
        print("Troubleshooting steps:")
        print("1. Verify database file exists")
        print("2. Check database path: python extract_schema.py /path/to/database.db")
        print("3. Ensure database has tables")
        print("4. Check logs for detailed errors\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
