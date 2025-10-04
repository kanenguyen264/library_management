#!/usr/bin/env python3
"""
Simple and Reliable Data Seeding Script

This script seeds data with a simple, batch-by-batch approach:
- Users: 1 admin account (admin/admin123)
- Each table: 100 records with proper error handling
- Simple logic, reliable execution

Usage:
    python scripts/simple_seed.py
"""

import sys
import os
from pathlib import Path
from datetime import datetime, date, timedelta
import random

# Add the backend directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import settings and models
from app.core.settings import settings
from app.core.auth import get_password_hash
from app.models.user import User
from app.models.author import Author
from app.models.category import Category
from app.models.book import Book
from app.models.chapter import Chapter
from app.models.favorite import Favorite
from app.models.reading_progress import ReadingProgress
from app.models.reading_list import ReadingList, ReadingListItem

def get_session():
    """Get database session."""
    engine = create_engine(settings.DATABASE_URL + "?sslmode=require", echo=False)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal(), engine

def seed_admin_user(session):
    """Seed 1 admin user."""
    print("👤 Seeding admin user...")
    
    try:
        # Check if exists
        existing = session.query(User).filter(User.username == "admin").first()
        if existing:
            print("  ⚠️  Admin already exists")
            return existing
        
        admin = User(
            email="admin@bookhub.com",
            username="admin",
            full_name="System Administrator",
            hashed_password=get_password_hash("admin123"),
            is_active=True,
            is_admin=True,
            bio="System administrator"
        )
        session.add(admin)
        session.commit()
        
        print("  ✅ Created admin user")
        return admin
        
    except Exception as e:
        session.rollback()
        print(f"  ❌ Error: {str(e)}")
        return None

def seed_categories(session, count=100):
    """Seed categories."""
    print(f"📚 Seeding {count} categories...")
    
    try:
        created = 0
        for i in range(count):
            name = f"Category {i + 1:03d}"
            slug = f"category-{i + 1:03d}"
            
            category = Category(
                name=name,
                slug=slug,
                description=f"Description for {name}",
                is_active=True
            )
            session.add(category)
            created += 1
            
            # Commit every 20 records to avoid large transactions
            if created % 20 == 0:
                session.commit()
        
        session.commit()  # Final commit
        print(f"  ✅ Created {created} categories")
        
        # Return all categories for foreign keys
        return session.query(Category).all()
        
    except Exception as e:
        session.rollback()
        print(f"  ❌ Error: {str(e)}")
        return []

def seed_authors(session, count=100):
    """Seed authors."""
    print(f"✍️  Seeding {count} authors...")
    
    try:
        created = 0
        for i in range(count):
            name = f"Author {i + 1:03d}"
            
            author = Author(
                name=name,
                bio=f"Biography of {name}",
                birth_date=date(1950 + (i % 50), 1 + (i % 12), 1 + (i % 28)),
                nationality=f"Country {(i % 10) + 1}"
            )
            session.add(author)
            created += 1
            
            # Commit every 20 records
            if created % 20 == 0:
                session.commit()
        
        session.commit()
        print(f"  ✅ Created {created} authors")
        
        return session.query(Author).all()
        
    except Exception as e:
        session.rollback()
        print(f"  ❌ Error: {str(e)}")
        return []

def seed_books(session, authors, categories, count=100):
    """Seed books."""
    print(f"📖 Seeding {count} books...")
    
    if not authors or not categories:
        print("  ❌ Need authors and categories first")
        return []
    
    try:
        created = 0
        for i in range(count):
            title = f"Book {i + 1:03d}"
            
            book = Book(
                title=title,
                description=f"Description of {title}",
                publication_date=date(2000 + (i % 24), 1 + (i % 12), 1 + (i % 28)),
                pages=100 + (i % 400),
                language="English",
                isbn=f"978-{1000000000 + i:010d}",
                is_free=i % 2 == 0,  # Half free, half paid
                price=None if i % 2 == 0 else round(10 + (i % 20), 2),
                is_active=True,
                author_id=random.choice(authors).id,
                category_id=random.choice(categories).id
            )
            session.add(book)
            created += 1
            
            if created % 20 == 0:
                session.commit()
        
        session.commit()
        print(f"  ✅ Created {created} books")
        
        return session.query(Book).all()
        
    except Exception as e:
        session.rollback()
        print(f"  ❌ Error: {str(e)}")
        return []

def seed_chapters(session, books, count=100):
    """Seed chapters."""
    print(f"📃 Seeding {count} chapters...")
    
    if not books:
        print("  ❌ Need books first")
        return []
    
    try:
        created = 0
        for i in range(count):
            book = random.choice(books)
            title = f"Chapter {i + 1:03d}"
            
            chapter = Chapter(
                book_id=book.id,
                title=title,
                chapter_number=i + 1,
                content=f"Content of {title} " * 20,
                word_count=100 + (i % 500),
                is_published=True,
                is_active=True
            )
            session.add(chapter)
            created += 1
            
            if created % 20 == 0:
                session.commit()
        
        session.commit()
        print(f"  ✅ Created {created} chapters")
        return True
        
    except Exception as e:
        session.rollback()
        print(f"  ❌ Error: {str(e)}")
        return False

