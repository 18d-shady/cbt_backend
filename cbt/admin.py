#admin.py
import io
import re
from django.core.files.base import ContentFile
from django.urls import path, reverse
from django.shortcuts import render, redirect
from django.contrib import admin
from django.contrib.auth.models import User
from .models import (
    Course, QuestionImage, Exam, Question, 
    StudentAnswer, ExamSession, StudentScore, CourseRegistration
)
from django.utils.html import format_html
from django.utils.text import slugify
from django.http import HttpResponse
from docx import Document
from docx.shared import Inches
from docx.shared import Pt, RGBColor
import io
from .views import grade_essays


from .admin_base import SchoolScopedAdmin, is_school_admin, is_superadmin
from .admin_users import SchoolAdmin, CustomUserAdmin # Triggers registration

from unfold.admin import ModelAdmin # Ensure you use this
from unfold.decorators import action



@admin.register(Course)
class CourseAdmin(SchoolScopedAdmin, ModelAdmin):
    list_display = ("name", "code", "target_class", "get_school_type")

    def get_school_type(self, obj):
        # If we are looking at an existing object
        if obj and obj.school:
            return obj.school.get_school_type_display()
        return "-"
    get_school_type.short_description = "School Type"

    def get_fields(self, request, obj=None):
        # Start with all fields from the model
        fields = list(super().get_fields(request, obj))
        
        # We only apply hiding logic for School Admins
        # Superadmins should still see everything to fix data if needed
        if is_school_admin(request.user) and not is_superadmin(request.user):
            school_type = request.user.userprofile.school.school_type
            
            if school_type == 'secondary':
                # Hide 'code', keep 'name' and 'student_class'
                if 'code' in fields:
                    fields.remove('code')
            
            else: # 'others'
                # Hide both extra fields, keep only 'name'
                if 'code' in fields: fields.remove('code')
                if 'target_class' in fields: fields.remove('target_class')
        
        return fields

    def get_list_display(self, request):
        # You can even hide columns in the table view!
        list_display = list(self.list_display)
        if is_school_admin(request.user) and not is_superadmin(request.user):
            school_type = request.user.userprofile.school.school_type
            if school_type == 'secondary' and 'code' in list_display:
                list_display.remove('code')
        return list_display
    
class QuestionImageInline(admin.TabularInline):
    model = QuestionImage
    extra = 1
     
class QuestionInline(admin.TabularInline):
    model = Question
    fields = ('question_number', 'question_type')
    extra = 0  # Admin can add as many as they need
    ordering = ('question_number',)

