from django.urls import path
from .views import *
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    path("api/login/", StudentLoginView.as_view(), name="student-login"),
    path("api/subjects/", SubjectRegisteredView.as_view(), name="subjects-registered"),
    path("api/exam/<str:course_code>/", ExamDetailView.as_view(), name="exam-detail"),
    path("api/exam/<str:course_code>/question/<int:index>/", QuestionByIndexView.as_view(), name="question-by-index"),
    path("api/answer/", SaveAnswerView.as_view(), name="save-answer"),
    path("api/exam/<str:course_code>/start/", StartExamSessionView.as_view(), name="start-session"),
    path("api/exam/<str:course_code>/time/", RemainingTimeView.as_view(), name="remaining-time"),
    path("api/exam/<str:course_code>/end/", EndExamSessionView.as_view(), name="end-session"),
]