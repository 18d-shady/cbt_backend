from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    School, Question, Exam, CourseRegistration, 
    StudentAnswer, ExamSession, StudentScore, QuestionImage
)

class SchoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = ["id", "name", "color", "icon", "school_type"]

class UserSerializer(serializers.ModelSerializer):
    school = serializers.CharField(source='userprofile.school.name', read_only=True)
    role = serializers.CharField(source='userprofile.role', read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "school", "role"]

class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = [
            "id", "exam", "question_number", "question_text", "question_type",
            "option_a", "option_b", "option_c", "option_d", "correct_answer"
        ]

class ExamSerializer(serializers.ModelSerializer):
    school = SchoolSerializer(read_only=True)
    course_name = serializers.ReadOnlyField(source='course.name')
    # Dynamic field: shows Class Name + Group
    class_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Exam
        fields = [
            "id", "school", "course_name", "class_name", "title",
            "total_questions", "duration_minutes", "rules"
        ]

    def get_class_name(self, obj):
        # Access the class via the course relationship
        target = obj.course.target_class
        if target:
            return f"{target.name} {target.group or ''}".strip()
        return "General"

class ExamSessionSerializer(serializers.ModelSerializer):
    # Adding extra info so the frontend knows exactly when the clock stops
    class Meta:
        model = ExamSession
        fields = ["id", "user", "exam", "start_time", "end_time"]
        
class StudentAnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentAnswer
        fields = ["id", "user", "question", "answer_text", "is_correct", "is_graded", "points_earned"]

class QuestionWithAnswerSerializer(serializers.ModelSerializer):
    student_answer = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = [
            "id", "question_number", "question_text", "question_type",
            "option_a", "option_b", "option_c", "option_d",
            "student_answer", "images"
        ]

    def get_student_answer(self, obj):
        user = self.context.get("request").user
        ans = StudentAnswer.objects.filter(user=user, question=obj).first()
        return ans.answer_text if ans else None

    def get_images(self, obj):
        return [{"image": img.image.url, "caption": img.caption} for img in obj.images.all()]