def seed_favorites(session, admin_user, books, count=100):
    """Seed favorites."""
    print(f"❤️  Seeding {count} favorites...")
    
    if not admin_user or not books:
        print("  ❌ Need admin user and books first")
        return False
    
    try:
        # Select random books for favorites (avoid duplicates)
        selected_books = random.sample(books, min(count, len(books)))
        
        created = 0
        for book in selected_books:
            favorite = Favorite(
                user_id=admin_user.id,
                book_id=book.id
            )
            session.add(favorite)
            created += 1
            
            if created % 20 == 0:
                session.commit()
        
        session.commit()
        print(f"  ✅ Created {created} favorites")
        return True
        
    except Exception as e:
        session.rollback()
        print(f"  ❌ Error: {str(e)}")
        return False

def seed_reading_lists(session, admin_user, count=100):
    """Seed reading lists."""
    print(f"📋 Seeding {count} reading lists...")
    
    if not admin_user:
        print("  ❌ Need admin user first")
        return []
    
    try:
        created = 0
        for i in range(count):
            name = f"Reading List {i + 1:03d}"
            
            reading_list = ReadingList(
                user_id=admin_user.id,
                name=name,
                description=f"Description for {name}",
                is_public=i % 3 == 0  # Every 3rd list is public
            )
            session.add(reading_list)
            created += 1
            
            if created % 20 == 0:
                session.commit()
        
        session.commit()
        print(f"  ✅ Created {created} reading lists")
        
        return session.query(ReadingList).all()
        
    except Exception as e:
        session.rollback()
        print(f"  ❌ Error: {str(e)}")
        return []

def seed_reading_list_items(session, reading_lists, books, count=100):
    """Seed reading list items."""
    print(f"📑 Seeding {count} reading list items...")
    
    if not reading_lists or not books:
        print("  ❌ Need reading lists and books first")
        return False
    
    try:
        created = 0
        for i in range(count):
            reading_list = random.choice(reading_lists)
            book = random.choice(books)
            
            item = ReadingListItem(
                reading_list_id=reading_list.id,
                book_id=book.id,
                order=i + 1
            )
            session.add(item)
            created += 1
            
            if created % 20 == 0:
                session.commit()
        
        session.commit()
        print(f"  ✅ Created {created} reading list items")
        return True
        
    except Exception as e:
        session.rollback()
        print(f"  ❌ Error: {str(e)}")
        return False

def seed_reading_progress(session, admin_user, books, count=100):
    """Seed reading progress."""
    print(f"📊 Seeding {count} reading progress records...")
    
    if not admin_user or not books:
        print("  ❌ Need admin user and books first")
        return False
    
    try:
        # Select random books
        selected_books = random.sample(books, min(count, len(books)))
        
        created = 0
        for book in selected_books:
            current_page = random.randint(0, book.pages)
            progress_percentage = round((current_page / book.pages) * 100, 2) if book.pages > 0 else 0
            
            status = "not_started"
            is_completed = False
            if progress_percentage > 0 and progress_percentage < 100:
                status = "reading"
            elif progress_percentage == 100:
                status = "completed"
                is_completed = True
            
            progress = ReadingProgress(
                user_id=admin_user.id,
                book_id=book.id,
                current_page=current_page,
                total_pages=book.pages,
                progress_percentage=progress_percentage,
                reading_time_minutes=random.randint(30, 300),
                status=status,
                is_completed=is_completed,
                started_at=datetime.now() - timedelta(days=random.randint(1, 100)),
                last_read_at=datetime.now() - timedelta(days=random.randint(0, 10))
            )
            session.add(progress)
            created += 1
            
            if created % 20 == 0:
                session.commit()
        
        session.commit()
        print(f"  ✅ Created {created} reading progress records")
        return True
        
    except Exception as e:
        session.rollback()
        print(f"  ❌ Error: {str(e)}")
        return False

def main():
    """Main seeding function."""
    print("🌱 Simple and Reliable Data Seeding")
    print("=" * 50)
    print(f"Environment: {settings.ENVIRONMENT}")
    print(f"Database: {settings.DATABASE_URL[:50]}...")
    print()
    
    session, engine = get_session()
    
    try:
        # Seed in dependency order
        admin_user = seed_admin_user(session)
        if not admin_user:
            print("❌ Failed to create admin user")
            return False
        
        categories = seed_categories(session, 100)
        if not categories:
            print("❌ Failed to create categories")
            return False
        
        authors = seed_authors(session, 100)
        if not authors:
            print("❌ Failed to create authors")
            return False
        
        books = seed_books(session, authors, categories, 100)
        if not books:
            print("❌ Failed to create books")
            return False
        
        seed_chapters(session, books, 100)
        seed_favorites(session, admin_user, books, 100)
        
        reading_lists = seed_reading_lists(session, admin_user, 100)
        if reading_lists:
            seed_reading_list_items(session, reading_lists, books, 100)
        
        seed_reading_progress(session, admin_user, books, 100)
        
        # Final summary
        print(f"\n📊 Seeding Summary:")
        print(f"  - Users: 1 admin")
        print(f"  - Categories: {len(categories)}")
        print(f"  - Authors: {len(authors)}")  
        print(f"  - Books: {len(books)}")
        print(f"  - Other tables: ~100 records each")
        
        print(f"\n🔐 Admin Login:")
        print(f"  Username: admin")
        print(f"  Password: admin123")
        
        print(f"\n🎉 Seeding completed successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        return False
    finally:
        session.close()
        engine.dispose()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
