from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from cbt.models import (
    StudentScore, ExamSession, StudentAnswer, 
    CourseRegistration, UserProfile
)

class Command(BaseCommand):
    help = 'Wipes all student activity and student accounts, keeping Schools and Admins intact.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Starting student data reset...'))

        # 1. Clear Activity Data (Results, Sessions, Answers)
        StudentScore.objects.all().delete()
        ExamSession.objects.all().delete()
        StudentAnswer.objects.all().delete()
        CourseRegistration.objects.all().delete()
        self.stdout.write('Cleared: Scores, Sessions, Answers, and Registrations.')

        # 2. Identify and Delete Student Users
        # We filter by the role in UserProfile
        student_profiles = UserProfile.objects.filter(role='student')
        student_count = student_profiles.count()
        
        # Get the actual User objects associated with these profiles
        student_user_ids = student_profiles.values_list('user_id', flat=True)
        
        # Delete the Users (this will cascade delete UserProfiles)
        User.objects.filter(id__in=student_user_ids).delete()

        self.stdout.write(self.style.SUCCESS(f'Successfully deleted {student_count} student accounts.'))
        self.stdout.write(self.style.SUCCESS('Reset Complete. Schools, Courses, and Admins are preserved.'))