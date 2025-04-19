from django.core.management.base import BaseCommand
from pharmacy.models import ProfitAnalytics
from django.utils import timezone

class Command(BaseCommand):
    help = 'Generate profit analytics report for a specific date or today'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            help='Date in YYYY-MM-DD format. If not provided, will use today\'s date.',
            required=False
        )

    def handle(self, *args, **options):
        date_str = options.get('date')
        if date_str:
            try:
                date = timezone.datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                self.stdout.write(self.style.ERROR('Invalid date format. Use YYYY-MM-DD'))
                return
        else:
            date = timezone.now().date()

        analytics = ProfitAnalytics.generate_daily_report(date)
        
        self.stdout.write(self.style.SUCCESS(f'Generated profit analytics for {date}:'))
        self.stdout.write(f'Total Sales: ${analytics.total_sales}')
        self.stdout.write(f'Total Cost: ${analytics.total_cost}')
        self.stdout.write(f'Total Profit: ${analytics.total_profit}')
        self.stdout.write(f'Profit Margin: {analytics.profit_margin}%')
        self.stdout.write(f'Number of Sales: {analytics.number_of_sales}')
        self.stdout.write(f'Average Profit per Sale: ${analytics.average_profit_per_sale}')
        self.stdout.write(f'Most Profitable Category: {analytics.most_profitable_category}')