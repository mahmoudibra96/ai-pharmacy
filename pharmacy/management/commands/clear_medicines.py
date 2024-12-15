from django.core.management.base import BaseCommand
from pharmacy.models import Medicine
from django.db import transaction

class Command(BaseCommand):
    help = 'Deletes all medicines from the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force deletion without confirmation',
        )

    def handle(self, *args, **kwargs):
        if not kwargs['force']:
            confirm = input('This will delete ALL medicines. Are you sure? (yes/no): ')
            if confirm.lower() != 'yes':
                self.stdout.write(self.style.WARNING('Operation cancelled.'))
                return

        try:
            with transaction.atomic():
                count = Medicine.objects.count()
                Medicine.objects.all().delete()
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully deleted {count} medicines')
                )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error deleting medicines: {str(e)}')
            ) 