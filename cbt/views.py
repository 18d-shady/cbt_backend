from django.shortcuts import render
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Exam, Question, StudentAnswer, ExamSession, StudentScore, CourseRegistration
from .serializers import (
    ExamSerializer,
    QuestionSerializer,
    QuestionWithAnswerSerializer,
    StudentAnswerSerializer,
    ExamSessionSerializer,
    StudentScoreSerializer,
    UserSerializer,
    CourseRegistrationSerializer
)


# -------------------
# Student Login (validate student exam number + course)
# -------------------

class StudentLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        exam_no = request.data.get("examNo")
        course_code = request.data.get("courseCode")
        password = request.data.get("password")

        if not exam_no or not course_code or not password:
            return Response(
                {"error": "Exam number, course code, and password required"},
                status=400
            )

        # Authenticate student by exam_no + password
        user = authenticate(username=exam_no, password=password)
        if not user:
            return Response(
                {"valid": False, "error": "Invalid exam number or password"},
                status=400
            )

        # Validate exam
        try:
            exam = Exam.objects.get(course_code=course_code)
        except Exam.DoesNotExist:
            return Response(
                {"valid": False, "error": "Invalid course code"},
                status=400
            )

        # Check if student is registered for this exam
        if not CourseRegistration.objects.filter(user=user, exam=exam).exists():
            return Response(
                {"valid": False, "error": "You are not registered for this exam"},
                status=403
            )

        # ✅ Generate JWT tokens
        refresh = RefreshToken.for_user(user)

        # If all good → return success with tokens
        return Response({
            "valid": True,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "student": UserSerializer(user).data,
            "exam": ExamSerializer(exam).data
        })

# -------------------
# Get Subjects Registered (all courses this student registered for)
# -------------------
class SubjectRegisteredView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        registrations = CourseRegistration.objects.filter(user=request.user).select_related("exam")
        subjects = [reg.exam.course_code for reg in registrations]
        return Response({"subjects": subjects})


# -------------------
# Exam Details
# -------------------
class ExamDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, course_code):
        try:
            exam = Exam.objects.get(course_code=course_code)
        except Exam.DoesNotExist:
            return Response({"error": "Exam not found"}, status=404)

        return Response({
            "exam": ExamSerializer(exam).data,
            "student": UserSerializer(request.user).data
        })



# -------------------
# Get Question by Index
# -------------------
class QuestionByIndexView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, course_code, index):
        try:
            exam = Exam.objects.get(course_code=course_code)
            question = Question.objects.filter(exam=exam).order_by("question_number")[index]
        except (Exam.DoesNotExist, IndexError):
            return Response({"error": "Question not found"}, status=404)

        #return Response(QuestionSerializer(question).data)
        serializer = QuestionWithAnswerSerializer(question, context={"request": request})
        return Response(serializer.data)


# -------------------
# Save Student Answer
# -------------------
class SaveAnswerView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        question_id = request.data.get("questionId")
        selected_option = request.data.get("selectedOption")
        print("hiiii")

        try:
            question = Question.objects.get(id=question_id)
        except Question.DoesNotExist:
            return Response({"error": "Question not found"}, status=404)

        is_correct = (
            str(selected_option).strip().lower()
            == str(question.correct_option).strip().lower()
        )

        answer, created = StudentAnswer.objects.update_or_create(
            user=request.user,
            question=question,
            defaults={
                "selected_option": selected_option,
                "is_correct": is_correct,
            },
        )

        return Response(StudentAnswerSerializer(answer).data)


# -------------------
# Start Exam Session
# -------------------
class StartExamSessionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, course_code):
        try:
            exam = Exam.objects.get(course_code=course_code)
        except Exam.DoesNotExist:
            return Response({"error": "Exam not found"}, status=404)

        # ✅ Check if student is registered for this exam
        if not CourseRegistration.objects.filter(user=request.user, exam=exam).exists():
            return Response(
                {"error": "You are not registered for this exam"},
                status=403
            )

        now = timezone.now()
        end_time = now + timezone.timedelta(minutes=exam.duration_minutes)

        # If session exists and active
        existing = ExamSession.objects.filter(user=request.user, exam=exam).first()
        if existing and existing.end_time > now:
            return Response(ExamSessionSerializer(existing).data)

        # Remove expired session
        ExamSession.objects.filter(user=request.user, exam=exam).delete()

        session = ExamSession.objects.create(
            user=request.user,
            exam=exam,
            start_time=now,
            end_time=end_time
        )

        return Response(ExamSessionSerializer(session).data)



# -------------------
# Remaining Time
# -------------------
class RemainingTimeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, course_code):
        try:
            exam = Exam.objects.get(course_code=course_code)
            session = ExamSession.objects.get(user=request.user, exam=exam)
        except (Exam.DoesNotExist, ExamSession.DoesNotExist):
            return Response({"remaining_time": 0})

        now = timezone.now()
        remaining = (session.end_time - now).total_seconds()
        return Response({"remaining_time": max(0, int(remaining))})


# -------------------
# End Exam Session + Calculate Score
# -------------------
class EndExamSessionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, course_code):
        try:
            exam = Exam.objects.get(course_code=course_code)
        except Exam.DoesNotExist:
            return Response({"error": "Exam not found"}, status=404)

        correct_count = StudentAnswer.objects.filter(
            user=request.user,
            question__exam=exam,
            is_correct=True
        ).count()

        StudentScore.objects.update_or_create(
            user=request.user,
            exam=exam,
            defaults={"score": correct_count}
        )

        # Delete session
        ExamSession.objects.filter(user=request.user, exam=exam).delete()

        return Response({"score": correct_count})



class RegisterCourseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        exam_id = request.data.get("exam_id")
        try:
            exam = Exam.objects.get(id=exam_id)
        except Exam.DoesNotExist:
            return Response({"error": "Exam not found"}, status=404)

        registration, created = CourseRegistration.objects.get_or_create(
            user=request.user,
            exam=exam
        )

        return Response(CourseRegistrationSerializer(registration).data)


class MyCoursesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        registrations = CourseRegistration.objects.filter(user=request.user)
        serializer = CourseRegistrationSerializer(registrations, many=True)
        return Response(serializer.data)
