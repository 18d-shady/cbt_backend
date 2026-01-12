#admin_users.py
import io
import csv
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.contrib.auth.admin import UserAdmin
from django.contrib import admin
from django import forms
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from .models import School, UserProfile, StudentClass, Course, CourseRegistration
from .admin_base import SchoolScopedAdmin, is_school_admin, is_superadmin, normalize_class_name
from django.contrib import messages
from django.db.models import Count
from django.urls import path, reverse
from django.shortcuts import render, redirect
from django.http import HttpResponse

from unfold.admin import ModelAdmin # Ensure you use this
from unfold.decorators import action


# --- Customized Admin Classes ---
class SchoolForm(forms.ModelForm):
    class Meta:
        model = School
        fields = '__all__'
        widgets = {
            'color': forms.TextInput(attrs={'type': 'color', 'style': 'height: 40px; width: 100px;'}),
        }


@admin.register(School)
class SchoolAdmin(ModelAdmin):
    form = SchoolForm
    list_display = ("name", "color_badge", "is_active")

    def color_badge(self, obj):
        if obj.color:
            from django.utils.safestring import mark_safe
            return mark_safe(f'<div style="width:20px; height:20px; background:{obj.color}; border-radius:3px;"></div>')
        return "-"
    color_badge.short_description = "Theme"

    def has_module_permission(self, request):
        return is_superadmin(request.user) # Hide model from sidebar for school admins

    def subscription_status(self, obj):
        return "Active" if obj.is_active else "Inactive"

    # --- ACTION: Send Welcome Email ---
    def send_welcome_email(self, request, queryset):
        for school in queryset:
            # Find the admin user for this school
            admin_profile = UserProfile.objects.filter(school=school, role='admin').first()
            
            if not admin_profile:
                self.message_user(request, f"No admin user found for {school.name}", messages.ERROR)
                continue

            user = admin_profile.user
            subject = f"Welcome to JustCBT - {school.name} Account Active"
            
            # Context for the email template
            context = {
                'school_name': school.name,
                'username': user.username,
                'login_url': "https://yourdomain.com/admin/", # Change to your actual URL
            }
            
            # Render HTML content
            html_content = render_to_string('emails/welcome_credentials.html', context)
            text_content = strip_tags(html_content)

            email = EmailMultiAlternatives(
                subject,
                text_content,
                settings.DEFAULT_FROM_EMAIL,
                [user.email]
            )
            email.attach_alternative(html_content, "text/html")
            email.send()

        self.message_user(request, "Welcome emails sent successfully.")
    
    send_welcome_email.short_description = "Send Welcome Credentials to School Admin"

    # --- ACTION: Bulk Activate ---
    def activate_schools(self, request, queryset):
        queryset.update(is_active=True)
    activate_schools.short_description = "Activate selected schools"



class StudentCreationForm(forms.ModelForm):
    middle_name = forms.CharField(max_length=150, required=False, label="Middle Name")
    # Make password optional during edit
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'border-gray-300 focus:border-indigo-500'}), 
        required=False,
        help_text="Leave blank to keep current password (during edit)."
    )
    username = forms.CharField(
        required=False, 
        help_text="Leave blank to auto-generate based on school rules.",
        widget=forms.TextInput(attrs={'class': 'border-gray-300'})
    )
    student_class = forms.ModelChoiceField(
        queryset=StudentClass.objects.none(), 
        required=True,
        label="Class/Level",
        widget=forms.Select(attrs={'class': 'border-gray-300'})
    )

    class Meta:
        model = User
        fields = ('first_name', 'middle_name', 'last_name', 'username', 'password', 'student_class')

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        if self.request and is_school_admin(self.request.user):
            school = self.request.user.userprofile.school
            self.fields['student_class'].queryset = StudentClass.objects.filter(school=school)

        # --- Prefill Logic for Edit Mode ---
        if self.instance and self.instance.pk:
            # 1. Prefill student_class from UserProfile
            if hasattr(self.instance, 'userprofile'):
                self.fields['student_class'].initial = self.instance.userprofile.student_class
            
            # 2. Prefill middle_name if it was stored in the last_name (per your logic)
            # If your logic stores it separately in a profile, pull it from there instead
            self.fields['password'].help_text = "Only enter a password if you want to change it."


