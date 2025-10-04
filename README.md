# Book Reading Platform - Backend API

A comprehensive FastAPI backend for the Book Reading Platform with user management, book catalog, reading progress tracking, and admin dashboard.

## Features

- **FastAPI Framework**: Modern Python web framework with automatic API documentation
- **PostgreSQL Database**: Robust relational database with SQLAlchemy ORM
- **JWT Authentication**: Secure user authentication with role-based access
- **File Upload**: Supabase integration for book covers and documents
- **Email Service**: SMTP integration for notifications and password reset
- **API Documentation**: Auto-generated interactive documentation
- **Admin Dashboard**: Complete admin interface for content management
- **Reading Progress**: Track user reading habits and analytics
- **Search & Filtering**: Advanced book search and filtering capabilities

## Tech Stack

- **FastAPI** - Modern web framework for building APIs
- **Python 3.11+** - Programming language
- **PostgreSQL 15** - Primary database
- **SQLAlchemy 2.0** - ORM and database toolkit
- **Alembic** - Database migration tool
- **Pydantic** - Data validation and settings management
- **JWT** - Authentication tokens
- **Supabase** - File storage and additional services
- **Redis** - Caching (optional)
- **uv** - Fast Python package manager

## ✅ Simplified Docker Setup

### Universal Dockerfile & Compose
- ✅ **Single Dockerfile**: Universal build supporting both development and production
- ✅ **Single docker-compose.yml**: Unified configuration with dynamic mode switching
- ✅ **Single env.template**: Simplified environment configuration
- ✅ **Cross-platform scripts**: Helper scripts for Linux and Windows
- ✅ **Integrated database**: PostgreSQL and Redis included in development

### Quick Start

**Option 1: Using Helper Scripts**

```bash
# Linux/Mac Development
./scripts/dev.sh

# Linux/Mac Production  
./scripts/prod.sh

# Windows Development
.\scripts\dev.bat

# Windows Production
.\scripts\prod.bat
```

**Option 2: Manual Docker Commands**

```bash
# Development Mode (includes database + redis + backend)
MODE=development docker-compose up --build

# Production Mode (backend only, expects external database)
MODE=production docker-compose up --build -d
```

## Environment Setup

### 1. Create Environment File
```bash
cp env.template .env
```

### 2. Configure Environment
Edit `.env` file with your settings:

```bash
# ==============================================
# DOCKER CONFIGURATION
# ==============================================
MODE=development                    # or 'production'
CONTAINER_NAME=backend_api_dev      # or 'backend_api_prod'

# ==============================================
# APPLICATION SETTINGS  
# ==============================================
ENVIRONMENT=development             # or 'production'
DEBUG=true                          # false for production
DATABASE_URL=postgresql://postgres:1234aa@database:5432/bookstore_db

# ==============================================
# SECURITY SETTINGS
# ==============================================
SECRET_KEY=development-secret-key-please-change-in-production-32-chars
ACCESS_TOKEN_EXPIRE_MINUTES=60
BACKEND_CORS_ORIGINS=["http://localhost:3000","http://localhost:3001"]
```

### 3. Production Configuration
For production, uncomment and configure the production overrides in `.env`:

```bash
MODE=production
ENVIRONMENT=production
DEBUG=false
DATABASE_URL=postgresql://username:password@your-db-host:5432/bookstore_prod
SECRET_KEY=your-super-secure-secret-key-minimum-32-characters
BACKEND_CORS_ORIGINS=["https://user.yourdomain.com","https://admin.yourdomain.com"]
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_service_role_key_here
```

## Docker Deployment Commands

### Development Deployment
```bash
# Quick development start (includes database)
./scripts/dev.sh

# Or manual
MODE=development \
ENVIRONMENT=development \
DEBUG=true \
docker-compose up --build

# Access:
# - API: http://localhost:8000
# - API Docs: http://localhost:8000/docs
# - Database: localhost:5432
# - Redis: localhost:6379
```

### Production Deployment
```bash
# Quick production start  
./scripts/prod.sh

# Or manual
MODE=production \
ENVIRONMENT=production \
DEBUG=false \
DATABASE_URL=postgresql://user:pass@your-db:5432/bookstore_prod \
docker-compose up --build -d

# View logs
docker-compose logs -f backend

# Stop
docker-compose down
```

## Environment-Based Settings System

The backend uses an intelligent settings system that automatically loads configuration based on the `ENVIRONMENT` variable:

### Settings Classes

1. **DevelopmentSettings** - Loaded when `ENVIRONMENT=development`
   - Database URL defaults to local PostgreSQL
   - Debug mode enabled
   - CORS allows all origins
   - Verbose logging and error details
   - Auto-reload enabled

