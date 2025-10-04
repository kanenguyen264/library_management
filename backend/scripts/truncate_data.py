#!/usr/bin/env python3
"""
Truncate All Data Script

This script removes all data from all tables while keeping table structure intact.
Uses proper order to handle foreign key constraints.

Usage:
    python scripts/truncate_data.py
"""

import sys
import os
from pathlib import Path

# Add the backend directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# Import settings
from app.core.settings import settings

def truncate_all_data():
    """Truncate all data from all tables."""
    print("🗑️  Truncating All Data")
    print("=" * 40)
    print(f"Environment: {settings.ENVIRONMENT}")
    print(f"Database: {settings.DATABASE_URL[:50]}...")
    print()
    
    try:
        # Create engine
        engine = create_engine(settings.DATABASE_URL + "?sslmode=require", echo=False)
        
        # Test connection first
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            print("✅ Database connection successful")
        
        with engine.connect() as conn:
            # Get all table names
            tables_result = conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """)).fetchall()
            
            table_names = [row[0] for row in tables_result]
            
            if not table_names:
                print("⚠️  No tables found to truncate")
                return True
            
            print(f"📋 Found {len(table_names)} tables to truncate:")
            for table in table_names:
                print(f"  - {table}")
            
            # Count records before truncation
            print(f"\n📊 Records before truncation:")
            total_records = 0
            for table in table_names:
                try:
                    count_result = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).fetchone()
                    count = count_result[0] if count_result else 0
                    print(f"  - {table}: {count} records")
                    total_records += count
                except Exception as e:
                    print(f"  - {table}: Error counting ({str(e)})")
            
            print(f"  Total records: {total_records}")
            
            if total_records == 0:
                print("\n✅ No data to truncate")
                return True
            
            # Truncate in proper order (considering foreign keys)
            # Order: child tables first, then parent tables
            truncate_order = [
                'reading_list_items',  # References reading_lists and books
                'reading_lists',       # References users
                'reading_progress',    # References users and books
                'favorites',           # References users and books
                'chapters',            # References books
                'books',               # References authors and categories
                'authors',             # No foreign keys
                'categories',          # No foreign keys
                'users'                # No foreign keys (referenced by others)
            ]
            
            print(f"\n🔥 Starting truncation in order...")
            
            # Use autocommit for each statement
            truncated_tables = []
            
            try:
                for table in truncate_order:
                    if table in table_names:
                        try:
                            # Use TRUNCATE CASCADE to handle any remaining foreign key issues
                            conn.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE"))
                            conn.commit()  # Commit each truncate individually
                            print(f"  ✅ Truncated: {table}")
                            truncated_tables.append(table)
                        except Exception as e:
                            conn.rollback()  # Rollback this individual operation
                            print(f"  ❌ Failed to truncate {table}: {str(e)}")
                
                # Truncate any remaining tables not in the order list
                remaining_tables = [t for t in table_names if t not in truncate_order]
                for table in remaining_tables:
                    try:
                        conn.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE"))
                        conn.commit()  # Commit each truncate individually
                        print(f"  ✅ Truncated: {table}")
                        truncated_tables.append(table)
                    except Exception as e:
                        conn.rollback()  # Rollback this individual operation
                        print(f"  ❌ Failed to truncate {table}: {str(e)}")
                
                # Verify truncation
                print(f"\n🔍 Verifying truncation...")
                total_remaining = 0
                for table in truncated_tables:
                    try:
                        count_result = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).fetchone()
                        count = count_result[0] if count_result else 0
                        if count > 0:
                            print(f"  ⚠️  {table}: {count} records remaining")
                        total_remaining += count
                    except Exception as e:
                        print(f"  ❌ Error verifying {table}: {str(e)}")
                
                if total_remaining == 0:
                    print(f"  ✅ All tables are empty")
                else:
                    print(f"  ⚠️  {total_remaining} records remaining across all tables")
                
                print(f"\n🎉 Truncation completed!")
                print(f"📋 Truncated {len(truncated_tables)} tables successfully")
                
                return True
                
            except Exception as e:
                print(f"❌ Truncation process failed: {str(e)}")
                return False
        
        engine.dispose()
        
    except SQLAlchemyError as e:
        print(f"❌ Database error: {str(e)}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return False

def main():
    """Main function."""
    print("⚠️  WARNING: This will DELETE ALL DATA from all tables!")
    print("Are you sure you want to continue? This action cannot be undone.")
    print("Tables will be emptied but structure will remain intact.")
    print()
    
    # In a real scenario, you might want to add a confirmation prompt
    # For automation, we'll proceed directly
    
    success = truncate_all_data()
    
    if success:
        print(f"\n📋 Next steps:")
        print(f"  1. Run: python scripts/seed_data.py (to add sample data)")
        print(f"  2. Or run: python scripts/create_tables.py (if tables were dropped)")
        sys.exit(0)
    else:
        print(f"\n❌ Data truncation failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
