from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from pharmacy.models import UserProfile

class Command(BaseCommand):
    help = 'Makes a user an admin'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str)

    def handle(self, *args, **options):
        username = options['username']
        try:
            user = User.objects.get(username=username)
            
            # Check if UserProfile exists
            profile, created = UserProfile.objects.get_or_create(
                user=user,
                defaults={'role': 'ADMIN'}
            )
            
            if not created:
                profile.role = 'ADMIN'
                profile.save()
            
            self.stdout.write(
                self.style.SUCCESS(f'Successfully made {username} an admin!')
            )
            
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'User {username} does not exist!')
            ) 