from django.db import models
from django.urls import reverse
import barcode
from barcode.writer import ImageWriter
from io import BytesIO
from django.core.files import File
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from decimal import Decimal

class Customer(models.Model):
    CUSTOMER_TYPE_CHOICES = [
        ('REGULAR', 'عميل عادي'),
        ('FAMILY', 'من الأقارب'),
        ('VIP', 'عميل مميز'),
        ('WHOLESALE', 'تاجر جملة'),
    ]

    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, unique=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    points = models.IntegerField(default=0)
    customer_type = models.CharField(
        max_length=20,
        choices=CUSTOMER_TYPE_CHOICES,
        default='REGULAR',
        verbose_name='نوع العميل'
    )
    discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text='نسبة الخصم الخاصة بالعميل'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.phone})"

    def add_points(self, amount):
        """Add loyalty points based on purchase amount"""
        points_to_add = int(amount / 10)  # 1 point for every $10 spent
        self.points += points_to_add
        self.save()
        return points_to_add

    def get_discount_price(self, original_price):
        """Calculate discounted price based on customer type"""
        if self.customer_type == 'FAMILY':
            # للأقارب: نسبة ربح بسيطة فوق سعر الشراء
            return original_price * Decimal('1.10')  # 10% profit margin
        return original_price * (1 - (self.discount_percentage / 100))

class Sale(models.Model):
    user = models.ForeignKey('auth.User', on_delete=models.PROTECT)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=20, choices=[
        ('CASH', 'Cash'),
        ('CARD', 'Card'),
    ], default='CASH')
    is_completed = models.BooleanField(default=False)

    def __str__(self):
        return f"Sale #{self.id} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

    def calculate_total(self):
        total = sum(item.subtotal for item in self.items.all())
        self.total_amount = total
        self.save()
        return total

    @property
    def total_profit(self):
        """Calculate total profit for this sale"""
        return sum(item.profit for item in self.items.all())

    @property
    def profit_margin_percentage(self):
        """Calculate overall profit margin percentage for this sale"""
        if self.total_amount > 0:
            return (self.total_profit / self.total_amount) * 100
        return 0
        
    def get_profit_by_category(self):
        """Get profits broken down by medicine category"""
        category_profits = {}
        for item in self.items.all():
            category = item.medicine.get_category_display()
            if category not in category_profits:
                category_profits[category] = 0
            category_profits[category] += item.profit
        return category_profits

class Medicine(models.Model):
    CATEGORY_CHOICES = [
        ('OTC', 'Over The Counter'),
        ('PRE', 'Prescription'),
        ('SUP', 'Supplements'),
        ('COS', 'Cosmetics'),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    purchase_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Cost price of the product"
    )
    stock = models.IntegerField(default=0)
    category = models.CharField(max_length=3, choices=CATEGORY_CHOICES)
    image = models.ImageField(upload_to='medicines/', null=True, blank=True)
    barcode = models.ImageField(upload_to='barcodes/', blank=True)
    barcode_number = models.CharField(max_length=13, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    reorder_level = models.IntegerField(default=10, help_text="Minimum stock level before reorder")
    strips_per_box = models.PositiveIntegerField(
        default=1,
        help_text="Number of strips per box"
    )
    can_sell_strips = models.BooleanField(
        default=True,
        help_text="Allow selling individual strips"
    )
    strip_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Price per strip (optional - if not set, will be calculated from box price)"
    )

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('pharmacy:medicine_detail', kwargs={'pk': self.pk})

    def save(self, *args, **kwargs):
        if not self.barcode_number:
            import random
            while True:
                number = ''.join(random.choices('0123456789', k=12))
                if not Medicine.objects.filter(barcode_number=number).exists():
                    self.barcode_number = number
                    break
        else:
            self.barcode_number = self.barcode_number.zfill(12)

        if not self.barcode:
            try:
                EAN = barcode.get_barcode_class('ean13')
                ean = EAN(self.barcode_number)
                buffer = BytesIO()
                ean.write(buffer, writer=ImageWriter())
                self.barcode.save(
                    f'barcode_{self.barcode_number}.png',
                    File(buffer),
                    save=False
                )
            except Exception as e:
                print(f"Error generating barcode: {e}")
                pass

        super().save(*args, **kwargs)

    def get_strip_price(self):
        """Get strip price - either custom or calculated from box price"""
        if self.strip_price:
            return self.strip_price
        return self.price / self.strips_per_box if self.strips_per_box > 0 else self.price

    def get_profit_per_unit(self):
        """Calculate profit per unit (box)"""
        return self.price - self.purchase_price

    def get_profit_margin_percentage(self):
        """Calculate profit margin as a percentage"""
        if self.purchase_price > 0:
            return ((self.price - self.purchase_price) / self.purchase_price) * 100
        return 0

    def get_strip_profit(self):
        """Calculate profit per strip"""
        if self.can_sell_strips:
            strip_purchase_price = self.purchase_price / self.strips_per_box if self.strips_per_box > 0 else 0
            return self.get_strip_price() - strip_purchase_price
        return 0

    def calculate_available_stock(self):
        """Calculate total available (non-expired) stock"""
        from django.utils import timezone
        from django.db.models import Sum
        
        today = timezone.now().date()
        return self.stock_entries.filter(
            expiration_date__gte=today
        ).aggregate(
            total=Sum('quantity')
        )['total'] or 0
    
    def update_stock(self, commit=True):
        """Update stock based on non-expired stock entries"""
        available = self.calculate_available_stock()
        if self.stock != available:
            self.stock = available
            if commit:
                self.save(update_fields=['stock'])
        return self.stock

    def validate_stock(self):
        """Validate that stock matches sum of valid stock entries"""
        available = self.calculate_available_stock()
        if self.stock != available:
            return False, f"Stock mismatch: recorded={self.stock}, calculated={available}"
        return True, "Stock valid"

