"""Core authentication / authorization helpers.

This module defines reusable decorators and helpers for role-based
access control. We keep it in `core` so it can be imported from
copper, cassiterite, and any future modules.
"""

from functools import wraps

from flask import abort
from flask_login import current_user


def role_required(*roles):
    """Restrict a view to one or more roles.

    Usage examples (on Flask views or blueprints):

        @role_required("boss")
        def boss_dashboard():
            ...

        @role_required("accountant", "boss")
        def accountant_or_boss_view():
            ...

    How it works:
    - The outer function `role_required(*roles)` receives the allowed
      role names as strings.
    - It returns an inner `decorator`, which receives the actual view
      function.
    - That `decorator` wraps the view function inside `wrapper`, where
      we can run checks *before* calling the original view.

    In `wrapper` we:
    - Check that the user is authenticated.
    - Check that `current_user.role` is in the allowed roles.
    - If everything is okay, we call the original view function.
    - If not, we abort with 401/403.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            # 1) Ensure the user is logged in. If your app uses a
            # custom login redirect, you can swap abort(401) for a
            # redirect to your login page.
            if not getattr(current_user, "is_authenticated", False):
                abort(401)  # Unauthorized

            # 2) Ensure the user has one of the required roles.
            #    `current_user.role` comes from the `User` model in
            #    core.models.
            if current_user.role not in roles:
                abort(403)  # Forbidden

            # 3) All checks passed → call the original view function.
            return view_func(*args, **kwargs)

        return wrapper

    return decorator
