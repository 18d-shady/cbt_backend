from rest_framework import serializers
from django.contrib.auth.models import User
from .models import CourseRegistration, Exam, Question, StudentAnswer, ExamSession, StudentScore


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name"]


class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = [
            "id",
            "exam",
            "question_number",
            "question_text",
            "option_a",
            "option_b",
            "option_c",
            "option_d",
            "correct_option",
        ]


class ExamSerializer(serializers.ModelSerializer):
    # include nested questions if needed
    questions = QuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Exam
        fields = [
            "id",
            "course_code",
            "course_title",
            "total_questions",
            "duration_minutes",
            "rules",
            "questions",
        ]

class CourseRegistrationSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    exam = ExamSerializer(read_only=True)
    exam_id = serializers.PrimaryKeyRelatedField(
        queryset=Exam.objects.all(), write_only=True, source="exam"
    )

    class Meta:
        model = CourseRegistration
        fields = ["id", "user", "exam", "exam_id", "registered_on"]

class StudentAnswerSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    question = QuestionSerializer(read_only=True)

    class Meta:
        model = StudentAnswer
        fields = ["id", "user", "question", "selected_option", "is_correct"]


class ExamSessionSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    exam = ExamSerializer(read_only=True)

    class Meta:
        model = ExamSession
        fields = ["id", "user", "exam", "start_time", "end_time"]


class StudentScoreSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    exam = ExamSerializer(read_only=True)

    class Meta:
        model = StudentScore
        fields = ["id", "user", "exam", "score"]


class QuestionWithAnswerSerializer(serializers.ModelSerializer):
    student_answer = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = [
            "id",
            "question_number",
            "question_text",
            "option_a",
            "option_b",
            "option_c",
            "option_d",
            "student_answer",
        ]

    def get_student_answer(self, obj):
        user = self.context.get("request").user
        if not user or user.is_anonymous:
            return None
        try:
            ans = StudentAnswer.objects.get(user=user, question=obj)
            return ans.selected_option
        except StudentAnswer.DoesNotExist:
            return None
