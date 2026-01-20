from datetime import timedelta
from django.utils.timezone import now
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
import requests
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.db.models import Sum
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib import messages
from rest_framework.decorators import api_view
import json
import hmac
import hashlib
from django.conf import settings
from django.core.mail import send_mail
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse

from .models import Exam, Question, School, SchoolRequest, StudentAnswer, ExamSession, StudentScore, CourseRegistration, UserProfile
from .serializers import (
    ExamSerializer,
    QuestionWithAnswerSerializer,
    ExamSessionSerializer,
    UserSerializer,
)


# -------------------
# Student Login (validate student exam number + course)
# -------------------

class StudentLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        exam_no = request.data.get("examNo")
        password = request.data.get("password")

        user = authenticate(username=exam_no, password=password)
        if not user:
            return Response({"valid": False, "error": "Invalid credentials"}, status=400)
        
        school = user.userprofile.school
        now = timezone.now()

        registrations = CourseRegistration.objects.filter(user=user).values_list('course_id', flat=True)

        # We look for exams where 'now' is between start and end (start + duration)
        available_exams = Exam.objects.filter(
            course_id__in=registrations,
            school=school,
            start_datetime__date=now.date() # Must be today
        )

        if not available_exams.exists():
            return Response({
                "valid": False, 
                "error": "You have no exams scheduled for today."
            }, status=400)
        
        active_exam = None
        upcoming_exam = None

        for exam in available_exams:
            # If current time is after start AND before (start + duration)
            if exam.start_datetime <= now <= exam.end_datetime:
                active_exam = exam
                break
            elif exam.start_datetime > now:
                upcoming_exam = exam

        if not active_exam:
            if upcoming_exam:
                start_time_str = upcoming_exam.start_datetime.strftime("%I:%M %p")
                return Response({
                    "valid": False, 
                    "error": f"Your exam ({upcoming_exam.course.name}) is scheduled for today at {start_time_str}. Please login then."
                }, status=403)
            else:
                return Response({
                    "valid": False, 
                    "error": "Your exam window for today has already passed."
                }, status=403)

        refresh = RefreshToken.for_user(user)
        return Response({
            "valid": True,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "student": UserSerializer(user).data,
            "exam": ExamSerializer(active_exam).data
        })

# -------------------
# Get Subjects Registered (all courses this student registered for)
# -------------------
class SubjectRegisteredView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school = request.user.userprofile.school
        # Pulling codes from the Course model via Registration
        registrations = CourseRegistration.objects.filter(user=request.user, school=school).select_related("course")
        subjects = [reg.course.name for reg in registrations]
        return Response({"subjects": subjects})


# -------------------
# Exam Details
# -------------------
class ExamDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, exam_id):
        school = request.user.userprofile.school
        try:
            exam = Exam.objects.get(id=exam_id, school=school)
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

    def get(self, request, exam_id, index): # Changed parameter
        school = request.user.userprofile.school
        try:
            exam = Exam.objects.get(id=exam_id, school=school)
            question = Question.objects.filter(exam=exam).order_by("question_number")[index]
        except (Exam.DoesNotExist, IndexError):
            return Response({"error": "Question not found"}, status=404)

        serializer = QuestionWithAnswerSerializer(question, context={"request": request})
        return Response(serializer.data)


# -------------------
# Save Student Answer
# -------------------
class SaveAnswerView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        school = request.user.userprofile.school
        question_id = request.data.get("questionId")
        answer_text = request.data.get("selectedOption") # This is the generic answer

        question = generics.get_object_or_404(Question, id=question_id, school=school)

        # Logic for auto-grading Objective, T/F, and FITG
        is_correct = False
        if question.question_type in ['obj', 'tf', 'fitg']:
            provided = str(answer_text).strip().lower()
            actual = str(question.correct_answer).strip().lower()
            if provided == actual:
                is_correct = True

        answer, created = StudentAnswer.objects.update_or_create(
            user=request.user,
            question=question,
            defaults={
                'school': school,
                'answer_text': answer_text,
                'is_correct': is_correct,
                'is_graded': question.question_type != 'essay' # Essay remains ungraded
            }
        )
        return Response({"status": "saved", "is_correct": is_correct})


