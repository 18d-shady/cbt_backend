from django.urls import path
from .views import *
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    path("api/login/", StudentLoginView.as_view(), name="student-login"),
    path("api/subjects/", SubjectRegisteredView.as_view(), name="subjects-registered"),
    path("api/exam/<int:exam_id>/", ExamDetailView.as_view(), name="exam-detail"),
    path("api/exam/<int:exam_id>/question/<int:index>/", QuestionByIndexView.as_view(), name="question-by-index"),
    path("api/answer/", SaveAnswerView.as_view(), name="save-answer"),
    path("api/exam/<int:exam_id>/start/", StartExamSessionView.as_view(), name="start-session"),
    path("api/exam/<int:exam_id>/time/", RemainingTimeView.as_view(), name="remaining-time"),
    path("api/exam/<int:exam_id>/end/", EndExamSessionView.as_view(), name="end-session"),


    # Subscription and Payment URLs
    path("api/demo/", DemoRequestView.as_view(), name="demo-request"),
    path("api/subscribe/", StartSubscriptionView.as_view(), name="start-subscription"),
    path("api/paystack-webhook/", paystack_webhook, name="paystack-webhook"),
    path("api/request-school/", RequestSchoolView.as_view(), name="school-request"),
    path("api/check-school/", CheckSchoolView.as_view(), name="check-school"),
]