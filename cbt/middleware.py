from django.shortcuts import redirect
from django.urls import reverse

class SubscriptionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and hasattr(request.user, 'school'):
            # Allow them to see only the 'Billing' or 'Logout' pages if inactive
            if not request.user.school.is_active and "/admin/" in request.path:
                return redirect('subscription_expired_page')
        return self.get_response(request)