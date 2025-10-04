#!/usr/bin/env python3
"""
Drop All Database Tables Script

This script drops all tables from the FastAPI Book Reading Platform database.
WARNING: This will completely remove all tables and data!

Usage:
    python scripts/drop_tables.py
"""

import sys
import os
from pathlib import Path

# Add the backend directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# Import settings and database base
from app.core.settings import settings
from app.core.database import Base

# Import all models to register them with Base.metadata
from app.models.user import User
from app.models.author import Author
from app.models.category import Category
from app.models.book import Book
from app.models.chapter import Chapter
from app.models.favorite import Favorite
from app.models.reading_progress import ReadingProgress
from app.models.reading_list import ReadingList, ReadingListItem

def drop_all_tables():
    """Drop all database tables."""
    print("💥 Dropping All Database Tables")
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
            # Get all table names before dropping
            tables_result = conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """)).fetchall()
            
            table_names = [row[0] for row in tables_result]
            
            if not table_names:
                print("✅ No tables found to drop")
                return True
            
            print(f"📋 Found {len(table_names)} tables to drop:")
            for table in table_names:
                print(f"  - {table}")
            
            # Count total records before dropping
            print(f"\n📊 Data summary before dropping:")
            total_records = 0
            for table in table_names:
                try:
                    count_result = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).fetchone()
                    count = count_result[0] if count_result else 0
                    print(f"  - {table}: {count} records")
                    total_records += count
                except Exception as e:
                    print(f"  - {table}: Error counting ({str(e)})")
            
            print(f"  Total records that will be lost: {total_records}")
            
            # Method 1: Use SQLAlchemy metadata (preferred)
            print(f"\n🔥 Dropping tables using SQLAlchemy metadata...")
            try:
                Base.metadata.drop_all(bind=engine)
                print(f"  ✅ SQLAlchemy drop completed")
                
                # Verify tables were dropped
                remaining_tables = conn.execute(text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_type = 'BASE TABLE'
                """)).fetchall()
                
                if not remaining_tables:
                    print(f"  ✅ All tables successfully dropped")
                    print(f"\n🎉 Table dropping completed!")
                    return True
                else:
                    print(f"  ⚠️  {len(remaining_tables)} tables still remain")
                    for table in remaining_tables:
                        print(f"    - {table[0]}")
                    
            except Exception as e:
                print(f"  ❌ SQLAlchemy drop failed: {str(e)}")
                print(f"  🔄 Trying manual drop with CASCADE...")
            
            # Method 2: Manual drop with CASCADE (fallback)
            print(f"\n🔥 Dropping tables manually with CASCADE...")
            
            # No manual transaction - use autocommit
            try:
                dropped_tables = []
                
                # Drop in reverse dependency order (children first)
                drop_order = [
                    'reading_list_items',
                    'reading_lists', 
                    'reading_progress',
                    'favorites',
                    'chapters',
                    'books',
                    'authors',
                    'categories',
                    'users'
                ]
                
                # Drop tables in order
                for table in drop_order:
                    if table in table_names:
                        try:
                            conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
                            print(f"  ✅ Dropped: {table}")
                            dropped_tables.append(table)
                        except Exception as e:
                            print(f"  ❌ Failed to drop {table}: {str(e)}")
                
                # Drop any remaining tables not in the order list
                remaining_tables = [t for t in table_names if t not in drop_order]
                for table in remaining_tables:
                    try:
                        conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
                        print(f"  ✅ Dropped: {table}")
                        dropped_tables.append(table)
                    except Exception as e:
                        print(f"  ❌ Failed to drop {table}: {str(e)}")
                
                # No manual commit needed with autocommit
                
                # Final verification
                final_tables = conn.execute(text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_type = 'BASE TABLE'
                """)).fetchall()
                
                if not final_tables:
                    print(f"\n✅ All tables successfully dropped!")
                    print(f"📋 Dropped {len(dropped_tables)} tables")
                else:
                    print(f"\n⚠️  {len(final_tables)} tables still remain:")
                    for table in final_tables:
                        print(f"  - {table[0]}")
                
                print(f"\n🎉 Table dropping completed!")
                return True
                
            except Exception as e:
                print(f"❌ Manual drop failed: {str(e)}")
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
    print("⚠️  DANGER: This will PERMANENTLY DELETE ALL TABLES and DATA!")
    print("This action cannot be undone. All tables and data will be lost.")
    print("Make sure you have backups if needed.")
    print()
    
    # In a real scenario, you might want to add a confirmation prompt
    # For automation, we'll proceed directly
    
    success = drop_all_tables()
    
    if success:
        print(f"\n📋 Next steps:")
        print(f"  1. Run: python scripts/create_tables.py (to recreate tables)")
        print(f"  2. Run: python scripts/seed_data.py (to add sample data)")
        sys.exit(0)
    else:
        print(f"\n❌ Table dropping failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
