from django.db import models
from django.urls import reverse
import barcode
from barcode.writer import ImageWriter
from io import BytesIO
from django.core.files import File
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth.models import User

class Customer(models.Model):
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, unique=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    points = models.IntegerField(default=0)
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
    stock = models.IntegerField(default=0)
    category = models.CharField(max_length=3, choices=CATEGORY_CHOICES)
    image = models.ImageField(upload_to='medicines/', null=True, blank=True)
    barcode = models.ImageField(upload_to='barcodes/', blank=True)
    barcode_number = models.CharField(max_length=13, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    reorder_level = models.IntegerField(default=10, help_text="Minimum stock level before reorder")

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
    sale = models.ForeignKey(Sale, related_name='items', on_delete=models.CASCADE)
    medicine = models.ForeignKey(Medicine, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    expiry_date = models.DateField()

    @property
    def subtotal(self):
        return self.quantity * self.price

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
    
    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

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
