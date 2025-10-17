from django.db import models

from django.db import models
from django.contrib.auth.models import User


class Exam(models.Model):
    course_code = models.CharField(max_length=20, unique=True)
    course_title = models.CharField(max_length=255)
    total_questions = models.PositiveIntegerField()
    duration_minutes = models.PositiveIntegerField()
    rules = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.course_code} - {self.course_title}"


class CourseRegistration(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="registrations")
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="registrations")
    registered_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'exam')

    def __str__(self):
        return f"{self.user.username} -> {self.exam.course_code}"


class Question(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="questions")
    question_number = models.PositiveIntegerField()
    question_text = models.TextField()
    option_a = models.CharField(max_length=255, blank=True, null=True)
    option_b = models.CharField(max_length=255, blank=True, null=True)
    option_c = models.CharField(max_length=255, blank=True, null=True)
    option_d = models.CharField(max_length=255, blank=True, null=True)
    correct_option = models.CharField(max_length=1)  # "A", "B", "C", "D"

    class Meta:
        unique_together = ('exam', 'question_number')

    def __str__(self):
        return f"Q{self.question_number} ({self.exam.course_code})"


class StudentAnswer(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="answers")
    selected_option = models.CharField(max_length=1)  # "A", "B", "C", "D"
    is_correct = models.BooleanField()

    class Meta:
        unique_together = ('user', 'question')

    def __str__(self):
        return f"{self.user.username} - Q{self.question.id} ({'✔' if self.is_correct else '✘'})"


class ExamSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="exam_sessions")
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="sessions")
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    class Meta:
        unique_together = ('user', 'exam')

    def __str__(self):
        return f"{self.user.username} - {self.exam.course_code}"


class StudentScore(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="scores")
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="scores")
    score = models.IntegerField()

    class Meta:
        unique_together = ('user', 'exam')

    def __str__(self):
        return f"{self.user.username} - {self.exam.course_code}: {self.score}"
