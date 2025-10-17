
from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin
from .models import Exam, Question, StudentAnswer, ExamSession, StudentScore, CourseRegistration


# -----------------
# Customize User (student) admin
# -----------------
class CustomUserAdmin(UserAdmin):
    # Show only exam_no (username), first name, last name, is_staff
    list_display = ("username", "first_name", "last_name", "is_staff")
    search_fields = ("username", "first_name", "last_name")

    fieldsets = (
        (None, {"fields": ("username", "password")}),  # username = exam_no
        ("Personal info", {"fields": ("first_name", "last_name", "email")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "password1", "password2"),
        }),
    )


# -----------------
# Exam and Question Admin
# -----------------
class QuestionInline(admin.TabularInline):
    model = Question
    extra = 5  # show 5 empty rows by default


class ExamAdmin(admin.ModelAdmin):
    list_display = ("course_code", "course_title", "total_questions", "duration_minutes")
    search_fields = ("course_code", "course_title")
    inlines = [QuestionInline]





class CourseRegistrationAdmin(admin.ModelAdmin):
    list_display = ("user", "exam", "registered_on")
    search_fields = ("user__username", "exam__course_code")

# -----------------
# Register everything
# -----------------
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
admin.site.register(Exam, ExamAdmin)
admin.site.register(StudentAnswer)
admin.site.register(CourseRegistration, CourseRegistrationAdmin)