class CustomUserAdmin(SchoolScopedAdmin, UserAdmin, ModelAdmin):
    add_form = StudentCreationForm
    form = StudentCreationForm
    
    # Customize what is shown in the list of users
    list_display = ("username", "get_full_display_name", "get_school", "role_display", "get_class")

    #change_list_template = "admin/user_changelist.html"
    actions_list = ["import_students_link"]
    actions = ['download_existing_slips']
    add_fieldsets = (
        (None, {
            'classes': ('extra_pretty',),
            'fields': ('first_name', 'middle_name', 'last_name', 'username', 'password', 'student_class'),
        }),
    )

    def get_full_display_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"
    get_full_display_name.short_description = "Full Name"

    def get_school(self, obj):
        return obj.userprofile.school.name if hasattr(obj, 'userprofile') and obj.userprofile.school else "-"
    get_school.short_description = "School"

    def role_display(self, obj):
        return obj.userprofile.role if hasattr(obj, 'userprofile') else "-"
    role_display.short_description = "Role"

    def get_class(self, obj):
        return obj.userprofile.student_class if hasattr(obj, 'userprofile') and obj.userprofile.student_class else "-"
    get_class.short_description = "Class"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if is_superadmin(request.user):
            return qs
        if is_school_admin(request.user):
            # Strict filter: only show users in their school
            return qs.filter(userprofile__school=request.user.userprofile.school)
        return qs.none()
    
    search_fields = ("username", "first_name", "last_name", "userprofile__student_class__name")

    list_filter = (
        "is_active", 
        "userprofile__student_class", # Allows filtering by the Class object
        "userprofile__school"         # If you are a superadmin, you can filter by school too
    )

    def get_fieldsets(self, request, obj=None):
        # If it's a Superadmin, use the default full UserAdmin fieldsets
        if is_superadmin(request.user):
            return super().get_fieldsets(request, obj)
        
        # If we are ADDING a new user (obj is None)
        if not obj:
            return (
                (None, {'fields': ('username', 'password', 'student_class')}),
                ('Personal info', {'fields': ('first_name', 'middle_name', 'last_name')}),
                ('Status', {'fields': ('is_active',)}),
            )

        # If we are EDITING an existing user
        return (
            (None, {'fields': ('username', 'password', 'student_class')}),
            ('Personal info', {'fields': ('first_name', 'middle_name', 'last_name')}),
            ('Status', {'fields': ('is_active',)}),
        )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('import-students/', self.import_students, name="import-students"),
            path('download-sample/', self.download_sample, name="download-sample"),
            path('download-bulk-slips/', self.download_bulk_slips, name="download-bulk-slips"),
        ]
        return custom_urls + urls
    
    def download_sample(self, request):
        """Generates a downloadable CSV template for the admin."""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="student_upload_sample.csv"'
        
        writer = csv.writer(response)
        # Header row
        writer.writerow(['first_name', 'middle_name', 'last_name', 'password', 'class_name', 'group_name'])
        # Example rows
        writer.writerow(['John', 'Quincy', 'Adams', 'Pass123!', 'SS3', 'Science'])
        writer.writerow(['Mary', '', 'Amaka', 'Pass123!', 'JS3', ''])
        writer.writerow(['Jane', '', 'Smith', 'Student2026', '200 Level (Electrical Electronics, Engineering)', 'Power'])
        writer.writerow(['Adams', 'Jay', 'Husseini', 'Student2026', '200 Level (Electrical Electronics, Engineering)', ''])
        
        return response
    
    def generate_school_prefix(self, school_name):
        words = school_name.split()
        
        # Rule: Only one word -> first 3 letters
        if len(words) == 1:
            return words[0][:3].lower()
        
        # Rule: Exactly two words -> first 2 of word1 + first 1 of word2
        # Example: "Flora School" -> "fls"
        if len(words) == 2:
            return (words[0][:2] + words[1][0]).lower()
        
        # Rule: Three or more words -> first 3 initials
        # Example: "Great Heights Academy" -> "gha"
        initials = "".join([word[0].lower() for word in words])
        return initials[:3]
    
    def create_student_logic(self, school, first, last, password, middle="", class_name=None, student_class_obj=None, manual_username=None):
        if manual_username and manual_username.strip():
            username = manual_username.strip()
        else:
            prefix = self.generate_school_prefix(school.name)
            # Find the next available number for THIS school
            count = User.objects.filter(userprofile__school=school, username__startswith=prefix).count()
            
            new_index = count + 1
            username = f"{prefix}{new_index}"
            # Safety: if flo1 exists but was deleted or moved, skip until we find a free slot
            while User.objects.filter(username=username).exists():
                new_index += 1
                username = f"{prefix}{new_index}"

        # Create User
        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=first,
            last_name=f"{last} {middle}" if middle else last
        )

        # Handle Class Registration (String from CSV or Object from Form)
        if not student_class_obj and class_name:
            student_class_obj, _ = StudentClass.objects.get_or_create(
                school=school, 
                name=class_name
            )

        # Profile link
        UserProfile.objects.create(
            user=user,
            school=school,
            role='student',
            student_class=student_class_obj
        )

        # Course Auto-Registration
        if student_class_obj:
            courses = Course.objects.filter(target_class=student_class_obj)
            for course in courses:
                CourseRegistration.objects.get_or_create(user=user, course=course, school=school)

        return user, username

    # --- 3. UI SAVE HOOK (Single Student) ---
    def save_model(self, request, obj, form, change):
        if not change and is_school_admin(request.user):
            # We ignore 'obj' and use our logic to create the user + profile + courses
            school = request.user.userprofile.school
            raw_password = form.cleaned_data.get('password')
            
            user, final_username = self.create_student_logic(
                school=school,
                first=form.cleaned_data.get('first_name'),
                middle=form.cleaned_data.get('middle_name', ''),
                last=form.cleaned_data.get('last_name'),
                password=raw_password,
                student_class_obj=form.cleaned_data.get('student_class'),
                manual_username=form.cleaned_data.get('username')
            )
            
            # Store for the PDF response
            request._created_student = {
                'name': f"{user.first_name} {user.last_name}",
                'username': final_username,
                'password': raw_password,
                'school': school.name
            }
        else:
            new_password = form.cleaned_data.get('password')
            if new_password:
                obj.set_password(new_password)
            
            # Update the student class in the Profile
            new_class = form.cleaned_data.get('student_class')
            if hasattr(obj, 'userprofile'):
                profile = obj.userprofile
                profile.student_class = new_class
                profile.save()
            
            super().save_model(request, obj, form, change)

    def response_add(self, request, obj, post_url_continue=None):
        if hasattr(request, '_created_student'):
            return self.generate_single_pdf(request._created_student)
        return super().response_add(request, obj, post_url_continue)

    def generate_single_pdf(self, data):
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{data["username"]}_slip.pdf"'
        p = canvas.Canvas(response, pagesize=A4)
        # Draw Slip (Simple Design)
        p.setFont("Helvetica-Bold", 14)
        p.drawString(100, 750, f"EXAMINATION ACCESS SLIP: {data['school']}")
        p.line(100, 745, 500, 745)
        p.setFont("Helvetica", 12)
        p.drawString(100, 720, f"Full Name: {data['name']}")
        p.drawString(100, 700, f"Username: {data['username']}")
        p.drawString(100, 680, f"Password: {data['password']}")
        p.showPage()
        p.save()
        return response

    def get_form(self, request, obj=None, **kwargs):
        # Use add_form for new users, regular form for editing
        if obj is None:
            kwargs['form'] = self.add_form
            
        form_class = super().get_form(request, obj, **kwargs)
        
        # This is the crucial part: it passes the request to the form
        class ConfigurationForm(form_class):
            def __init__(self, *args, **kwargs):
                kwargs['request'] = request
                super().__init__(*args, **kwargs)
        
        return ConfigurationForm

    @action(
            description="Bulk Upload Students", 
            url_path="import-students-btn",
            icon="upload_file", # Material Icon Name
        )
    def import_students_link(self, request):
        return redirect("admin:import-students")
    
    def import_students(self, request):
        if request.method == "POST":
            csv_file = request.FILES.get("csv_file")
            if not csv_file: return redirect("..")

            io_string = io.StringIO(csv_file.read().decode('utf-8'))
            reader = csv.reader(io_string)
            next(reader) # skip header

            imported_data = []
            school = request.user.userprofile.school
            
            for row in reader:
                if len(row) < 4: continue
                row += [""] * (6 - len(row)) # padding
                first, middle, last, password, class_name, _ = [item.strip() for item in row]

                user, final_username = self.create_student_logic(
                    school=school, first=first, middle=middle, last=last, 
                    password=password, class_name=class_name
                )

                imported_data.append({
                    'name': f"{first} {last}",
                    'username': final_username,
                    'password': password 
                })
                request.session['latest_import'] = imported_data

            return render(request, "admin/import_success.html", {"students": imported_data, "count": len(imported_data)})
        return render(request, "admin/csv_form.html")
    

    def download_bulk_slips(self, request):
        students = request.session.get('latest_import', [])
        if not students:
            messages.error(request, "No recent import data found.")
            return redirect("..")

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="bulk_login_slips.pdf"'
        
        p = canvas.Canvas(response, pagesize=A4)
        width, height = A4
        y_position = height - 1*inch

        for student in students:
            # Check if we need a new page
            if y_position < 2*inch:
                p.showPage()
                y_position = height - 1*inch

            # Draw a box for the slip
            p.rect(1*inch, y_position - 1.5*inch, 6*inch, 1.4*inch)
            
            # Add Content
            p.setFont("Helvetica-Bold", 12)
            p.drawString(1.2*inch, y_position - 0.3*inch, f"SCHOOL: {request.user.userprofile.school.name}")
            p.setFont("Helvetica", 11)
            p.drawString(1.2*inch, y_position - 0.6*inch, f"Name: {student['name']}")
            p.drawString(1.2*inch, y_position - 0.8*inch, f"Username: {student['username']}")
            p.setFont("Helvetica-Bold", 11)
            p.drawString(1.2*inch, y_position - 1.0*inch, f"Password: {student['password']}")
            
            # Move cursor down for next slip
            y_position -= 1.7*inch

        p.save()
        return response

    # --- PDF ACTION (FOR EXISTING STUDENTS) ---
    def download_existing_slips(self, request, queryset):
        """
        This is for students who already exist. 
        It shows usernames only (passwords are hashed and cannot be shown).
        """
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="student_usernames.pdf"'
        p = canvas.Canvas(response, pagesize=A4)
        y = 800
        
        p.setFont("Helvetica-Bold", 14)
        p.drawString(100, y, f"Student Usernames - {request.user.userprofile.school.name}")
        y -= 30

        for user in queryset:
            if y < 100: p.showPage(); y = 800
            p.rect(80, y-50, 400, 40)
            p.setFont("Helvetica-Bold", 10)
            p.drawString(100, y-25, f"Name: {user.first_name} {user.last_name}")
            p.setFont("Helvetica", 10)
            p.drawString(100, y-40, f"Username: {user.username} (Password: Use your school password)")
            y -= 60
            
        p.save()
        return response
    download_existing_slips.short_description = "Download Username Slips (Existing Students)"


