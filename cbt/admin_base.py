#admin_base.py
import re
from django.contrib import admin

admin.site.site_header = "JustCBT Administration"
admin.site.site_title = "JustCBT Admin Portal"
admin.site.index_title = "Welcome to JustCBT Management"

# --- Helper Functions ---
def is_superadmin(user):
    return user.is_superuser or (
        hasattr(user, "userprofile") and user.userprofile.role == "superadmin"
    )

def is_school_admin(user):
    return hasattr(user, "userprofile") and user.userprofile.role == "admin"


# --- Base Admin Mixin for School Filtering ---
class SchoolScopedAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if is_superadmin(request.user):
            return qs
        if is_school_admin(request.user):
            if hasattr(self.model, 'school'):
                return qs.filter(school=request.user.userprofile.school)
            elif hasattr(self.model, 'userprofile'):
                return qs.filter(userprofile__school=request.user.userprofile.school)
        return qs.none()

    def get_fields(self, request, obj=None):
        fields = list(super().get_fields(request, obj))
        if not is_superadmin(request.user) and is_school_admin(request.user):
            if 'school' in fields:
                fields.remove('school')
        return fields

    def save_model(self, request, obj, form, change):
        if not is_superadmin(request.user) and is_school_admin(request.user):
            # 1. Get the current admin's school
            user_school = request.user.userprofile.school
            
            # 2. Force assign the school to the object BEFORE saving
            if hasattr(obj, 'school'):
                obj.school = user_school
            

        # 4. NOW save the object to the database
        super().save_model(request, obj, form, change)

def normalize_class_name(name):
    """
    Converts 'J.S.S 3' or 'jss3' or 'JSS 3' all into 'jss3'
    """
    return re.sub(r'[^a-zA-Z0-9]', '', name).lower()

