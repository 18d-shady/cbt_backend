from django.conf import settings # Add this import
from django.shortcuts import redirect
from django.http import JsonResponse

class SubscriptionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user

        # 1️⃣ Allow unauthenticated users
        if not user.is_authenticated:
            return self.get_response(request)

        # 2️⃣ Superadmins bypass
        if user.is_superuser:
            return self.get_response(request)

        # 3️⃣ Exempt paths
        exempt_paths = (
            "/admin/login/",
            "/admin/logout/",
            "/api/login/",
            "/api/subscribe/",
            "/api/paystack-webhook/",
        )
        if request.path.startswith(exempt_paths):
            return self.get_response(request)

        # 4️⃣ Subscription Check for Admin and APIs
        profile = getattr(user, "userprofile", None)
        school = profile.school if profile else None

        if school and not school.is_subscription_active():
            # If it's an API call, return JSON so the frontend can handle the popup/redirect
            if request.path.startswith("/api/"):
                return JsonResponse({
                    "detail": "Subscription expired",
                    "status": "expired",
                    "payment_url": f"{settings.FRONTEND_URL}/payment?email={user.email}"
                }, status=403)

            # If they are trying to access the Django Admin directly
            if request.path.startswith("/admin/"):
                if "/logout/" not in request.path:
                    # Redirect to absolute Next.js URL
                    return redirect(f"{settings.FRONTEND_URL}/payment?email={user.email}&plan=monthly")

        return self.get_response(request)