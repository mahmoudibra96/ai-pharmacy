from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from pharmacy.models import UserProfile

class Command(BaseCommand):
    help = 'Creates missing user profiles'

    def handle(self, *args, **kwargs):
        users_without_profile = User.objects.filter(userprofile__isnull=True)
        created_count = 0
        
        for user in users_without_profile:
            UserProfile.objects.create(
                user=user,
                role='CASHIER'  # Default role
            )
            created_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully created {created_count} missing user profiles')
        ) 