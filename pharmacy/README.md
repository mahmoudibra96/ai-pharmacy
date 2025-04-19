# Profit Analytics Setup

## Daily Analytics Generation

To ensure profit analytics are generated automatically each day, set up one of the following:

### Option 1: Using Cron (Recommended for Production)

Add the following line to your crontab (run `crontab -e`):

```bash
0 1 * * * /path/to/python /path/to/manage.py generate_daily_analytics
```

This will run the analytics generation every day at 1 AM.

### Option 2: Using Django Management Command

You can manually generate analytics for any date using:

```bash
python manage.py generate_daily_analytics
```

## Accessing Profit Analytics

1. Navigate to /profit-analytics/ in your browser
2. Use the date range picker to view analytics for specific periods
3. View:
   - Daily profit trends
   - Category performance
   - Top performing products
   - Overall profit margins
   - Sales and cost analysis

## Features

- Track purchase prices and selling prices
- Calculate profits per unit (box and strip)
- Monitor profit margins by product and category
- View daily, weekly, and monthly profit trends
- Identify most profitable products and categories
- Export profit reports for analysis

## Best Practices

1. Always enter accurate purchase prices when adding new products
2. Regularly review profit margins and adjust prices if needed
3. Monitor the daily analytics reports for any anomalies
4. Use the profit analytics dashboard to make informed pricing decisions