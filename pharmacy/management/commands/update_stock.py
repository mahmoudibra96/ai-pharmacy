from django.core.management.base import BaseCommand
from django.utils import timezone
from pharmacy.models import Medicine, StockEntry

class Command(BaseCommand):
    help = 'Update stock quantities based on non-expired stock entries'

    def handle(self, *args, **kwargs):
        today = timezone.now().date()
        updated = 0

        for medicine in Medicine.objects.all():
            valid_stock = StockEntry.objects.filter(
                medicine=medicine,
                expiration_date__gte=today
            ).aggregate(
                total=models.Sum('quantity')
            )['total'] or 0

            if medicine.stock != valid_stock:
                medicine.stock = valid_stock
                medicine.save(update_fields=['stock'])
                updated += 1
                self.stdout.write(
                    f"Updated {medicine.name}: {medicine.stock} -> {valid_stock}"
                )

        self.stdout.write(
            self.style.SUCCESS(f'Successfully updated stock for {updated} medicines')
        )
