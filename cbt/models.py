from django.utils import timezone
import datetime
from django.db import models

from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify


def school_icon_path(instance, filename):
    ext = filename.split('.')[-1]
    # If the school exists, use ID; otherwise use a slug of the name
    identifier = instance.id if instance.id else slugify(instance.name)
    return f'schools/{identifier}/logo.{ext}'

class School(models.Model):
    SCHOOL_TYPES = [
        ('secondary', 'Secondary School'),
        ('tertiary', 'Tertiary Institution'),
        ('others', 'Others'),
    ]
    name = models.CharField(max_length=255, unique=True)
    email = models.EmailField(unique=True, default="admin@justcbt.com")
    school_type = models.CharField(max_length=20, choices=SCHOOL_TYPES, default='tertiary')
    color = models.CharField(max_length=10, default="#0D7313")
    icon = models.ImageField(upload_to=school_icon_path, null=True, blank=True)
    is_active = models.BooleanField(default=False)
    subscription_plan = models.CharField(
        max_length=20,
        choices=[
            ('trial', 'Trial'),
            ('monthly', 'Monthly'),
            ('yearly', 'Yearly'),
        ],
        default='trial'
    )

    subscription_start = models.DateTimeField(null=True, blank=True)
    subscription_end = models.DateTimeField(null=True, blank=True)
    trial_used = models.BooleanField(default=False)


    def is_subscription_active(self):
        if not self.subscription_end:
            return False
        return timezone.now() <= self.subscription_end

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.get_school_type_display()})"

class SchoolRequest(models.Model):
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email


class StudentClass(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="classes", null=True)
    name = models.CharField(max_length=100)  # e.g., JSS 3, 200 Level, Primary 5
    group = models.CharField(max_length=100, blank=True, null=True) # e.g., B, Science, Electrical (Power)
    
    class Meta:
        unique_together = ('school', 'name', 'group')
        verbose_name = "Class / Level"

    def __str__(self):
        return f"{self.name} {self.group if self.group else ''}".strip()


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True)
    student_class = models.ForeignKey(StudentClass, on_delete=models.SET_NULL, null=True, blank=True)
    role = models.CharField(
        max_length=20,
        choices=[("student", "Student"), ("admin", "Admin"), ("superadmin", "Superadmin")]
    )
    #must_change_password = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username} - {self.school.name}"
    

class Course(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="courses", null=True)
    name = models.CharField(max_length=255) # e.g., Mathematics or Calculus 101
    target_class = models.ForeignKey(StudentClass, on_delete=models.CASCADE, related_name="courses", null=True, blank=True)
    
    # Tertiary use-case: 'MTH101'
    code = models.CharField(max_length=20, blank=True, null=True, verbose_name="Course Code (For Tertiary)")

    class Meta:
        unique_together = ("school", "name", "code", "target_class")

    def __str__(self):
        return f"{self.name} - {self.target_class.name if self.target_class else 'General'}"


class Exam(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="exams", null=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="exams")
    academic_year = models.CharField(max_length=20, default="2025/2026", help_text="e.g., 2025/2026")
    title = models.CharField(max_length=255, blank=True)
    start_datetime = models.DateTimeField(null=True, blank=True, help_text="When the exam window opens, Date:2026-12-31 14:30:00")
    total_questions = models.PositiveIntegerField()
    duration_minutes = models.PositiveIntegerField()
    rules = models.TextField(blank=True, null=True)

    @property
    def end_datetime(self):
        if self.start_datetime:
            return self.start_datetime + timezone.timedelta(minutes=self.duration_minutes)
        return None

    def __str__(self):
        return f"{self.course} - {self.title}"


class CourseRegistration(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="registrations")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="registrations")
    #exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="registrations")
    registered_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'course')

    def __str__(self):
        return f"{self.user.username} -> {self.course}"


def question_image_path(instance, filename):
    return f'exams/{instance.question.exam.id}/questions/{instance.question.id}/{filename}'

class Question(models.Model):
    QUESTION_TYPES = [
        ('obj', 'Objective (MCQ)'),
        ('tf', 'True / False'),
        ('fitg', 'Fill in the Gap'),
        ('essay', 'Essay / Theory'),
    ]
    
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="questions")
    question_number = models.PositiveIntegerField()#editable=False
    question_type = models.CharField(max_length=10, choices=QUESTION_TYPES, default='obj')
    
    question_text = models.TextField(blank=True, null=True)
    
    # Options are now optional (blank/null = True)
    option_a = models.CharField(max_length=255, blank=True, null=True)
    option_b = models.CharField(max_length=255, blank=True, null=True)
    option_c = models.CharField(max_length=255, blank=True, null=True)
    option_d = models.CharField(max_length=255, blank=True, null=True)
    
    # Correct Answer logic:
    # For MCQ/TF: Store "A", "B", "T", or "F"
    # For FITG: Store the exact string
    # For Essay: Leave blank
    correct_answer = models.TextField(blank=True, null=True, help_text="Correct option letter or exact word for FITG")
    point = models.FloatField(default=1.0, help_text="Points for getting this right")

    class Meta:
        unique_together = ('exam', 'question_number')
        ordering = ['question_number']

    def __str__(self):
        return f"Q{self.question_number} - {self.get_question_type_display()}"
    
    def save(self, *args, **kwargs):
        if not self.question_number:
            # Auto-assign the next number for this specific exam
            last_q = Question.objects.filter(exam=self.exam).order_by("-question_number").first()
            if last_q:
                self.question_number = last_q.question_number + 1
            else:
                self.question_number = 1
        super().save(*args, **kwargs)

class QuestionImage(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to=question_image_path)
    caption = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"Image for {self.question}"
    


class StudentAnswer(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="answers")
    
    # What the student actually typed or selected
    answer_text = models.TextField() 
    
    # Grading fields
    is_graded = models.BooleanField(default=False)
    is_correct = models.BooleanField(default=False)
    points_earned = models.FloatField(default=0.0) # For manual grading/essays

    class Meta:
        unique_together = ('user', 'question')



class ExamSession(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="exam_sessions")
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="sessions")
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    class Meta:
        unique_together = ('user', 'exam')

    def __str__(self):
        return f"{self.user.username} - {self.exam.course.name}"


class StudentScore(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="scores")
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="scores")
    score = models.IntegerField()

    class Meta:
        unique_together = ('user', 'exam')

    def __str__(self):
        return f"{self.user.username} - {self.exam.course.name}: {self.score}"



