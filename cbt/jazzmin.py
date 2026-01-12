JAZZMIN_SETTINGS = {
    "site_title": "JustCBT Admin",
    "site_header": "JustCBT",
    "site_brand": "JustCBT Management",
    "welcome_sign": "Welcome to the JustCBT Admin Portal",
    "copyright": "JustCBT Ltd",
    "search_model": ["auth.User", "api.Exam"],
    
    # User Menu
    "user_menu_links": [
        {"name": "Support", "url": "https://support.justcbt.com", "new_window": True},
        {"model": "auth.user"},
    ],

    # Sidebar Navigation Grouping
    "navigation_expanded": True,
    "topmenu_links": [
        {"name": "Home",  "url": "admin:index", "permissions": ["auth.view_user"]},
        {"model": "auth.User"},
    ],

    "icons": {
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "api.School": "fas fa-university",
        "api.Exam": "fas fa-file-signature",
        "api.Question": "fas fa-question-circle",
        "api.StudentClass": "fas fa-chalkboard",
        "api.Course": "fas fa-book",
        "api.StudentScore": "fas fa-poll",
    },
    
    # Order of menu groups
    "order_with_respect_to": ["api.School", "api.Exam", "api.Course", "auth"],
    
    "show_ui_builder": True, # This allows you to live-edit the theme in the browser
}

JAZZMIN_UI_TWEAKS = {
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": False,
    "brand_small_text": False,
    "brand_colour": "navbar-primary",
    "accent": "accent-primary",
    "navbar": "navbar-white navbar-light",
    "no_navbar_border": False,
    "navbar_fixed": True,
    "layout_boxed": False,
    "footer_fixed": False,
    "sidebar_fixed": True,
    "sidebar": "sidebar-dark-primary",
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": False,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,
    "theme": "default",
    "dark_mode_theme": None,
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success"
    }
}