@admin.register(UserProfile)
class UserProfileAdmin(SchoolScopedAdmin):
    list_display = ("user", "school", "role")
    list_filter = ("role",)

class MergeClassesForm(forms.Form):
    # This will be the name assigned to the merged result
    master_name = forms.CharField(
        label="New/Primary Class Name", 
        help_text="All selected classes will be renamed to this and merged."
    )

@admin.register(StudentClass)
class StudentClassAdmin(SchoolScopedAdmin, ModelAdmin):
    list_display = ("name", "group", "school")
    list_filter = ("name",)
    actions = ['bulk_register_courses', 'merge_classes_action']

    #change_list_template = "admin/studentclass_changelist.html"
    actions_list = ["run_cleanup_link"]

    @action(
        description="Run Class Cleanup Tool",
        icon="cleaning_services", 
        url_path="cleanup-tool-btn"
    )
    def run_cleanup_link(self, request):
        return redirect("admin:studentclass-cleanup")


    @action(
        description="Merge selected classes into one",
        url_path="merge-classes",
        icon="merge_type", # Material icon name
    )
    def merge_classes_action(self, request, queryset):
        if queryset.count() < 2:
            self.message_user(request, "Please select at least two classes.", messages.WARNING)
            return

        if 'apply' in request.POST:
            form = MergeClassesForm(request.POST)
            if form.is_valid():
                master_name = form.cleaned_data['master_name']
                base_class = queryset.first()
                other_classes = queryset.exclude(id=base_class.id)

                # Execute Move
                profiles_moved = UserProfile.objects.filter(student_class__in=other_classes).update(student_class=base_class)
                courses_moved = Course.objects.filter(target_class__in=other_classes).update(target_class=base_class)
                
                base_class.name = master_name
                base_class.save()
                other_classes.delete()

                self.message_user(request, f"Merged into '{master_name}'. {profiles_moved} students moved.")
                return redirect(request.get_full_path())
        else:
            form = MergeClassesForm()

        return render(request, 'admin/merge_classes_confirmation.html', {
            'items': queryset,
            'form': form,
            'action': 'merge_classes_action',
            # This is critical for the IDs to persist!
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
        })

    @action(
        description="Register Students for Courses",
        icon="how_to_reg",
    )
    def bulk_register_courses(self, request, queryset):
        total_registrations = 0
        for student_class in queryset:
            # 1. Get all students in this class
            students = User.objects.filter(userprofile__student_class=student_class)
            # 2. Get all courses assigned to this class
            courses = Course.objects.filter(target_class=student_class)
            
            for student in students:
                for course in courses:
                    _, created = CourseRegistration.objects.get_or_create(
                        user=student,
                        course=course,
                        school=student_class.school
                    )
                    if created:
                        total_registrations += 1
                                      
        self.message_user(request, f"Successfully created {total_registrations} new course registrations.")
    #bulk_register_courses.short_description = "Register all students in selected classes for their courses"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('cleanup/', self.admin_site.admin_view(self.cleanup_view), name='studentclass-cleanup'),
        ]
        return custom_urls + urls

    def cleanup_view(self, request):
        school = request.user.userprofile.school
        all_classes = StudentClass.objects.filter(school=school)
        
        # Dictionary to group similar names
        groups = {}
        for cls in all_classes:
            norm = normalize_class_name(cls.name)
            if norm not in groups:
                groups[norm] = []
            groups[norm].append(cls)
        
        # Filter groups that actually have duplicates
        duplicates = {k: v for k, v in groups.items() if len(v) > 1}

        if request.method == "POST":
            # Process the auto-merge
            group_to_merge = request.POST.get("group_key")
            if group_to_merge in duplicates:
                target_group = duplicates[group_to_merge]
                master = target_group[0]
                others = target_group[1:]
                
                # Move students and courses (same logic as manual merge)
                UserProfile.objects.filter(student_class__in=others).update(student_class=master)
                Course.objects.filter(target_class__in=others).update(target_class=master)
                
                # Delete duplicates
                for o in others:
                    o.delete()
                
                self.message_user(request, f"Merged variations of {master.name} successfully.")
                return redirect('admin:studentclass-cleanup')

        return render(request, 'admin/class_cleanup.html', {
            'duplicates': duplicates,
            'title': "Class Name Cleanup Tool"
        })

    