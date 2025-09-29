from fastapi import APIRouter

# Tạo router cho admin
admin_router = APIRouter(prefix="/api/v1/admin")

# Import các router một lần vào cuối file để tránh circular import


def register_all_routers():
    """Register all routers to avoid circular imports"""
    # Import và đăng ký router cơ bản đầu tiên
    from app.admin_site.api.v1 import auth

    admin_router.include_router(auth.router, tags=["Admin Auth"])

    # Import và đăng ký các router còn lại
    from app.admin_site.api.v1 import admins

    admin_router.include_router(admins.router, prefix="/admins", tags=["Admins"])

    from app.admin_site.api.v1 import admin_sessions

    admin_router.include_router(
        admin_sessions.router, prefix="/admin-sessions", tags=["Admin Sessions"]
    )

    from app.admin_site.api.v1 import roles

    admin_router.include_router(roles.router, prefix="/roles", tags=["Roles"])

    from app.admin_site.api.v1 import permissions

    admin_router.include_router(
        permissions.router, prefix="/permissions", tags=["Permissions"]
    )

    from app.admin_site.api.v1 import system_settings

    admin_router.include_router(
        system_settings.router, prefix="/system-settings", tags=["System Settings"]
    )

    from app.admin_site.api.v1 import system_metrics

    admin_router.include_router(
        system_metrics.router, prefix="/system-metrics", tags=["System Metrics"]
    )

    from app.admin_site.api.v1 import system_health

    admin_router.include_router(
        system_health.router, prefix="/system-health", tags=["System Health"]
    )

    from app.admin_site.api.v1 import content_approval

    admin_router.include_router(
        content_approval.router, prefix="/content-approval", tags=["Content Approval"]
    )

    from app.admin_site.api.v1 import featured_content

    admin_router.include_router(
        featured_content.router, prefix="/featured-content", tags=["Featured Content"]
    )

    from app.admin_site.api.v1 import promotions

    admin_router.include_router(
        promotions.router, prefix="/promotions", tags=["Promotions"]
    )

    from app.admin_site.api.v1 import achievements

    admin_router.include_router(
        achievements.router, prefix="/achievements", tags=["Achievements"]
    )

    from app.admin_site.api.v1 import badges

    admin_router.include_router(badges.router, prefix="/badges", tags=["Badges"])

    from app.admin_site.api.v1 import books

    admin_router.include_router(
        books.router, prefix="/books", tags=["Books Management"]
    )

    from app.admin_site.api.v1 import users

    admin_router.include_router(
        users.router, prefix="/users", tags=["Users Management"]
    )

    from app.admin_site.api.v1 import authors

    admin_router.include_router(
        authors.router, prefix="/authors", tags=["Authors Management"]
    )

    from app.admin_site.api.v1 import categories

    admin_router.include_router(
        categories.router, prefix="/categories", tags=["Categories Management"]
    )

    from app.admin_site.api.v1 import chapters

    admin_router.include_router(
        chapters.router, prefix="/chapters", tags=["Chapters Management"]
    )

    from app.admin_site.api.v1 import tags

    admin_router.include_router(tags.router, prefix="/tags", tags=["Tags Management"])

    from app.admin_site.api.v1 import analytics

    admin_router.include_router(
        analytics.router, prefix="/analytics", tags=["Analytics"]
    )

    from app.admin_site.api.v1 import reports

    admin_router.include_router(reports.router, prefix="/reports", tags=["Reports"])

    from app.admin_site.api.v1 import logs

    admin_router.include_router(logs.router, prefix="/logs", tags=["Logs Management"])

    from app.admin_site.api.v1 import dashboard

    admin_router.include_router(
        dashboard.router, prefix="/dashboard", tags=["Dashboard"]
    )

    from app.admin_site.api.v1 import discussions

    admin_router.include_router(
        discussions.router, prefix="/discussions", tags=["Discussions Management"]
    )

    from app.admin_site.api.v1 import publishers

    admin_router.include_router(
        publishers.router, prefix="/publishers", tags=["Publishers Management"]
    )

    from app.admin_site.api.v1 import reviews

    admin_router.include_router(
        reviews.router, prefix="/reviews", tags=["Reviews Management"]
    )

    from app.admin_site.api.v1 import subscriptions

    admin_router.include_router(
        subscriptions.router, prefix="/subscriptions", tags=["Subscriptions Management"]
    )

    from app.admin_site.api.v1 import book_series

    admin_router.include_router(
        book_series.router, prefix="/book-series", tags=["Book Series Management"]
    )


# Register all routers
register_all_routers()
