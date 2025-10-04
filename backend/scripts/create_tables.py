#!/usr/bin/env python3
"""
Create All Database Tables Script

This script creates all tables for the FastAPI Book Reading Platform
using SQLAlchemy models.

Usage:
    python scripts/create_tables.py
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

def create_all_tables():
    """Create all database tables."""
    print("🏗️  Creating All Database Tables")
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
        
        # Create all tables
        print("🔨 Creating tables...")
        Base.metadata.create_all(bind=engine)
        
        # Verify tables were created
        with engine.connect() as conn:
            tables_result = conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """)).fetchall()
            
            table_names = [row[0] for row in tables_result]
            
            print(f"✅ Successfully created {len(table_names)} tables:")
            for table in table_names:
                print(f"  - {table}")
            
            # Check constraints
            constraints_result = conn.execute(text("""
                SELECT 
                    tc.table_name, 
                    COUNT(*) as constraint_count
                FROM information_schema.table_constraints tc
                WHERE tc.table_schema = 'public'
                GROUP BY tc.table_name
                ORDER BY tc.table_name
            """)).fetchall()
            
            print(f"\n🔗 Table constraints:")
            for table, count in constraints_result:
                print(f"  - {table}: {count} constraints")
        
        engine.dispose()
        print(f"\n🎉 All tables created successfully!")
        return True
        
    except SQLAlchemyError as e:
        print(f"❌ Database error: {str(e)}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return False

def main():
    """Main function."""
    success = create_all_tables()
    
    if success:
        print(f"\n📋 Next steps:")
        print(f"  1. Run: python scripts/seed_data.py")
        print(f"  2. Or run: python scripts/truncate_data.py")
        sys.exit(0)
    else:
        print(f"\n❌ Table creation failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
