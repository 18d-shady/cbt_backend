from datetime import timedelta
from django.shortcuts import redirect, render
from django.utils import timezone
import requests
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib import messages
import json
import hmac
import hashlib
from django.conf import settings
from django.core.mail import send_mail
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse

from .models import Exam, Question, School, StudentAnswer, ExamSession, StudentScore, CourseRegistration, UserProfile
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

        correct_count = StudentAnswer.objects.filter(
            school=school,
            user=user,
            question__exam_id=exam_id,
            is_correct=True
        ).count()

        StudentScore.objects.update_or_create(
            school=school,
            user=user,
            exam_id=exam_id,
            defaults={"score": correct_count}
        )

        session.delete()
        return Response({"score": correct_count})


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
    

# 2. Paystack Webhook (Production Standard)
@csrf_exempt
def paystack_webhook(request):
    payload = request.body
    sig_header = request.headers.get('x-paystack-signature')
    
    # Verify the request is actually from Paystack
    hash = hmac.new(
        settings.PAYSTACK_SECRET_KEY.encode('utf-8'),
        payload,
        hashlib.sha512
    ).hexdigest()

    if hash == sig_header:
        data = json.loads(payload)
        if data['event'] == 'charge.success':
            customer_email = data['data']['customer']['email']
            school = School.objects.filter(email=customer_email).first()
            base_date = school.subscription_end_date if (school.subscription_end_date and school.subscription_end_date > timezone.now()) else timezone.now()
    
            school.subscription_end_date = base_date + timedelta(days=30)
            school.is_active = True
            school.save()
            return HttpResponse(status=200)
    
    return HttpResponse(status=400)

class VerifyPaymentView(APIView):
    permission_classes = [AllowAny] # Allow non-logged in users to verify

    def post(self, request):
        reference = request.data.get("reference")
        plan = request.data.get("plan")
        
        # Verify with Paystack API
        url = f"https://api.paystack.co/transaction/verify/{reference}"
        headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
        response = requests.get(url, headers=headers)
        res_data = response.json()

        if res_data['status'] and res_data['data']['status'] == 'success':
            email = res_data['data']['customer']['email']
            
            # Check if this school/email already exists
            try:
                profile = UserProfile.objects.get(user__email=email)
                school = profile.school
                school.is_active = True
                # logic: add 30 days to current date or end_date
                school.save()
                return Response({"status": "active", "message": "Subscription extended!"})
            
            except UserProfile.DoesNotExist:
                # NEW USER LOGIC
                # Send email to you (Admin) to create the school
                send_mail(
                    subject="NEW SCHOOL PAYMENT - ACTIVATION REQUIRED",
                    message=f"A new user paid for {plan}.\nEmail: {email}\nRef: {reference}\nPlease create their school profile.",
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[settings.ADMIN_EMAIL],
                )
                return Response({
                    "status": "pending", 
                    "message": "Payment verified! Our team will set up your school account within 24 hours."
                })
        
        return Response({"status": "failed"}, status=400)
    
# views.py
def subscription_expired_page(request):
    return render(request, "billing/expired.html", {
        "school": request.user.userprofile.school if request.user.is_authenticated else None
    })

# In your admin.py or views.py
def grade_essays(request, exam_id):
    ungraded = StudentAnswer.objects.filter(
        question__exam_id=exam_id, 
        question__question_type='essay', 
        is_graded=False
    )
    
    if request.method == "POST":
        for answer in ungraded:
            score = request.POST.get(f"score_{answer.id}")
            if score:
                answer.points_earned = float(score)
                answer.is_graded = True
                answer.save()
        messages.success(request, "Scores updated successfully!")
        return redirect("..")

    return render(request, "admin/grade_essays.html", {"answers": ungraded})