import os
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from .models import School, StudentAnswer, StudentScore, UserProfile, Exam, Question, CourseRegistration, StudentClass, Course
from django.utils.text import slugify


TEMP_ADMIN_PASSWORD = "ChangeMe@123"

@receiver(post_save, sender=School)
def create_school_admin(sender, instance, created, **kwargs):
    if not created:
        return

    username = f"{slugify(instance.name)}_admin" # my-school_admin
    user, user_created = User.objects.get_or_create(username=username)
    
    if user_created:
        user.set_password(TEMP_ADMIN_PASSWORD)
        user.is_staff = True
        user.save()

    UserProfile.objects.get_or_create(
        user=user,
        defaults={'school': instance, 'role': "admin"}
    )

    group, _ = Group.objects.get_or_create(name='School Admins')
    
    # Safely add permissions
    if not group.permissions.exists():
        models = [Exam, Question, CourseRegistration, User, StudentAnswer, StudentScore, StudentClass, Course]
        for model in models:
            try:
                content_type = ContentType.objects.get_for_model(model)
                perms = Permission.objects.filter(content_type=content_type)
                group.permissions.add(*perms)
            except:
                pass # Guard against migration race conditions

    user.groups.add(group)



@receiver(post_delete, sender=UserProfile)
def delete_associated_user(sender, instance, **kwargs):
    if instance.user:
        instance.user.delete()

@receiver(post_delete, sender=User)
def delete_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'userprofile'):
        instance.userprofile.delete()

@receiver(post_delete, sender=School)
def delete_school_icon(sender, instance, **kwargs):
    if instance.icon:
        if os.path.isfile(instance.icon.path):
            os.remove(instance.icon.path)