from django.core.management.base import BaseCommand
from django.db import transaction
from pharmacy.models import (
    Medicine, StockEntry, Sale, SaleItem, 
    Supplier, Purchase, PurchaseItem, 
    Customer, Prescription, PrescriptionItem,
    SearchHistory
)
from django.db.utils import OperationalError

class Command(BaseCommand):
    help = 'Clears all data from the pharmacy database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force deletion without confirmation',
        )

    def safe_delete(self, model, model_name):
        try:
            count = model.objects.count()
            model.objects.all().delete()
            return count
        except OperationalError:
            self.stdout.write(self.style.WARNING(f'Table for {model_name} does not exist'))
            return 0
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Error deleting {model_name}: {str(e)}'))
            return 0

    def handle(self, *args, **kwargs):
        if not kwargs['force']:
            confirm = input('This will DELETE ALL DATA from the pharmacy database. Are you sure? (yes/no): ')
            if confirm.lower() != 'yes':
                self.stdout.write(self.style.WARNING('Operation cancelled.'))
                return

        try:
            with transaction.atomic():
                # Delete in correct order to avoid foreign key constraints
                self.stdout.write('Deleting data...')
                
                deletions = [
                    (SearchHistory, 'Search History'),
                    (PrescriptionItem, 'Prescription Items'),
                    (Prescription, 'Prescriptions'),
                    (SaleItem, 'Sale Items'),
                    (Sale, 'Sales'),
                    (PurchaseItem, 'Purchase Items'),
                    (Purchase, 'Purchases'),
                    (StockEntry, 'Stock Entries'),
                    (Medicine, 'Medicines'),
                    (Supplier, 'Suppliers'),
                    (Customer, 'Customers'),
                ]

                counts = {}
                for model, name in deletions:
                    count = self.safe_delete(model, name)
                    if count > 0:
                        counts[name] = count

                # Report what was deleted
                if counts:
                    self.stdout.write(self.style.SUCCESS('\nSuccessfully deleted:'))
                    for model, count in counts.items():
                        self.stdout.write(f'  - {count} {model}')
                else:
                    self.stdout.write(self.style.SUCCESS('\nNo data to delete'))

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'\nError clearing data: {str(e)}')
            ) 