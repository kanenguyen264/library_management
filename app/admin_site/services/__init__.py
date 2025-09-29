from app.admin_site.services.achievement_service import (
    get_all_achievements,
    get_achievement_by_id,
    create_achievement,
    update_achievement,
    delete_achievement,
)

from app.admin_site.services.admin_service import (
    get_all_admins,
    get_admin_by_id,
    create_new_admin,
    update_admin,
    delete_admin,
    set_admin_roles,
)

from app.admin_site.services.admin_session_service import (
    create_admin_session,
    get_admin_sessions,
    invalidate_session,
    invalidate_all_admin_sessions,
)

from app.admin_site.services.analytics_service import (
    get_user_analytics,
    get_content_analytics,
    get_revenue_analytics,
    get_engagement_analytics,
)

from app.admin_site.services.annotation_service import (
    get_all_annotations,
    count_annotations,
    get_annotation_by_id,
    create_annotation,
    update_annotation,
    delete_annotation,
    get_user_annotations,
    get_book_public_annotations,
    toggle_annotation_visibility,
    get_annotation_statistics,
)

from app.admin_site.services.auth_service import (
    authenticate_admin,
    create_admin_token,
    refresh_admin_token,
    verify_password,
    get_password_hash,
    change_admin_password,
)

from app.admin_site.services.author_service import (
    get_all_authors,
    count_authors,
    get_author_by_id,
    get_author_by_slug,
    create_author,
    update_author,
    delete_author,
    get_author_books,
    update_book_count,
)

from app.admin_site.services.badge_service import (
    get_all_badges,
    get_badge_by_id,
    create_badge,
    update_badge,
    delete_badge,
)

from app.admin_site.services.book_service import (
    get_all_books,
    get_book_by_id,
    get_book_by_isbn,
    create_book,
    publish_book,
)

from app.admin_site.services.book_list_service import (
    get_all_book_lists,
    get_book_list_by_id,
    create_book_list,
    update_book_list,
    delete_book_list,
)

from app.admin_site.services.book_series_service import (
    get_all_series,
    get_series_by_id,
    create_series,
    update_series,
    delete_series,
)

from app.admin_site.services.bookmark_service import (
    get_all_bookmarks,
    get_bookmark_by_id,
    create_bookmark,
    update_bookmark,
    delete_bookmark,
)

from app.admin_site.services.bookshelf_service import (
    get_all_bookshelves,
    get_bookshelf_by_id,
    create_bookshelf,
    update_bookshelf,
    delete_bookshelf,
)

from app.admin_site.services.category_service import (
    get_all_categories,
    get_category_by_id,
    create_category,
    update_category,
    delete_category,
)

from app.admin_site.services.chapter_service import (
    get_all_chapters,
    get_chapter_by_id,
    create_chapter,
    update_chapter,
    delete_chapter,
)

from app.admin_site.services.content_approval_service import (
    get_all_content_approvals,
    get_content_approval_by_id,
    create_content_approval,
    update_content_approval,
    approve_content,
    reject_content,
)

from app.admin_site.services.dashboard_service import (
    get_dashboard_summary,
    get_dashboard_stats,
    get_recent_activities,
    get_alerts_and_notifications,
)

from app.admin_site.services.discussion_service import (
    get_all_discussions,
    get_discussion_by_id,
    create_discussion,
    update_discussion,
    delete_discussion,
)

from app.admin_site.services.featured_content_service import (
    get_all_featured_contents,
    get_featured_content_by_id,
    create_featured_content,
    update_featured_content,
    delete_featured_content,
)

from app.admin_site.services.following_service import (
    get_all_followings,
    get_following_by_id,
    create_following,
    delete_following,
)

from app.admin_site.services.notification_service import (
    get_all_notifications,
    get_notification_by_id,
    create_notification,
    update_notification,
    delete_notification,
)

from app.admin_site.services.payment_method_service import (
    get_all_payment_methods,
    get_payment_method_by_id,
    create_payment_method,
    update_payment_method,
    delete_payment_method,
)

from app.admin_site.services.payment_service import (
    get_all_payments,
    get_payment_by_id,
    create_payment,
    update_payment,
    delete_payment,
)

from app.admin_site.services.permission_service import (
    get_all_permissions,
    get_permission_by_id,
    create_permission,
    update_permission,
    delete_permission,
)

from app.admin_site.services.preference_service import (
    get_all_preferences,
    get_preference_by_id,
    create_preference,
    update_preference,
    delete_preference,
)

from app.admin_site.services.promotion_service import (
    get_all_promotions,
    get_promotion_by_id,
    create_promotion,
    update_promotion,
    delete_promotion,
)

from app.admin_site.services.publisher_service import (
    get_all_publishers,
    get_publisher_by_id,
    get_publisher_books,
    count_publisher_books,
)

from app.admin_site.services.quote_service import (
    get_all_quotes,
    get_quote_by_id,
    create_quote,
    update_quote,
    delete_quote,
)

from app.admin_site.services.quote_like_service import (
    get_all_quote_likes,
    get_quote_like_by_id,
    create_quote_like,
    delete_quote_like,
)

from app.admin_site.services.reading_goal_service import (
    get_all_reading_goals,
    get_reading_goal_by_id,
    create_reading_goal,
    update_reading_goal,
    delete_reading_goal,
)

from app.admin_site.services.reading_history_service import (
    get_all_reading_histories,
    get_reading_history_by_id,
    create_reading_history,
    update_reading_history,
    delete_reading_history,
)

from app.admin_site.services.reading_session_service import (
    get_all_reading_sessions,
    get_reading_session_by_id,
    create_reading_session,
    update_reading_session,
    delete_reading_session,
)

from app.admin_site.services.recommendation_service import (
    get_all_recommendations,
    get_recommendation_by_id,
    create_recommendation,
    update_recommendation,
    delete_recommendation,
)

from app.admin_site.services.report_service import (
    get_user_report,
    get_content_report,
    get_financial_report,
    get_system_report,
    get_activity_report,
)

from app.admin_site.services.review_service import (
    get_all_reviews,
    get_review_by_id,
    create_review,
    update_review,
    delete_review,
    get_book_reviews,
)

from app.admin_site.services.role_service import (
    get_all_roles,
    get_role_by_id,
    create_role,
    update_role,
    delete_role,
    set_role_permissions,
)

from app.admin_site.services.social_profile_service import (
    get_all_social_profiles,
    get_social_profile_by_id,
    create_social_profile,
    update_social_profile,
    delete_social_profile,
)

from app.admin_site.services.subscription_service import (
    get_all_subscriptions,
    get_subscription_by_id,
    create_subscription,
    update_subscription,
    delete_subscription,
)

from app.admin_site.services.system_health_service import (
    get_all_system_health,
    get_system_health_by_id,
    create_system_health,
    update_system_health,
    delete_system_health,
)

from app.admin_site.services.system_metric_service import (
    get_all_system_metrics,
    get_system_metric_by_id,
    create_system_metric,
    update_system_metric,
    delete_system_metric,
)

from app.admin_site.services.system_setting_service import (
    get_all_system_settings,
    get_system_setting_by_id,
    get_system_setting_by_key,
    create_system_setting,
    update_system_setting,
    delete_system_setting,
)

from app.admin_site.services.tag_service import (
    get_all_tags,
    get_tag_by_id,
    create_tag,
    update_tag,
    delete_tag,
)

from app.admin_site.services.user_service import (
    get_all_users,
    get_user_by_id,
    create_user,
    update_user,
    delete_user,
)
