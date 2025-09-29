# Logs Manager Integration

This document describes how the logging system is integrated throughout the application.

## Overview

The logs manager provides comprehensive logging services for various aspects of the application:

- Authentication logs
- API request logs
- Performance logs
- Error logs
- User activity logs
- Admin activity logs
- Search logs

## Middleware Integration

### Authentication Middleware (`app/middlewares/auth_middleware.py`)

- Uses `authentication_log_service` to log:
  - Successful authentication attempts
  - Failed authentication attempts with reason (missing token, expired token, invalid token, etc.)
  - Authorization failures

### Logging Middleware (`app/middlewares/logging_middleware.py`)

- Uses `api_request_log_service` to log:
  - All API requests
  - Request path, method, status code
  - Client information (IP, user agent)
  - Performance metrics (duration)
  - Associated user/admin ID

### Tracing Middleware (`app/middlewares/tracing_middleware.py`)

- Uses `performance_log_service` to log:
  - Slow API requests (exceeding configured threshold)
  - Path, method, duration
  - User/admin ID 
  - Request context

## Service Integration

### Auth Service (`app/user_site/services/auth_service.py`)

- Uses `authentication_log_service` to log:
  - Login attempts (success/failure)
  - Token validation
  - Authentication errors

### User Service (`app/user_site/services/user_service.py`)

- Uses `user_activity_log_service` to log:
  - User registration
  - Profile updates
  - Account deletion
  - Email verification
  - Password changes

### Search Service (`app/user_site/services/search_service.py`)

- Uses `search_log_service` to log:
  - Search queries
  - Search filters
  - Result counts
  - Source of search (books, authors, all)

### Review Service (`app/user_site/services/review_service.py`)

- Uses `user_activity_log_service` to log:
  - Review creation
  - Review updates
  - Review deletion

### Reading Session Service (`app/user_site/services/reading_session_service.py`)

- Uses `performance_log_service` to log:
  - Session start operations
  - Performance metrics

## How to Use Logs in Services

When implementing new functionality, consider adding appropriate logging:

1. For user actions, use `create_user_activity_log`:

```python
await create_user_activity_log(
    db,
    UserActivityLogCreate(
        user_id=user_id,
        activity_type="ACTION_TYPE",
        entity_type="ENTITY_TYPE",
        entity_id=entity_id,
        description="Description of action",
        metadata={...} # Additional context
    )
)
```

2. For authentication, use `create_authentication_log`:

```python
await create_authentication_log(
    db,
    AuthenticationLogCreate(
        user_id=user_id,
        action="action_name",
        status="success|failed",
        ip_address=client_ip,
        user_agent=user_agent,
        details={...} # Additional context
    )
)
```

3. For performance tracking, use `create_performance_log`:

```python
await create_performance_log(
    db,
    PerformanceLogCreate(
        component="component_name",
        operation="operation_name",
        duration_ms=duration_ms,
        endpoint=endpoint,
        user_id=user_id,
        details={...} # Additional context
    )
)
```

4. For search logging, use `create_search_log`:

```python
await create_search_log(
    db,
    SearchLogCreate(
        user_id=user_id,
        query_term=query,
        session_id=session_id,
        results_count=total,
        filters_json=filters,
        source="source_name"
    )
)
``` 