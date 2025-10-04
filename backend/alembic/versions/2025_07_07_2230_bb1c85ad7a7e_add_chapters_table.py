"""Create all database tables

Revision ID: bb1c85ad7a7e
Revises: 
Create Date: 2025-07-07 22:30:16.730707

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'bb1c85ad7a7e'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### Create all database tables ###
    
    # Create users table
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('username', sa.String(), nullable=False),
    sa.Column('full_name', sa.String(), nullable=False),
    sa.Column('hashed_password', sa.String(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('is_admin', sa.Boolean(), nullable=True),
    sa.Column('avatar_url', sa.String(), nullable=True),
    sa.Column('bio', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    
    # Create authors table
    op.create_table('authors',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('bio', sa.Text(), nullable=True),
    sa.Column('birth_date', sa.Date(), nullable=True),
    sa.Column('death_date', sa.Date(), nullable=True),
    sa.Column('nationality', sa.String(), nullable=True),
    sa.Column('website', sa.String(), nullable=True),
    sa.Column('image_url', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_authors_id'), 'authors', ['id'], unique=False)
    op.create_index(op.f('ix_authors_name'), 'authors', ['name'], unique=False)
    
    # Create categories table
    op.create_table('categories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('slug', sa.String(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name'),
    sa.UniqueConstraint('slug')
    )
    op.create_index(op.f('ix_categories_id'), 'categories', ['id'], unique=False)
    op.create_index(op.f('ix_categories_name'), 'categories', ['name'], unique=True)
    op.create_index(op.f('ix_categories_slug'), 'categories', ['slug'], unique=True)
    
    # Create books table
    op.create_table('books',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('isbn', sa.String(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('publication_date', sa.Date(), nullable=True),
    sa.Column('pages', sa.Integer(), nullable=True),
    sa.Column('language', sa.String(), nullable=True),
    sa.Column('cover_url', sa.String(), nullable=True),
    sa.Column('pdf_url', sa.String(), nullable=True),
    sa.Column('epub_url', sa.String(), nullable=True),
    sa.Column('price', sa.Float(), nullable=True),
    sa.Column('is_free', sa.Boolean(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('author_id', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['author_id'], ['authors.id'], ),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('isbn')
    )
    op.create_index(op.f('ix_books_id'), 'books', ['id'], unique=False)
    op.create_index(op.f('ix_books_title'), 'books', ['title'], unique=False)
    
    # Create reading_progress table
    op.create_table('reading_progress',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('book_id', sa.Integer(), nullable=False),
    sa.Column('current_page', sa.Integer(), nullable=True),
    sa.Column('total_pages', sa.Integer(), nullable=True),
    sa.Column('progress_percentage', sa.Float(), nullable=True),
    sa.Column('reading_time_minutes', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(), nullable=True),
    sa.Column('is_completed', sa.Boolean(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['book_id'], ['books.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_reading_progress_id'), 'reading_progress', ['id'], unique=False)
    
    # Create chapters table
    op.create_table('chapters',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('content', sa.Text(), nullable=True),
    sa.Column('chapter_number', sa.Integer(), nullable=False),
    sa.Column('image_url', sa.String(), nullable=True),
    sa.Column('is_published', sa.Boolean(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('book_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['book_id'], ['books.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('book_id', 'chapter_number', name='unique_chapter_number_per_book')
    )
    op.create_index(op.f('ix_chapters_book_id'), 'chapters', ['book_id'], unique=False)
    op.create_index(op.f('ix_chapters_chapter_number'), 'chapters', ['chapter_number'], unique=False)
    op.create_index(op.f('ix_chapters_id'), 'chapters', ['id'], unique=False)
    op.create_index(op.f('ix_chapters_title'), 'chapters', ['title'], unique=False)
    
    # Create reading_lists table
    op.create_table('reading_lists',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_reading_lists_id'), 'reading_lists', ['id'], unique=False)
    op.create_index(op.f('ix_reading_lists_name'), 'reading_lists', ['name'], unique=False)
    op.create_index(op.f('ix_reading_lists_user_id'), 'reading_lists', ['user_id'], unique=False)
    
    # Create favorites table
    op.create_table('favorites',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('book_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['book_id'], ['books.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'book_id', name='unique_user_book_favorite')
    )
    op.create_index(op.f('ix_favorites_book_id'), 'favorites', ['book_id'], unique=False)
    op.create_index(op.f('ix_favorites_id'), 'favorites', ['id'], unique=False)
    op.create_index(op.f('ix_favorites_user_id'), 'favorites', ['user_id'], unique=False)
    
    # Create reading_list_items table
    op.create_table('reading_list_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reading_list_id', sa.Integer(), nullable=False),
        sa.Column('book_id', sa.Integer(), nullable=False),
        sa.Column('order_index', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['book_id'], ['books.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reading_list_id'], ['reading_lists.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('reading_list_id', 'book_id', name='unique_book_per_reading_list')
    )
    op.create_index(op.f('ix_reading_list_items_book_id'), 'reading_list_items', ['book_id'], unique=False)
    op.create_index(op.f('ix_reading_list_items_id'), 'reading_list_items', ['id'], unique=False)
    op.create_index(op.f('ix_reading_list_items_reading_list_id'), 'reading_list_items', ['reading_list_id'], unique=False)
    
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### Drop all tables in reverse order ###
    
    # Drop reading_list_items table
    op.drop_index(op.f('ix_reading_list_items_reading_list_id'), table_name='reading_list_items')
    op.drop_index(op.f('ix_reading_list_items_id'), table_name='reading_list_items')
    op.drop_index(op.f('ix_reading_list_items_book_id'), table_name='reading_list_items')
    op.drop_table('reading_list_items')
    
    # Drop favorites table
    op.drop_index(op.f('ix_favorites_user_id'), table_name='favorites')
    op.drop_index(op.f('ix_favorites_id'), table_name='favorites')
    op.drop_index(op.f('ix_favorites_book_id'), table_name='favorites')
    op.drop_table('favorites')
    
    # Drop reading_lists table
    op.drop_index(op.f('ix_reading_lists_user_id'), table_name='reading_lists')
    op.drop_index(op.f('ix_reading_lists_name'), table_name='reading_lists')
    op.drop_index(op.f('ix_reading_lists_id'), table_name='reading_lists')
    op.drop_table('reading_lists')
    
    # Drop chapters table
    op.drop_index(op.f('ix_chapters_title'), table_name='chapters')
    op.drop_index(op.f('ix_chapters_id'), table_name='chapters')
    op.drop_index(op.f('ix_chapters_chapter_number'), table_name='chapters')
    op.drop_index(op.f('ix_chapters_book_id'), table_name='chapters')
    op.drop_table('chapters')
    
    # Drop reading_progress table
    op.drop_index(op.f('ix_reading_progress_id'), table_name='reading_progress')
    op.drop_table('reading_progress')
    
    # Drop books table
    op.drop_index(op.f('ix_books_title'), table_name='books')
    op.drop_index(op.f('ix_books_id'), table_name='books')
    op.drop_table('books')
    
    # Drop categories table
    op.drop_index(op.f('ix_categories_slug'), table_name='categories')
    op.drop_index(op.f('ix_categories_name'), table_name='categories')
    op.drop_index(op.f('ix_categories_id'), table_name='categories')
    op.drop_table('categories')
    
    # Drop authors table
    op.drop_index(op.f('ix_authors_name'), table_name='authors')
    op.drop_index(op.f('ix_authors_id'), table_name='authors')
    op.drop_table('authors')
    
    # Drop users table
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    # ### end Alembic commands ### 