2. **ProductionSettings** - Loaded when `ENVIRONMENT=production`
   - Database URL must be set via `DATABASE_URL`
   - Debug mode disabled
   - Restricted CORS origins
   - Error logging with minimal details
   - Optimized for performance

### Environment Variables

All environment variables are clearly documented in `env.template`:

#### Core Configuration
```bash
ENVIRONMENT=development|production  # Determines which settings class to load
DEBUG=true|false                   # Enable debug mode
PROJECT_NAME="Book Reading API"    # Application name
DATABASE_URL=postgresql://...      # Database connection string
```

#### Security Settings
```bash
SECRET_KEY=your-secret-key         # JWT signing key (32+ chars)
ALGORITHM=HS256                    # JWT algorithm
ACCESS_TOKEN_EXPIRE_MINUTES=60     # Token expiration
BACKEND_CORS_ORIGINS=["http://..."] # Allowed frontend origins
```

#### External Services
```bash
SUPABASE_URL=https://your-project.supabase.co    # File storage
SUPABASE_KEY=your_service_role_key               # Supabase key
BUCKET_NAME=book-file                            # Storage bucket
SMTP_HOST=smtp.gmail.com                         # Email service
```

## API Documentation

### Automatic Documentation
- **Interactive Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI Schema**: http://localhost:8000/openapi.json

### Main API Endpoints

#### Authentication
```
POST   /api/v1/auth/register          # User registration
POST   /api/v1/auth/login-json        # User login
GET    /api/v1/auth/me                # Current user info
POST   /api/v1/auth/forgot-password   # Password reset request
POST   /api/v1/auth/reset-password    # Password reset
POST   /api/v1/auth/change-password   # Change password
```

#### Books & Content
```
GET    /api/v1/books/public/          # Public book list
GET    /api/v1/books/public/{id}      # Public book details
GET    /api/v1/authors/public/        # Public authors list
GET    /api/v1/categories/public/     # Public categories list
GET    /api/v1/chapters/public/book/{id} # Book chapters
GET    /api/v1/search/                # Search books
```

#### User Features (Authenticated)
```
GET    /api/v1/favorites/             # User favorites
POST   /api/v1/favorites/toggle       # Toggle favorite
GET    /api/v1/reading-lists/         # User reading lists
GET    /api/v1/reading-progress/      # Reading progress
```

#### Admin Endpoints (Admin only)
```
POST   /api/v1/books/                 # Create book
PUT    /api/v1/books/{id}             # Update book
DELETE /api/v1/books/{id}             # Delete book
GET    /api/v1/users/                 # Manage users
```

### Default Credentials (Development)
After running the development setup:
- **Admin User**: 
  - Email: `admin@example.com`
  - Password: `admin123`
- **Regular Users**: 
  - Any seeded user email
  - Password: `password123`

## Database Management

### Automatic Migrations
Development mode automatically runs:
1. Database migrations (`alembic upgrade head`)
2. Sample data seeding (200 records per table)

### Manual Database Operations
```bash
# Run migrations only
docker-compose exec backend uv run alembic upgrade head

# Seed sample data
docker-compose exec backend uv run python scripts/seed_database.py

# Check database status
docker-compose exec backend uv run python scripts/check_database.py

# Reset and recreate database
docker-compose exec backend uv run python scripts/setup_complete.py
```

### Available Scripts
- `seed_database.py` - Create realistic sample data
- `check_database.py` - Verify database connection and integrity
- `setup_complete.py` - Complete database reset and setup
- `reset_database.py` - Clean database reset

## File Structure

```
backend/
├── Dockerfile              # Universal Dockerfile (dev & prod)
├── docker-compose.yml      # Universal compose file
├── env.template            # Environment template
├── scripts/
│   ├── dev.sh             # Linux development script
│   ├── prod.sh            # Linux production script
│   ├── dev.bat            # Windows development script
│   ├── prod.bat           # Windows production script
│   ├── seed_database.py   # Database seeding
│   └── check_database.py  # Database verification
├── app/
│   ├── api/v1/endpoints/  # API route handlers
│   ├── core/              # Core configurations
│   │   ├── settings/      # Environment settings
│   │   ├── auth.py        # Authentication logic
│   │   └── database.py    # Database connection
│   ├── models/            # SQLAlchemy models
│   ├── schemas/           # Pydantic schemas
│   ├── crud/              # Database operations
│   ├── services/          # Business logic
│   └── main.py            # FastAPI application
├── alembic/               # Database migrations
├── tests/                 # Test suite
└── logs/                  # Application logs
```

## Testing