class StockEntry(models.Model):
    medicine = models.ForeignKey(Medicine, on_delete=models.CASCADE, related_name='stock_entries')
    quantity = models.IntegerField()
    expiration_date = models.DateField(null=False, blank=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['expiration_date']

    def __str__(self):
        return f"{self.medicine.name} - {self.quantity} units (Expires: {self.expiration_date})"

    def clean(self):
        if self.expiration_date and self.expiration_date < timezone.now().date():
            raise ValidationError('Expiration date cannot be in the past')

class SaleItem(models.Model):
    UNIT_CHOICES = [
        ('BOX', 'Box'),
        ('STRIP', 'Strip'),
    ]

    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    medicine = models.ForeignKey(Medicine, on_delete=models.PROTECT)
    quantity = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    expiry_date = models.DateField()
    unit_type = models.CharField(
        max_length=5,
        choices=UNIT_CHOICES,
        default='BOX'
    )

    @property
    def discounted_price(self):
        """Calculate price after customer discount"""
        if self.sale.customer:
            if self.sale.customer.customer_type == 'FAMILY':
                return self.medicine.purchase_price * Decimal('1.10')  # 10% profit margin for family
            else:
                discount = self.sale.customer.discount_percentage / 100
                return self.price * (1 - discount)
        return self.price

    @property
    def subtotal(self):
        return self.discounted_price * self.quantity

    @property 
    def profit(self):
        """Calculate profit for this sale item"""
        if self.unit_type == 'STRIP':
            unit_profit = self.medicine.get_strip_profit()
        else:  # BOX
            unit_profit = self.medicine.get_profit_per_unit()
        return unit_profit * self.quantity
    
    @property
    def profit_margin_percentage(self):
        """Calculate profit margin percentage for this sale"""
        if self.subtotal > 0:
            return (self.profit / self.subtotal) * 100
        return 0

class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('ADMIN', 'Administrator'),
        ('PHARMACIST', 'Pharmacist'),
        ('CASHIER', 'Cashier'),
        ('STOCK_MANAGER', 'Stock Manager'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    profile_pic = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    bio = models.TextField(blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

    def get_profile_pic_url(self):
        if self.profile_pic:
            return self.profile_pic.url
        return '/static/pharmacy/images/default_profile.png'

class Supplier(models.Model):
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    address = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class Purchase(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('RECEIVED', 'Received'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    date = models.DateTimeField(auto_now_add=True)
    invoice_number = models.CharField(max_length=50, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.PROTECT)
    
    def __str__(self):
        return f"PO-{self.invoice_number} ({self.supplier.name})"

    def calculate_total(self):
        total = sum(item.subtotal for item in self.items.all())
        self.total_amount = total
        self.save()
        return total

class PurchaseItem(models.Model):
    purchase = models.ForeignKey(Purchase, related_name='items', on_delete=models.CASCADE)
    medicine = models.ForeignKey(Medicine, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    expiry_date = models.DateField()
    
    @property
    def subtotal(self):
        return self.quantity * self.price

class Prescription(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('DISPENSED', 'Dispensed'),
        ('CANCELLED', 'Cancelled'),
        ('REFILL_REQUESTED', 'Refill Requested'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    doctor_name = models.CharField(max_length=100)
    doctor_contact = models.CharField(max_length=20, blank=True)
    prescription_date = models.DateField()
    expiry_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    notes = models.TextField(blank=True)
    image = models.ImageField(upload_to='prescriptions/', blank=True, null=True)
    refills_allowed = models.PositiveIntegerField(default=0)
    refills_remaining = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.PROTECT)
    sale = models.OneToOneField(Sale, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"Prescription #{self.id} - {self.customer.name}"

    def save(self, *args, **kwargs):
        if not self.pk:  # New prescription
            self.refills_remaining = self.refills_allowed
        super().save(*args, **kwargs)

class PrescriptionItem(models.Model):
    prescription = models.ForeignKey(Prescription, related_name='items', on_delete=models.CASCADE)
    medicine = models.ForeignKey(Medicine, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    dosage = models.CharField(max_length=100)  # e.g., "1 tablet twice daily"
    duration = models.CharField(max_length=100)  # e.g., "7 days"
    instructions = models.TextField(blank=True)

    def __str__(self):
        return f"{self.medicine.name} - {self.dosage}"

class SearchHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    query = models.CharField(max_length=100)
    found_results = models.BooleanField()
    timestamp = models.DateTimeField(auto_now_add=True)
    clicked_result = models.BooleanField(default=False)  # Track if user clicked any result
    suggested_query = models.CharField(max_length=100, blank=True, null=True)  # For "Did you mean"

    class Meta:
        ordering = ['-timestamp']
        verbose_name_plural = "Search histories"

    def __str__(self):
        return f"{self.user.username} - {self.query}"

class ProfitAnalytics(models.Model):
    date = models.DateField(auto_now_add=True)
    total_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_profit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    profit_margin = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # percentage
    number_of_sales = models.IntegerField(default=0)
    average_profit_per_sale = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    most_profitable_category = models.CharField(max_length=50, blank=True)
    most_profitable_medicine = models.ForeignKey(
        Medicine, 
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='top_profit_days'
    )

    class Meta:
        ordering = ['-date']
        verbose_name_plural = "Profit analytics"

    @classmethod
    def generate_daily_report(cls, date=None):
        """Generate or update profit analytics for a specific date"""
        from django.utils import timezone
        from django.db.models import Sum, Count
        
        if date is None:
            date = timezone.now().date()
            
        sales = Sale.objects.filter(
            created_at__date=date,
            is_completed=True
        )
        
        # Calculate daily totals
        daily_totals = sales.aggregate(
            total_sales=Sum('total_amount'),
            number_of_sales=Count('id')
        )
        
        total_sales = daily_totals['total_sales'] or 0
        number_of_sales = daily_totals['number_of_sales']
        
        # Calculate total cost and profit
        total_cost = 0
        total_profit = 0
        category_profits = {}
        medicine_profits = {}
        
        for sale in sales:
            for item in sale.items.all():
                if item.unit_type == 'STRIP':
                    cost = item.medicine.purchase_price / item.medicine.strips_per_box * item.quantity
                else:
                    cost = item.medicine.purchase_price * item.quantity
                    
                profit = item.profit
                total_cost += cost
                total_profit += profit
                
                # Track category profits
                category = item.medicine.get_category_display()
                category_profits[category] = category_profits.get(category, 0) + profit
                
                # Track individual medicine profits
                medicine_id = item.medicine.id
                medicine_profits[medicine_id] = medicine_profits.get(medicine_id, 0) + profit
        
        # Find most profitable category and medicine
        most_profitable_category = max(category_profits.items(), key=lambda x: x[1])[0] if category_profits else ''
        most_profitable_medicine_id = max(medicine_profits.items(), key=lambda x: x[1])[0] if medicine_profits else None
        
        # Calculate averages
        average_profit = total_profit / number_of_sales if number_of_sales > 0 else 0
        profit_margin = (total_profit / total_sales * 100) if total_sales > 0 else 0
        
        # Create or update analytics record
        analytics, created = cls.objects.update_or_create(
            date=date,
            defaults={
                'total_sales': total_sales,
                'total_cost': total_cost,
                'total_profit': total_profit,
                'profit_margin': profit_margin,
                'number_of_sales': number_of_sales,
                'average_profit_per_sale': average_profit,
                'most_profitable_category': most_profitable_category,
                'most_profitable_medicine_id': most_profitable_medicine_id if most_profitable_medicine_id else None
            }
        )
        
        return analytics

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(
            user=instance,
            role='CASHIER'  # Default role, you can change this
        )

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    try:
        instance.userprofile.save()
    except UserProfile.DoesNotExist:
        UserProfile.objects.create(
            user=instance,
            role='CASHIER'
        )