# -------------------
# Start Exam Session
# -------------------
class StartExamSessionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, exam_id):
        school = request.user.userprofile.school
        try:
            exam = Exam.objects.get(id=exam_id, school=school)
        except Exam.DoesNotExist:
            return Response({"error": "Exam not found"}, status=404)

        if not exam.start_datetime:
            return Response({"error": "Exam start time is not configured."}, status=400)

        now = timezone.now()
        official_end_time = exam.start_datetime + timezone.timedelta(minutes=exam.duration_minutes)

        # Discrepancy Fix: Check if it's too early
        if now < exam.start_datetime:
            return Response({"error": "The exam has not started yet."}, status=403)

        # Check if it's too late
        if now > official_end_time:
            return Response({"error": "The exam window has already closed."}, status=403)

        existing = ExamSession.objects.filter(user=request.user, exam=exam).first()
        if existing:
            return Response(ExamSessionSerializer(existing).data)

        session = ExamSession.objects.create(
            school=school,
            user=request.user,
            exam=exam,
            start_time=now,           
            end_time=official_end_time # Fixed official deadline
        )
        return Response(ExamSessionSerializer(session).data)


# -------------------
# Remaining Time
# -------------------
class RemainingTimeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, exam_id):
        school = request.user.userprofile.school
        try:
            exam = Exam.objects.get(id=exam_id, school=school)
            session = ExamSession.objects.get(school=school, user=request.user, exam=exam)
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

    def post(self, request, exam_id):
        school = request.user.userprofile.school
        user = request.user
        
        # Discrepancy Fix: Verify session exists and isn't expired before allowing submit
        session = ExamSession.objects.filter(user=user, exam_id=exam_id).first()
        if not session:
             return Response({"error": "No active session found"}, status=404)

        # Logic: We allow the submit even if slightly over, but you can be strict:
        # if timezone.now() > session.end_time + timezone.timedelta(seconds=30): ...

        # Sum the 'point' value of all questions where is_correct is True
        score_data = StudentAnswer.objects.filter(
            school=school,
            user=user,
            question__exam_id=exam_id,
            is_correct=True
        ).aggregate(total_points=Sum('question__point'))

        total_score = score_data['total_points'] or 0.0

        # Handle Essays: Add manually graded points
        essay_points = StudentAnswer.objects.filter(
            user=user,
            question__exam_id=exam_id,
            question__question_type='essay',
            is_graded=True
        ).aggregate(essay_sum=Sum('points_earned'))['essay_sum'] or 0.0

        final_total = total_score + essay_points

        StudentScore.objects.update_or_create(
            school=school,
            user=user,
            exam_id=exam_id,
            defaults={"score": final_total}
        )

        session.delete()
        return Response({"score": final_total})


class DemoRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        name = request.data.get("name")
        email = request.data.get("email")
        phone = request.data.get("phone")

        # In production: Send email to Admin
        send_mail(
            subject=f"New Demo Request: {name}",
            message=f"Name: {name}\nEmail: {email}\nPhone: {phone}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.ADMIN_EMAIL],
        )
        return Response({"message": "Request received"}, status=status.HTTP_201_CREATED)


class CheckSchoolView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")

        school = School.objects.filter(email=email).first()

        if school:
            return Response({
                "exists": True,
                "school_name": school.name,
                "is_active": school.is_active,
            })

        return Response({"exists": False})

class RequestSchoolView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        phone = request.data.get("phone")

        SchoolRequest.objects.get_or_create(
            email=email,
            defaults={"phone": phone}
        )

        send_mail(
            "New School Creation Request",
            f"Email: {email}\nPhone: {phone}",
            settings.DEFAULT_FROM_EMAIL,
            [settings.ADMIN_EMAIL],
        )

        return Response({
            "message": "School request submitted. You will be contacted."
        }, status=201)


PLAN_DAYS = {
    'trial': 30,
    'monthly': 30,
    'yearly': 365,
}   