### Run Tests
```bash
# Run all tests
docker-compose exec backend uv run pytest

# Run with coverage
docker-compose exec backend uv run pytest --cov=app

# Run specific test file
docker-compose exec backend uv run pytest tests/test_auth.py
```

### Test Coverage
- Authentication and authorization
- CRUD operations for all entities
- API endpoint testing
- Database integration tests
- File upload functionality

## Troubleshooting

### Common Issues

1. **"Settings validation failed: DATABASE_URL must be set"**
   - Set `DATABASE_URL` to your actual database URL in production
   - Ensure database is accessible from the container

2. **"Database connection failed"**
   - Check if PostgreSQL container is running: `docker-compose ps`
   - Verify database credentials in environment variables
   - Check network connectivity between containers

3. **"Permission denied for migrations"**
   - Ensure database user has sufficient privileges
   - Check if database exists and is accessible
   - Verify connection string format

4. **Docker Build Failures**
   - Ensure Docker and Docker Compose are installed
   - Clear Docker cache: `docker system prune -f`
   - Check network connectivity for Python packages

5. **CORS Issues**
   - Update `BACKEND_CORS_ORIGINS` in environment variables
   - Ensure frontend URL matches CORS configuration
   - Check if requests include credentials properly

6. **File Upload Issues**
   - Verify Supabase configuration (URL, key, bucket)
   - Check file size limits and allowed extensions
   - Ensure proper permissions on upload directory

### Debug Mode

Enable debug mode to see detailed information:

```bash
DEBUG=true
LOG_LEVEL=DEBUG
```

This will log:
- SQL queries executed
- Detailed error tracebacks
- Request/response information
- Settings loaded
- Authentication flows

### Health Checks

- **Health Endpoint**: `GET /health`
- **Database Check**: Included in health endpoint
- **Docker Health**: Configured in Dockerfile
- **Service Status**: `docker-compose ps`

## Security Features

### Authentication & Authorization
- JWT-based authentication
- Role-based access control (User/Admin)
- Password hashing with bcrypt
- Secure session management

### Security Headers
- CORS protection
- Input validation with Pydantic
- SQL injection prevention via SQLAlchemy
- XSS protection in API responses

### Production Security
- Non-root user execution
- Environment variable validation
- Secure defaults for production
- Error message sanitization

## Performance Features

### Database Optimization
- Connection pooling
- Query optimization
- Database indexing
- Pagination for large datasets

### Caching
- Redis integration (optional)
- Response caching
- Static file caching

### Monitoring
- Health check endpoints
- Request logging
- Error tracking ready
- Performance metrics

## Deployment Examples

### Development (.env)
```bash
MODE=development
ENVIRONMENT=development
DEBUG=true
DATABASE_URL=postgresql://postgres:1234aa@database:5432/bookstore_db
SECRET_KEY=development-secret-key-please-change-in-production-32-chars
```

### Production (.env)
```bash
MODE=production
ENVIRONMENT=production
DEBUG=false
DATABASE_URL=postgresql://username:password@your-db-host:5432/bookstore_prod
SECRET_KEY=your-super-secure-secret-key-minimum-32-characters
BACKEND_CORS_ORIGINS=["https://user.yourdomain.com","https://admin.yourdomain.com"]
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_service_role_key_here
```

## ✅ Final Verification

### ✅ Simplified Setup Complete

**Docker Configuration:**
- ✅ Universal Dockerfile supporting both dev and prod modes
- ✅ Single docker-compose.yml with dynamic configuration  
- ✅ Simplified env.template replacing multiple env files
- ✅ Cross-platform scripts for easy deployment

**Build & Runtime:**
- ✅ Python dependencies: Clean installation with uv
- ✅ Database integration: PostgreSQL with automatic migrations
- ✅ Redis caching: Optional service for development
- ✅ Health checks: Comprehensive service monitoring

**Environment Management:**
- ✅ Dynamic mode switching (dev/prod)
- ✅ Automatic .env file creation
- ✅ Environment validation for production
- ✅ Clear documentation and examples

**Cross-Platform Support:**
- ✅ Linux/Mac shell scripts
- ✅ Windows batch scripts
- ✅ Docker volume handling for Windows
- ✅ Consistent behavior across platforms

**Next Steps:**
1. Copy `env.template` to `.env` 
2. Configure `DATABASE_URL` and `SECRET_KEY` for production
3. Run `./scripts/dev.sh` (Linux) or `.\scripts\dev.bat` (Windows)
4. For production: Update environment settings and run prod scripts

The backend is now **100% ready** with simplified Docker setup! 🚀

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly with both development and production settings
5. Submit a pull request

## License

This project is part of the Book Reading Platform and follows the same license terms. 