@admin.register(Exam)
class ExamAdmin(SchoolScopedAdmin, ModelAdmin):
    #form = ExamForm # Including the date/time fix from before
    inlines = [QuestionInline]
    list_display = ("title", "course", "total_questions", "grading_actions")
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:exam_id>/generate-word-template/', self.generate_word_template, name="generate-word-template"),
            path('<int:exam_id>/import-word-questions/', self.import_word_questions, name="import-word-questions"),
            path('<int:exam_id>/grade-essays/', self.grade_essays_view, name="grade-essays"),
        ]
        return custom_urls + urls
    
    def generate_word_template(self, request, exam_id):
        exam = self.get_object(request, exam_id)
        questions = exam.questions.all().order_by('question_number')
        
        doc = Document()
        doc.add_heading(f'Exam: {exam.title}', 0)
        
        # Instruction Box
        instruction = doc.add_paragraph()
        run = instruction.add_run("IMPORTANT INSTRUCTIONS:\n")
        run.bold = True
        run.font.color.rgb = RGBColor(255, 0, 0)
        instruction.add_run("1. Do not delete the [[[ % ... % ]]] tags.\n")
        instruction.add_run("2. Paste images directly between the tags for that question.\n")
        instruction.add_run("3. Objective types (obj) must use the [[A]] style below.\n")
        instruction.add_run("4. For 'obj' types, the CORRECT tag must be just the letter (e.g., A, B, C, or D).")

        for q in questions:
            doc.add_paragraph("___________________________________________________")
            p = doc.add_paragraph()
            p.add_run(f"--- Question {q.question_number} ---").bold = True
            
            # Tags with Bold styling
            q_text = doc.add_paragraph()
            q_text.add_run("[[[% Q %]]] ").bold = True
            q_text.add_run(q.question_text or "[Enter Question Here]")
            q_text.add_run(" [[[% /Q %]]]").bold = True

            type_p = doc.add_paragraph()
            type_p.add_run("[[[% TYPE %]]] ").bold = True
            type_p.add_run(q.question_type)
            type_p.add_run(" [[[% /TYPE %]]]").bold = True

            if q.question_type == 'obj':
                doc.add_paragraph("[[[% OPTIONS %]]]").bold = True
                doc.add_paragraph(f"[[A]] {q.option_a or ''}")
                doc.add_paragraph(f"[[B]] {q.option_b or ''}")
                doc.add_paragraph(f"[[C]] {q.option_c or ''}")
                doc.add_paragraph(f"[[D]] {q.option_d or ''}")
                doc.add_paragraph("[[[% /OPTIONS %]]]").bold = True
            
            ans_p = doc.add_paragraph()
            ans_p.add_run("[[[% CORRECT %]]] ").bold = True
            ans_p.add_run(q.correct_answer or "")
            ans_p.add_run(" [[[% /CORRECT %]]]").bold = True
            
            doc.add_paragraph("[[[% END %]]]").bold = True
            # Note: doc.add_page_break() has been removed here to allow continuous scrolling

        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        response = HttpResponse(buffer.read(), content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        response['Content-Disposition'] = f'attachment; filename=edit_{slugify(exam.title)}.docx'
        return response

    def import_word_questions(self, request, exam_id):
        if request.method == "POST":
            exam = Exam.objects.get(id=exam_id)
            word_file = request.FILES.get("word_file")
            doc = Document(word_file)
            
            # 1. Map Image IDs to binary data
            images_data = {}
            for rel in doc.part.rels.values():
                if "image" in rel.target_ref:
                    images_data[rel.rId] = rel.target_part.blob

            # 2. Extract paragraph texts and associate images per paragraph
            full_content = []
            for para in doc.paragraphs:
                found_image = None
                if 'pic:pic' in para._p.xml:
                    img_match = re.search(r'r:embed="(rId\d+)"', para._p.xml)
                    if img_match:
                        found_image = images_data.get(img_match.group(1))
                full_content.append({'text': para.text, 'image': found_image})

            full_text_blob = "\n".join([c['text'] for c in full_content])
            blocks = full_text_blob.split("[[[% END %]]]")

            def extract_tag(tag, text):
                pattern = rf"\[\[\[% {tag} %\]\]\](.*?)\[\[\[% /{tag} %\]\]\]"
                match = re.search(pattern, text, re.DOTALL)
                return match.group(1).strip() if match else ""

            def extract_option(letter, text):
                pattern = rf"\[\[{letter}\]\](.*?)(\[\[|$)"
                match = re.search(pattern, text, re.DOTALL)
                return match.group(1).strip() if match else ""

            highest_num = 0
            content_cursor = 0

            for block in blocks:
                q_match = re.search(r"--- Question (\d+) ---", block)
                if q_match:
                    q_num = int(q_match.group(1))
                    highest_num = max(highest_num, q_num)
                    
                    q_type = extract_tag("TYPE", block).lower()
                    q_text = extract_tag("Q", block)
                    opt_block = extract_tag("OPTIONS", block)
                    
                    # Update Question data
                    question, created = Question.objects.update_or_create(
                        exam=exam,
                        question_number=q_num,
                        defaults={
                            'school': exam.school,
                            'question_type': q_type,
                            'question_text': q_text,
                            'option_a': extract_option('A', opt_block) if q_type == 'obj' else None,
                            'option_b': extract_option('B', opt_block) if q_type == 'obj' else None,
                            'option_c': extract_option('C', opt_block) if q_type == 'obj' else None,
                            'option_d': extract_option('D', opt_block) if q_type == 'obj' else None,
                            'correct_answer': extract_tag("CORRECT", block).upper(),
                        }
                    )

                    # Handle Images: Check content between start of this question and the END tag
                    # We delete existing images first to prevent stacking copies on re-upload
                    QuestionImage.objects.filter(question=question).delete()
                    
                    for i in range(content_cursor, len(full_content)):
                        item = full_content[i]
                        if item['image']:
                            img_name = f"exam_{exam.id}_q{q_num}.png"
                            QuestionImage.objects.create(
                                question=question, 
                                image=ContentFile(item['image'], name=img_name)
                            )
                        
                        if "[[[% END %]]]" in item['text']:
                            content_cursor = i + 1
                            break
            
            if highest_num > exam.total_questions:
                exam.total_questions = highest_num
                exam.save()

            self.message_user(request, f"Processed {highest_num} questions successfully.")
            return redirect("..")
        return render(request, "admin/word_upload_form.html", {"exam_id": exam_id})
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if is_school_admin(request.user) and not is_superadmin(request.user):
            school = request.user.userprofile.school
            if db_field.name == "course":
                kwargs["queryset"] = Course.objects.filter(school=school)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
    def grading_actions(self, obj):
        return format_html(
            '<a class="button" href="{}">Grade Essays</a>&nbsp;'
            '<a class="button" href="{}">Get Word Template</a>&nbsp;'
            '<a class="button" style="background-color: #417690;" href="{}">Import Questions</a>',
            reverse('admin:grade-essays', args=[obj.pk]),
            reverse('admin:generate-word-template', args=[obj.pk]),
            reverse('admin:import-word-questions', args=[obj.pk])
        )
    grading_actions.short_description = "Management"

    def grade_essays_view(self, request, exam_id):
        # Import your view function
        return grade_essays(request, exam_id)


@admin.register(Question)
class QuestionAdmin(SchoolScopedAdmin, ModelAdmin):
    list_display = ("question_number", "exam", "question_type", "question_text")
    list_filter = ("exam", "question_type")
    search_fields = ("question_text",)
    ordering = ("exam", "question_number")

@admin.register(CourseRegistration)
class CourseRegistrationAdmin(SchoolScopedAdmin, ModelAdmin):
    list_display = ("user", "course", "registered_on")
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if is_school_admin(request.user) and not is_superadmin(request.user):
            school = request.user.userprofile.school
            if db_field.name == "user":
                kwargs["queryset"] = User.objects.filter(userprofile__school=school)
            if db_field.name == "course":
                kwargs["queryset"] = Course.objects.filter(school=school)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

# --- Results & Sessions (Read-Only or Limited for Admins) ---

@admin.register(StudentScore)
class StudentScoreAdmin(SchoolScopedAdmin):
    list_display = ("user", "exam", "score")
    readonly_fields = ("user", "exam", "score") # Scores usually shouldn't be edited manually

@admin.register(ExamSession)
class ExamSessionAdmin(SchoolScopedAdmin):
    list_display = ("user", "exam", "start_time", "end_time")

@admin.register(StudentAnswer)
class StudentAnswerAdmin(SchoolScopedAdmin):
    list_display = ("user", "question", "answer_text", "is_correct", "is_graded", "points_earned")


# Re-register User
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
