from django.core.management.base import BaseCommand
from pharmacy.models import ProfitAnalytics
from django.utils import timezone

class Command(BaseCommand):
    help = 'Generate profit analytics for yesterday'

    def handle(self, *args, **options):
        yesterday = timezone.now().date() - timezone.timedelta(days=1)
        analytics = ProfitAnalytics.generate_daily_report(yesterday)
        
        self.stdout.write(self.style.SUCCESS(f'Generated profit analytics for {yesterday}:'))
        self.stdout.write(f'Total Sales: ${analytics.total_sales}')
        self.stdout.write(f'Total Cost: ${analytics.total_cost}')
        self.stdout.write(f'Total Profit: ${analytics.total_profit}')
        self.stdout.write(f'Profit Margin: {analytics.profit_margin}%')
        self.stdout.write(f'Number of Sales: {analytics.number_of_sales}')