class StartSubscriptionView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        plan = request.data.get("plan")  # trial | monthly | yearly
        email = request.data.get("email")

        if plan not in PLAN_DAYS:
            return Response({"error": "Invalid plan"}, status=400)

        school = School.objects.filter(email=email).first()

        # Ensure school exists
        if not school:
            return Response({
                "error": "No school found with this email. Request creation instead."
            }, status=404)  

        # ---- TRIAL ----
        if plan == "trial":
            if school.trial_used:
                return Response(
                    {"error": "Trial already used"},
                    status=403
                )

            self.activate_subscription(school, plan)
            school.trial_used = True
            school.save()

            return Response({"message": "Trial activated"})

        # ---- PAID PLANS ----
        return self.initialize_paystack_payment(email, plan)

    def activate_subscription(self, school, plan):
        from django.utils.timezone import now
        from datetime import timedelta

        school.subscription_plan = plan
        school.subscription_start = now()
        school.subscription_end = now() + timedelta(days=PLAN_DAYS[plan])
        school.is_active = True
        school.save()

    def initialize_paystack_payment(self, email, plan):
        amount_map = {
            'monthly': 1000000,
            'yearly': 10000000,
        }
        try:

            response = requests.post(
                "https://api.paystack.co/transaction/initialize",
                headers={
                    "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "email": email,
                    "amount": amount_map[plan],
                    "metadata": {
                        "plan": plan,
                    },
                }
            )

            res_data = response.json()

            # If Paystack returns a 200 but 'status' is False, or if it returns a 400/401
            if response.status_code != 200 or not res_data.get('status'):
                return Response({
                    "error": res_data.get('message', "Paystack initialization failed")
                }, status=status.HTTP_400_BAD_REQUEST)

            return Response(res_data) # This contains the data.authorization_url

        except requests.exceptions.RequestException as e:
            return Response({"error": "External payment gateway unreachable"}, status=503)



@csrf_exempt
def paystack_webhook(request):
    payload = json.loads(request.body)

    if payload['event'] != 'charge.success':
        return HttpResponse(status=200)

    data = payload['data']
    email = data['customer']['email']
    plan = data['metadata']['plan']

    school = School.objects.filter(email=email).first()

    if not school:
        return Response({
            "error": "No school found with this email. Request creation instead."
        }, status=404)

    days = PLAN_DAYS[plan]

    school.subscription_plan = plan
    school.subscription_start = now()
    school.subscription_end = now() + timedelta(days=days)
    school.is_active = True
    school.save()

    return HttpResponse(status=200)



# In your admin.py or views.py
from django.db.models import Sum

def grade_essays(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    answers = StudentAnswer.objects.filter(
        question__exam=exam, 
        question__question_type='essay'
    ).select_related('user', 'question').order_by('is_graded', 'user')
    
    if request.method == "POST":
        # 1. Update the individual essay answers
        for answer in answers:
            score_input = request.POST.get(f"score_{answer.id}")
            if score_input is not None and score_input != "":
                val = float(score_input)
                # Cap the score at the question's max points
                val = min(val, answer.question.point)
                
                answer.points_earned = val
                answer.is_graded = True
                # A question is 'correct' if it earned any points
                answer.is_correct = True if val > 0 else False
                answer.save()

        # 2. Recalculate StudentScores (DO THIS ONCE outside the loop)
        # Find all students who took this exam
        student_ids = StudentAnswer.objects.filter(question__exam=exam).values_list('user', flat=True).distinct()
        
        for s_id in student_ids:
            total_pts = StudentAnswer.objects.filter(
                user_id=s_id, 
                question__exam=exam
            ).aggregate(total=Sum('points_earned'))['total'] or 0.0
            
            StudentScore.objects.update_or_create(
                user_id=s_id, 
                exam=exam,
                defaults={'score': int(total_pts), 'school': exam.school}
            )
        
        messages.success(request, "Grades saved. Scores recalculated for all students.")
        return redirect("..")

    return render(request, "admin/grade_essays.html", {"answers": answers, "exam": exam})