from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.conf import settings
from django.urls import reverse
import os
import subprocess
import logging

# Set up logging
logger = logging.getLogger(__name__)

from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import F, Sum, Count, Avg, Max, Q, Case, When, DecimalField
from django.db.models.functions import ExtractMonth, TruncDate, TruncMonth
from django.utils import timezone
from django.db import transaction
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST, require_http_methods
from .models import Medicine, StockEntry, Sale, SaleItem, Supplier, Purchase, Customer, Prescription, SearchHistory, ProfitAnalytics
from .forms import (
    MedicineForm, SupplierForm, PurchaseForm, PurchaseItemForm, 
    CustomerForm, CustomerSearchForm, PrescriptionForm, PrescriptionItemFormSet,
    CustomUserCreationForm, UserProfileForm, ChangePasswordForm
)
from django.contrib.auth.forms import UserCreationForm
from .mixins import RoleRequiredMixin
import csv
from datetime import datetime, timedelta
from django.core.exceptions import ValidationError
import requests
from decimal import Decimal
import statistics

# List all medicines
class MedicineListView(ListView):
    model = Medicine
    template_name = 'pharmacy/medicine_list.html'
    context_object_name = 'medicines'
    paginate_by = 12

# Show medicine details
class MedicineDetailView(DetailView):
    model = Medicine
    template_name = 'pharmacy/medicine_detail.html'

# Add new medicine
class MedicineCreateView(LoginRequiredMixin, CreateView):
    model = Medicine
    template_name = 'pharmacy/medicine_form.html'
    form_class = MedicineForm
    success_url = reverse_lazy('pharmacy:medicine_list')

    def get_initial(self):
        initial = super().get_initial()
        # Pre-fill barcode from URL parameter if it exists
        barcode = self.request.GET.get('barcode')
        if barcode:
            initial['barcode_number'] = barcode
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'Medicine added successfully! Please add initial stock.')
        return redirect('pharmacy:update_stock', barcode=self.object.barcode_number)

# Edit medicine
class MedicineUpdateView(LoginRequiredMixin, UpdateView):
    model = Medicine
    template_name = 'pharmacy/medicine_form.html'
    form_class = MedicineForm
    success_url = reverse_lazy('pharmacy:medicine_list')

    def form_valid(self, form):
        messages.success(self.request, 'Medicine updated successfully!')
        return super().form_valid(form)

# Delete medicine
class MedicineDeleteView(LoginRequiredMixin, DeleteView):
    model = Medicine
    template_name = 'pharmacy/medicine_confirm_delete.html'
    success_url = reverse_lazy('pharmacy:medicine_list')

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Medicine deleted successfully!')
        return super().delete(request, *args, **kwargs)

def home(request):
    return render(request, 'pharmacy/home.html', {
        'title': 'Welcome to Elersraa Pharmacy',
    })

# Add this class to your existing views
class SignUpView(CreateView):
    form_class = CustomUserCreationForm
    success_url = reverse_lazy('login')
    template_name = 'pharmacy/signup.html'

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'Account created successfully! Please login.')
        return response

# Add these new views
@login_required
def stock_management(request):
    return render(request, 'pharmacy/stock_management.html')

@require_POST
@login_required
def update_stock(request):
    from django.db.models import Sum, F

    # Add debug prints
    print("Received POST request")
    print("POST data:", request.POST)
    
    try:
        barcode = request.POST.get('barcode')
        quantity = int(request.POST.get('quantity', 1))
        expiration_date = request.POST.get('expiration_date')
        
        print(f"Processing: barcode={barcode}, quantity={quantity}, expiration_date={expiration_date}")
        
        if not barcode:
            return JsonResponse({
                'success': False,
                'error': 'Barcode is required'
            }, status=400)

        try:
            medicine = Medicine.objects.get(barcode_number=barcode)
            print(f"Found medicine: {medicine.name}")
            
            # Create stock entry
            stock_entry = StockEntry.objects.create(
                medicine=medicine,
                quantity=quantity,
                expiration_date=expiration_date
            )
            print(f"Created stock entry: {stock_entry}")
            
            # Update stock based on non-expired entries
            new_stock = medicine.update_stock()
            print(f"Updated stock to: {new_stock}")
            
            return JsonResponse({
                'success': True,
                'medicine': {
                    'name': medicine.name,
                    'new_stock': medicine.stock,
                    'price': str(medicine.price),
                    'expiration_date': expiration_date
                }
            })
        except Medicine.DoesNotExist:
            print(f"Medicine not found for barcode: {barcode}")
            return JsonResponse({
                'success': False,
                'error': 'Medicine not found',
                'redirect_url': reverse('pharmacy:medicine_add') + f'?barcode={barcode}'
            }, status=404)
            
    except Exception as e:
        print(f"Error occurred: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
def stock_view(request):
    today = timezone.now().date()
    
    # Get all medicines with their stock entries
    medicines = Medicine.objects.prefetch_related(
        'stock_entries'
    ).all()
    
    # Prepare stock data
    stock_data = []
    for medicine in medicines:
        # Get all stock entries for this medicine
        stock_entries = medicine.stock_entries.all()
        
        # Ensure stock is up to date
        medicine.update_stock()
        
        # Calculate expired and near-expiry stock
        expired_stock = stock_entries.filter(
            expiration_date__lt=today
        ).aggregate(
            total=Sum('quantity')
        )['total'] or 0
        
        near_expiry_stock = stock_entries.filter(
            expiration_date__range=[today, today + timezone.timedelta(days=30)]
        ).aggregate(
            total=Sum('quantity')
        )['total'] or 0
        
        stock_data.append({
            'medicine': medicine,
            'total_stock': medicine.stock,
            'expired_stock': expired_stock,
            'near_expiry_stock': near_expiry_stock,
            'stock_entries': stock_entries,
        })
    
    context = {
        'stock_data': stock_data,
        'today': today,
    }
    return render(request, 'pharmacy/stock_view.html', context)

@login_required
def update_existing_stock(request, barcode):
    medicine = get_object_or_404(Medicine, barcode_number=barcode)
    today = timezone.now().date()
    
    if request.method == 'POST':
        quantity = int(request.POST.get('quantity', 0))
        expiration_date = request.POST.get('expiration_date')
        
        if quantity and expiration_date:
            try:
                exp_date = timezone.datetime.strptime(expiration_date, '%Y-%m-%d').date()
                
                # Validate expiration date
                if exp_date <= today:
                    messages.error(request, 'Expiration date must be in the future')
                    return redirect('pharmacy:update_existing_stock', barcode=barcode)
                
                # Create new stock entry
                StockEntry.objects.create(
                    medicine=medicine,
                    quantity=quantity,
                    expiration_date=exp_date
                )
                
                # Update stock based on non-expired entries
                new_stock = medicine.update_stock()
                
                messages.success(request, f'Updated stock for {medicine.name}. New total: {new_stock}')
                return redirect('pharmacy:stock_view')
                
            except ValueError:
                messages.error(request, 'Invalid expiration date format')
    
    context = {
        'medicine': medicine,
        'stock_entries': medicine.stock_entries.all().order_by('expiration_date'),
        'today': today,
    }
    return render(request, 'pharmacy/update_existing_stock.html', context)

@login_required
def check_barcode(request, barcode=None):
    # Get barcode from query parameters if not in URL
    barcode = barcode or request.GET.get('barcode')
    
    if not barcode:
        messages.error(request, 'Please provide a barcode')
        return redirect('pharmacy:stock_scan')
        
    try:
        medicine = Medicine.objects.filter(barcode_number=barcode).first()
        
        if medicine:
            # Medicine exists - redirect to update stock
            return redirect('pharmacy:update_stock', barcode=barcode)
        else:
            # Medicine doesn't exist - redirect to add new
            return redirect(f"{reverse('pharmacy:medicine_add')}?barcode={barcode}")
            
    except Exception as e:
        messages.error(request, f'Error: {str(e)}')
        return redirect('pharmacy:stock_scan')

@login_required
def stock_scan(request):
    return render(request, 'pharmacy/stock_scan.html')

@login_required
def update_stock(request, barcode):
    medicine = get_object_or_404(Medicine, barcode_number=barcode)
    today = timezone.now().date()
    
    if request.method == 'POST':
        quantities = request.POST.getlist('quantity[]')
        expiration_dates = request.POST.getlist('expiration_date[]')
        
        if not all(expiration_dates):
            messages.error(request, 'Expiration date is required for all entries')
            return redirect('pharmacy:update_stock', barcode=barcode)

        if quantities and expiration_dates and len(quantities) == len(expiration_dates):
            total_added = 0
            
            # Validate and create stock entries
            for quantity, expiration_date in zip(quantities, expiration_dates):
                try:
                    quantity = int(quantity)
                    exp_date = timezone.datetime.strptime(expiration_date, '%Y-%m-%d').date()
                    
                    # Validate expiration date
                    if exp_date <= today:
                        messages.error(request, 'Expiration date must be in the future')
                        return redirect('pharmacy:update_stock', barcode=barcode)
                    
                    if quantity > 0:
                        StockEntry.objects.create(
                            medicine=medicine,
                            quantity=quantity,
                            expiration_date=exp_date
                        )
                        total_added += quantity
                except (ValueError, TypeError):
                    messages.error(request, 'Invalid quantity or expiration date format')
                    return redirect('pharmacy:update_stock', barcode=barcode)
            
            # Update stock based on non-expired entries
            new_stock = medicine.update_stock()
            
            messages.success(
                request, 
                f'Added {total_added} units to {medicine.name} with different expiration dates. New total: {new_stock}'
            )
            return redirect('pharmacy:medicine_list')
        else:
            messages.error(request, 'Please provide valid quantities and expiration dates for all entries')
    
    context = {
        'medicine': medicine,
        'stock_entries': medicine.stock_entries.all().order_by('-created_at'),
        'total_stock': medicine.stock,
        'today': today,
    }
    return render(request, 'pharmacy/update_stock.html', context)

@login_required
def pos_view(request):
    """View for the Point of Sale (POS) system"""
    if request.method == 'POST':
        if request.POST.get('action') == 'cancel':
            # Clear the cart and customer
            request.session['cart'] = []
            request.session['selected_customer_id'] = None
            request.session.modified = True
            messages.success(request, 'Sale cancelled successfully')
            return redirect('pharmacy:pos')
        elif request.POST.get('customer_id') is not None:
            # AJAX customer selection
            customer_id = request.POST.get('customer_id')
            if customer_id:
                try:
                    # Validate customer exists
                    customer = Customer.objects.get(id=customer_id)
                    request.session['selected_customer_id'] = customer_id
                    
                    # Update cart prices with new customer
                    cart = request.session.get('cart', [])
                    updated_cart = []
                    for item in cart:
                        medicine = Medicine.objects.get(id=item['medicine_id'])
                        original_price = medicine.get_strip_price() if item['unit_type'] == 'STRIP' else medicine.price
                        
                        # Calculate discounted price based on customer type
                        if customer.customer_type == 'FAMILY':
                            # Calculate minimum profitable price
                            discounted_price = medicine.purchase_price * Decimal('1.10')  # Cost + 10%
                            if item['unit_type'] == 'STRIP':
                                discounted_price = discounted_price / medicine.strips_per_box
                        else:
                            discount = customer.discount_percentage / 100
                            discounted_price = original_price * (1 - discount)
                            # Ensure price doesn't go below cost + 10%
                            min_price = medicine.purchase_price * Decimal('1.10')
                            if item['unit_type'] == 'STRIP':
                                min_price = min_price / medicine.strips_per_box
                            if discounted_price < min_price:
                                discounted_price = min_price
                        
                        item['original_price'] = float(original_price)
                        item['discounted_price'] = float(discounted_price)
                        item['total'] = float(discounted_price * item['quantity'])
                        updated_cart.append(item)
                    
                    request.session['cart'] = updated_cart
                    request.session.modified = True
                    
                except Customer.DoesNotExist:
                    pass
            else:
                # Clear customer selection
                request.session['selected_customer_id'] = None
                request.session.modified = True
            return JsonResponse({'status': 'ok'})
    
    # Get cart from session
    cart = request.session.get('cart', [])
    
    # Calculate totals
    original_total = sum(float(item['original_price'] * item['quantity']) for item in cart)
    cart_total = sum(float(item['total']) for item in cart)
    
    # Get customer from session
    customer_id = request.session.get('selected_customer_id')
    customer = None
    if customer_id:
        try:
            customer = Customer.objects.get(id=customer_id)
        except Customer.DoesNotExist:
            request.session['selected_customer_id'] = None
            
    context = {
        'cart': cart,
        'original_total': original_total,
        'cart_total': cart_total,
        'selected_customer': customer
    }
    
    return render(request, 'pharmacy/pos.html', context)

@login_required
def pos_remove_item(request, item_id):
    if request.method == 'POST':
        cart = request.session.get('cart', [])
        try:
            if 0 <= item_id < len(cart):
                cart.pop(item_id)
                request.session['cart'] = cart
                request.session.modified = True
                messages.success(request, 'Item removed from cart')
            else:
                messages.error(request, 'Invalid item')
        except Exception as e:
            messages.error(request, f'Error removing item: {str(e)}')
    return redirect('pharmacy:pos')

@login_required
@require_POST
def pos_complete_sale(request):
    """Complete the sale and clear the cart"""
    try:
        cart = request.session.get('cart', [])
        if not cart:
            messages.error(request, 'Cart is empty')
            return redirect('pharmacy:pos')

        payment_method = request.POST.get('payment_method', 'CASH')
        customer_id = request.POST.get('customer_id')
        customer = Customer.objects.get(id=customer_id) if customer_id else None

        # Calculate total with discounts
        total_amount = sum(float(item['total']) for item in cart)

        # Create sale record
        sale = Sale.objects.create(
            customer=customer,
            payment_method=payment_method,
            total_amount=total_amount,
            user=request.user,
            is_completed=True
        )

        # Create sale items and update stock
        completed_items = []
        for item in cart:
            medicine = Medicine.objects.get(id=item['medicine_id'])
            
            # Calculate stock reduction
            if item['unit_type'] == 'STRIP':
                stock_reduction = item['quantity'] / medicine.strips_per_box
            else:
                stock_reduction = item['quantity']
            
            # Update stock
            medicine.stock = F('stock') - stock_reduction
            medicine.save()
            
            # Get earliest expiring stock entry
            stock_entry = StockEntry.objects.filter(
                medicine=medicine,
                quantity__gt=0,
                expiration_date__gt=timezone.now().date()
            ).order_by('expiration_date').first()
            
            if not stock_entry:
                raise ValidationError(f'No valid stock entry found for {medicine.name}')
            
            # Create sale item with original and discounted prices
            sale_item = SaleItem.objects.create(
                sale=sale,
                medicine=medicine,
                quantity=item['quantity'],
                unit_type=item['unit_type'],
                price=item['discounted_price'],  # Store the discounted price
                expiry_date=stock_entry.expiration_date
            )
            completed_items.append(sale_item)

        # Add loyalty points if customer exists
        if customer:
            points_added = customer.add_points(total_amount)
            messages.success(
                request, 
                f'Added {points_added} points to {customer.name}\'s account!'
            )

        # Clear the cart
        request.session['cart'] = []
        request.session.modified = True
        
        # Add receipt data to session for printing
        request.session['completed_sale'] = {
            'id': sale.id,
            'customer': customer.name if customer else None,
            'items': [
                {
                    'name': item.medicine.name,
                    'quantity': item.quantity,
                    'unit_type': item.get_unit_type_display(),
                    'price': float(item.price),
                    'total': float(item.subtotal)
                }
                for item in completed_items
            ],
            'total': float(total_amount),
            'discounts_applied': bool(customer and (customer.customer_type == 'FAMILY' or customer.discount_percentage > 0)),
            'customer_type': customer.get_customer_type_display() if customer else None,
            'discount_info': (
                'سعر التكلفة + 10% فقط' if customer and customer.customer_type == 'FAMILY'
                else f'خصم {customer.discount_percentage}%' if customer and customer.discount_percentage > 0
                else None
            )
        }
        
        messages.success(request, f'Sale completed successfully. Sale ID: {sale.id}')
        
    except ValidationError as e:
        messages.error(request, str(e))
    except Exception as e:
        messages.error(request, f'Error completing sale: {str(e)}')
    
    return redirect('pharmacy:pos')

@login_required
def sales_history(request):
    # Get completed sales
    sales = Sale.objects.filter(
        is_completed=True
    ).order_by('-created_at')
    
    # Calculate totals
    total_sales = sales.count()
    total_revenue = sum(sale.total_amount for sale in sales)
    
    context = {
        'sales': sales,
        'total_sales': total_sales,
        'total_revenue': total_revenue,
    }
    return render(request, 'pharmacy/sales_history.html', context)

@login_required
def sale_detail(request, sale_id):
    sale = get_object_or_404(Sale, id=sale_id, is_completed=True)
    
    context = {
        'sale': sale,
        'items': sale.items.all(),
        'total': sale.total_amount,
    }
    return render(request, 'pharmacy/sale_detail.html', context)

@login_required
def dashboard(request):
    today = timezone.now().date()
    start_of_month = today.replace(day=1)
    
    # Sales Analytics
    daily_sales = Sale.objects.filter(
        created_at__date=today,
        is_completed=True
    )
    monthly_sales = Sale.objects.filter(
        created_at__date__gte=start_of_month,
        created_at__date__lte=today,
        is_completed=True
    )
    
    # Stock Analytics
    low_stock_threshold = 10  # We can make this configurable later
    low_stock = Medicine.objects.filter(stock__lte=low_stock_threshold)
    
    expiring_soon = StockEntry.objects.filter(
        expiration_date__range=[today, today + timezone.timedelta(days=30)],
        quantity__gt=0
    ).select_related('medicine')
    
    # Most sold medicines
    top_medicines = Medicine.objects.annotate(
        total_sold=Sum('saleitem__quantity')
    ).filter(total_sold__gt=0).order_by('-total_sold')[:5]
    
    context = {
        'today': today,
        'daily_sales_count': daily_sales.count(),
        'daily_revenue': daily_sales.aggregate(total=Sum('total_amount'))['total'] or 0,
        'monthly_sales_count': monthly_sales.count(),
        'monthly_revenue': monthly_sales.aggregate(total=Sum('total_amount'))['total'] or 0,
        'low_stock_items': low_stock,
        'expiring_soon': expiring_soon,
        'top_medicines': top_medicines,
        'total_medicines': Medicine.objects.count(),
        'out_of_stock': Medicine.objects.filter(stock=0).count(),
    }
    return render(request, 'pharmacy/dashboard.html', context)

class StockManagementView(LoginRequiredMixin, RoleRequiredMixin, View):
    allowed_roles = ['ADMIN', 'STOCK_MANAGER']
    template_name = 'pharmacy/stock_management.html'

    def get(self, request):
        # Get low stock items
        low_stock_threshold = 10  # We can make this configurable later
        low_stock = Medicine.objects.filter(stock__lte=low_stock_threshold)
        
        context = {
            'low_stock': low_stock,
        }
        return render(request, self.template_name, context)

class SupplierListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    model = Supplier
    template_name = 'pharmacy/supplier_list.html'
    context_object_name = 'suppliers'
    allowed_roles = ['ADMIN', 'STOCK_MANAGER']

class SupplierCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    model = Supplier
    form_class = SupplierForm
    template_name = 'pharmacy/supplier_form.html'
    success_url = reverse_lazy('pharmacy:supplier_list')
    allowed_roles = ['ADMIN', 'STOCK_MANAGER']

    def form_valid(self, form):
        messages.success(self.request, 'Supplier added successfully!')
        return super().form_valid(form)

class PurchaseListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    model = Purchase
    template_name = 'pharmacy/purchase_list.html'
    context_object_name = 'purchases'
    allowed_roles = ['ADMIN', 'STOCK_MANAGER']

@login_required
def purchase_create(request):
    if request.method == 'POST':
        form = PurchaseForm(request.POST)
        if form.is_valid():
            purchase = form.save(commit=False)
            purchase.created_by = request.user
            purchase.save()
            return redirect('pharmacy:purchase_detail', pk=purchase.pk)
    else:
        form = PurchaseForm()
    
    return render(request, 'pharmacy/purchase_form.html', {'form': form})

@login_required
def purchase_detail(request, pk):
    purchase = get_object_or_404(Purchase, pk=pk)
    if request.method == 'POST':
        form = PurchaseItemForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.purchase = purchase
            item.save()
            purchase.calculate_total()
            messages.success(request, 'Item added to purchase order')
            return redirect('pharmacy:purchase_detail', pk=pk)
    else:
        form = PurchaseItemForm()
    
    context = {
        'purchase': purchase,
        'items': purchase.items.all(),
        'form': form,
    }
    return render(request, 'pharmacy/purchase_detail.html', context)

@login_required
def receive_purchase(request, pk):
    purchase = get_object_or_404(Purchase, pk=pk)
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Update stock for each item
                for item in purchase.items.all():
                    StockEntry.objects.create(
                        medicine=item.medicine,
                        quantity=item.quantity,
                        expiration_date=item.expiry_date
                    )
                    
                    # Update medicine stock
                    total_stock = StockEntry.objects.filter(
                        medicine=item.medicine
                    ).aggregate(
                        total=Sum('quantity')
                    )['total'] or 0
                    
                    item.medicine.stock = total_stock
                    item.medicine.save()
                
                # Mark purchase as received
                purchase.status = 'RECEIVED'
                purchase.save()
                
                messages.success(request, 'Purchase order received successfully')
                return redirect('pharmacy:purchase_list')
                
        except Exception as e:
            messages.error(request, f'Error receiving purchase: {str(e)}')
            
    return redirect('pharmacy:purchase_detail', pk=pk)

class SupplierDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    model = Supplier
    template_name = 'pharmacy/supplier_detail.html'
    context_object_name = 'supplier'
    allowed_roles = ['ADMIN', 'STOCK_MANAGER']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['purchases'] = self.object.purchase_set.all().order_by('-date')
        return context

class SupplierUpdateView(LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    model = Supplier
    form_class = SupplierForm
    template_name = 'pharmacy/supplier_form.html'
    success_url = reverse_lazy('pharmacy:supplier_list')
    allowed_roles = ['ADMIN', 'STOCK_MANAGER']

    def form_valid(self, form):
        messages.success(self.request, 'Supplier updated successfully!')
        return super().form_valid(form)

class PurchaseDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    model = Purchase
    template_name = 'pharmacy/purchase_detail.html'
    context_object_name = 'purchase'
    allowed_roles = ['ADMIN', 'STOCK_MANAGER']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['items'] = self.object.items.all()
        if self.object.status == 'PENDING':
            context['form'] = PurchaseItemForm()
        return context

class PurchaseCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    model = Purchase
    form_class = PurchaseForm
    template_name = 'pharmacy/purchase_form.html'
    success_url = reverse_lazy('pharmacy:purchase_list')
    allowed_roles = ['ADMIN', 'STOCK_MANAGER']

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, 'Purchase order created successfully!')
        return super().form_valid(form)

@login_required
def report_dashboard(request):
    return render(request, 'pharmacy/reports/dashboard.html')

@login_required
def sales_report(request):
    """Generate sales report"""
    # Get date range from request
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    # Base queryset
    sales = Sale.objects.filter(is_completed=True)
    
    # Apply date filters if provided
    if start_date:
        sales = sales.filter(created_at__date__gte=start_date)
    if end_date:
        sales = sales.filter(created_at__date__lte=end_date)
    
    # Calculate statistics
    total_sales = sales.count()
    total_revenue = sales.aggregate(total=Sum('total_amount'))['total'] or 0
    avg_sale_value = total_revenue / total_sales if total_sales > 0 else 0
    
    # Group by payment method
    payment_methods = sales.values('payment_method').annotate(
        count=Count('id'),
        total=Sum('total_amount')
    )
    
    # Group by day
    daily_sales = sales.annotate(
        day=TruncDate('created_at')
    ).values('day').annotate(
        count=Count('id'),
        total=Sum('total_amount')
    ).order_by('day')
    
    # Top selling products
    top_products = SaleItem.objects.filter(
        sale__in=sales
    ).values(
        'medicine__name'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_revenue=Sum(F('quantity') * F('price'))
    ).order_by('-total_quantity')[:10]
    
    context = {
        'total_sales': total_sales,
        'total_revenue': total_revenue,
        'avg_sale_value': avg_sale_value,
        'payment_methods': payment_methods,
        'daily_sales': daily_sales,
        'top_products': top_products,
        'start_date': start_date,
        'end_date': end_date
    }
    
    return render(request, 'pharmacy/reports/sales.html', context)

@login_required
def inventory_report(request):
    medicines = Medicine.objects.all()
    
    # Calculate inventory value using Decimal
    total_value = sum(Decimal(str(medicine.stock)) * medicine.price for medicine in medicines)
    
    # Low stock items
    low_stock = medicines.filter(stock__lte=F('reorder_level'))
    
    # Stock movement
    stock_movement = StockEntry.objects.values(
        'medicine__name'
    ).annotate(
        total_in=Sum('quantity')
    ).order_by('-total_in')
    
    context = {
        'medicines': medicines,
        'total_value': total_value,
        'low_stock': low_stock,
        'stock_movement': stock_movement,
    }
    
    return render(request, 'pharmacy/reports/inventory_report.html', context)

@login_required
def expiry_report(request):
    today = timezone.now().date()
    
    # Get expiring items grouped by timeframe
    expiring_30 = StockEntry.objects.filter(
        expiration_date__range=[today, today + timezone.timedelta(days=30)]
    ).select_related('medicine')
    
    expiring_60 = StockEntry.objects.filter(
        expiration_date__range=[
            today + timezone.timedelta(days=31),
            today + timezone.timedelta(days=60)
        ]
    ).select_related('medicine')
    
    expired = StockEntry.objects.filter(
        expiration_date__lt=today
    ).select_related('medicine')
    
    context = {
        'expiring_30': expiring_30,
        'expiring_60': expiring_60,
        'expired': expired,
    }
    return render(request, 'pharmacy/reports/expiry_report.html', context)

@login_required
def financial_report(request):
    try:
        year = int(request.GET.get('year', timezone.now().year))
    except (ValueError, TypeError):
        year = timezone.now().year
        
    try:
        month = int(request.GET.get('month')) if request.GET.get('month') else None
    except (ValueError, TypeError):
        month = None
    
    sales = Sale.objects.filter(
        is_completed=True,
        created_at__year=year
    )
    
    if month:
        sales = sales.filter(created_at__month=month)
    
    # Calculate total sales count
    total_sales = sales.count()
    
    # Monthly revenue
    monthly_revenue = sales.annotate(
        month=ExtractMonth('created_at')
    ).values('month').annotate(
        total=Sum('total_amount')
    ).order_by('month')
    
    # Payment method distribution
    payment_distribution = sales.values(
        'payment_method'
    ).annotate(
        count=Count('id'),
        total=Sum('total_amount')
    )
    
    # Get list of years for dropdown (current year and 4 years back)
    current_year = timezone.now().year
    years = range(current_year - 4, current_year + 1)
    
    context = {
        'sales': sales,
        'monthly_revenue': monthly_revenue,
        'payment_distribution': payment_distribution,
        'year': year,
        'month': month,
        'total_sales': total_sales,
        'years': years,  # Add this to context
    }
    return render(request, 'pharmacy/reports/financial_report.html', context)

@login_required
def export_sales_report(request):
    # Create the HttpResponse object with CSV header
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="sales_report_{datetime.now().strftime("%Y%m%d")}.csv"'
    
    # Get filter parameters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    # Get sales data
    sales = Sale.objects.filter(is_completed=True)
    if start_date:
        sales = sales.filter(created_at__date__gte=start_date)
    if end_date:
        sales = sales.filter(created_at__date__lte=end_date)
    
    # Create CSV writer
    writer = csv.writer(response)
    
    # Write headers
    writer.writerow([
        'Sale ID', 'Date', 'Customer', 'Payment Method', 
        'Items Count', 'Total Amount', 'Cashier'
    ])
    
    # Write data
    for sale in sales:
        writer.writerow([
            sale.id,
            sale.created_at.strftime('%Y-%m-%d %H:%M'),
            'Walk-in Customer',  # Can be updated if you add customer info
            sale.get_payment_method_display(),
            sale.items.count(),
            sale.total_amount,
            sale.user.username
        ])
    
    return response

@login_required
def export_inventory_report(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="inventory_report_{datetime.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    
    # Write headers
    writer.writerow([
        'Medicine Name', 'Category', 'Current Stock', 
        'Unit Price', 'Total Value', 'Status'
    ])
    
    # Get all medicines
    medicines = Medicine.objects.all()
    
    # Write data
    for medicine in medicines:
        status = 'Out of Stock' if medicine.stock == 0 else (
            'Low Stock' if medicine.stock <= 10 else 'In Stock'
        )
        writer.writerow([
            medicine.name,
            medicine.get_category_display(),
            medicine.stock,
            medicine.price,
            medicine.stock * medicine.price,
            status
        ])
    
    return response

class CustomerListView(LoginRequiredMixin, ListView):
    model = Customer
    template_name = 'pharmacy/customer_list.html'
    context_object_name = 'customers'
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(phone__icontains=search)
            )
        return queryset.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_form'] = CustomerSearchForm(self.request.GET)
        return context

class CustomerCreateView(LoginRequiredMixin, CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'pharmacy/customer_form.html'
    success_url = reverse_lazy('pharmacy:customer_list')

    def form_valid(self, form):
        messages.success(self.request, 'Customer added successfully!')
        return super().form_valid(form)

class CustomerDetailView(LoginRequiredMixin, DetailView):
    model = Customer
    template_name = 'pharmacy/customer_detail.html'
    context_object_name = 'customer'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sales'] = Sale.objects.filter(
            customer=self.object,
            is_completed=True
        ).order_by('-created_at')
        return context

@login_required
def customer_search(request):
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        term = request.GET.get('term', '').strip()
        query = Q()
        if term:
            query = Q(name__icontains=term) | Q(phone__icontains=term)
        else:
            # Return recent customers when no search term
            query = Q()
        
        customers = Customer.objects.filter(query).order_by('-created_at')[:10]
        results = []
        for customer in customers:
            results.append({
                'id': customer.id,
                'text': f"{customer.name} ({customer.phone})",
                'points': customer.points
            })
        return JsonResponse({'results': results})
    return JsonResponse({'results': []})

class CustomerUpdateView(LoginRequiredMixin, UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'pharmacy/customer_form.html'
    success_url = reverse_lazy('pharmacy:customer_list')

    def form_valid(self, form):
        messages.success(self.request, 'Customer updated successfully!')
        return super().form_valid(form)

@login_required
def customer_analytics(request):
    # Get all customers
    customers = Customer.objects.all()
    
    # Get completed sales
    sales = Sale.objects.filter(is_completed=True)
    
    # Calculate top customers
    top_customers = customers.annotate(
        total_purchases=Count('sale', filter=Q(sale__is_completed=True)),
        total_spent=Sum('sale__total_amount', filter=Q(sale__is_completed=True)),
        avg_purchase=Case(
            When(total_purchases__gt=0, 
                 then=F('total_spent') / F('total_purchases')),
            default=0,
            output_field=DecimalField()
        ),
        last_purchase=Max('sale__created_at', filter=Q(sale__is_completed=True))
    ).filter(total_purchases__gt=0).order_by('-total_spent')[:10]
    
    # Calculate monthly new customers
    monthly_customers = Customer.objects.annotate(
        month=TruncMonth('created_at')
    ).values('month').annotate(
        count=Count('id')
    ).order_by('-month')[:12]
    
    context = {
        'total_customers': customers.count(),
        'active_customers': customers.filter(sale__is_completed=True).distinct().count(),
        'total_points': customers.aggregate(Sum('points'))['points__sum'] or 0,
        'avg_points': customers.filter(points__gt=0).aggregate(Avg('points'))['points__avg'] or 0,
        'top_customers': top_customers,
        'monthly_customers': monthly_customers,
    }
    
    return render(request, 'pharmacy/customer_analytics.html', context)

@login_required
def profile_view(request):
    return render(request, 'pharmacy/profile/view.html', {
        'profile': request.user.userprofile
    })

@login_required
def profile_edit(request):
    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=request.user.userprofile)
        if form.is_valid():
            profile = form.save(commit=False)
            
            # Update User model fields
            user = profile.user
            user.first_name = form.cleaned_data['first_name']
            user.last_name = form.cleaned_data['last_name']
            user.email = form.cleaned_data['email']
            user.save()
            
            profile.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('pharmacy:profile_view')
    else:
        form = UserProfileForm(instance=request.user.userprofile)
    
    return render(request, 'pharmacy/profile/edit.html', {'form': form})

@login_required
def change_password(request):
    if request.method == 'POST':
        form = ChangePasswordForm(request.POST)
        if form.is_valid():
            if request.user.check_password(form.cleaned_data['current_password']):
                request.user.set_password(form.cleaned_data['new_password'])
                request.user.save()
                messages.success(request, 'Password changed successfully!')
                return redirect('login')
            else:
                messages.error(request, 'Current password is incorrect!')
    else:
        form = ChangePasswordForm()
    
    return render(request, 'pharmacy/profile/change_password.html', {'form': form})

class PrescriptionListView(LoginRequiredMixin, ListView):
    model = Prescription
    template_name = 'pharmacy/prescription/list.html'
    context_object_name = 'prescriptions'
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset()
        status = self.request.GET.get('status')
        search = self.request.GET.get('search')

        if status:
            queryset = queryset.filter(status=status)
        if search:
            queryset = queryset.filter(
                Q(customer__name__icontains=search) |
                Q(doctor_name__icontains=search)
            )
        return queryset.order_by('-created_at')

class PrescriptionCreateView(LoginRequiredMixin, CreateView):
    model = Prescription
    template_name = 'pharmacy/prescription/form.html'
    form_class = PrescriptionForm
    success_url = reverse_lazy('pharmacy:prescription_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        
        # Handle prescription items formset
        formset = PrescriptionItemFormSet(self.request.POST, instance=self.object)
        if formset.is_valid():
            formset.save()
            messages.success(self.request, 'Prescription created successfully!')
            return response
        else:
            self.object.delete()
            return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['items_formset'] = PrescriptionItemFormSet(self.request.POST)
        else:
            context['items_formset'] = PrescriptionItemFormSet()
        return context

class PrescriptionDetailView(LoginRequiredMixin, DetailView):
    model = Prescription
    template_name = 'pharmacy/prescription/detail.html'
    context_object_name = 'prescription'

@login_required
def dispense_prescription(request, pk):
    prescription = get_object_or_404(Prescription, pk=pk)
    
    if request.method == 'POST':
        if prescription.status != 'PENDING':
            messages.error(request, 'This prescription cannot be dispensed.')
            return redirect('pharmacy:prescription_detail', pk=pk)
        
        try:
            with transaction.atomic():
                # Create a new sale
                sale = Sale.objects.create(
                    user=request.user,
                    customer=prescription.customer
                )
                
                # Add prescription items to sale
                for item in prescription.items.all():
                    if item.medicine.stock < item.quantity:
                        raise ValidationError(f'Insufficient stock for {item.medicine.name}')
                    
                    SaleItem.objects.create(
                        sale=sale,
                        medicine=item.medicine,
                        quantity=item.quantity,
                        price=item.medicine.price,
                        expiry_date=StockEntry.objects.filter(
                            medicine=item.medicine,
                            quantity__gt=0
                        ).order_by('expiration_date').first().expiration_date
                    )
                    
                    # Update stock
                    item.medicine.stock -= item.quantity
                    item.medicine.save()
                
                # Update prescription status
                prescription.status = 'DISPENSED'
                prescription.sale = sale
                prescription.save()
                
                sale.calculate_total()
                messages.success(request, 'Prescription dispensed successfully!')
                return redirect('pharmacy:sale_detail', sale_id=sale.id)
                
        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f'Error dispensing prescription: {str(e)}')
    
    return redirect('pharmacy:prescription_detail', pk=pk)

@login_required
def request_refill(request, pk):
    prescription = get_object_or_404(Prescription, pk=pk)
    
    if request.method == 'POST':
        if prescription.status != 'DISPENSED' or prescription.refills_remaining <= 0:
            messages.error(request, 'Refill cannot be requested for this prescription.')
        else:
            prescription.status = 'REFILL_REQUESTED'
            prescription.save()
            messages.success(request, 'Refill requested successfully!')
    
    return redirect('pharmacy:prescription_detail', pk=pk)

class PrescriptionUpdateView(LoginRequiredMixin, UpdateView):
    model = Prescription
    template_name = 'pharmacy/prescription/form.html'
    form_class = PrescriptionForm
    success_url = reverse_lazy('pharmacy:prescription_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['items_formset'] = PrescriptionItemFormSet(
                self.request.POST, 
                instance=self.object
            )
        else:
            context['items_formset'] = PrescriptionItemFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['items_formset']
        
        if formset.is_valid():
            self.object = form.save()
            formset.instance = self.object
            formset.save()
            messages.success(self.request, 'Prescription updated successfully!')
            return super().form_valid(form)
        else:
            return self.render_to_response(self.get_context_data(form=form))

@login_required
def product_search(request):
    """View for searching products"""
    query = request.GET.get('query', '')
    results = []
    
    if query:
        results = Medicine.objects.filter(
            Q(name__icontains=query) |
            Q(barcode_number__icontains=query)
        ).order_by('name')
    
    return render(request, 'pharmacy/search/product_search.html', {
        'query': query,
        'results': results
    })

@login_required
def search_analytics(request):
    # Get date range from request or default to last 30 days
    days = int(request.GET.get('days', 30))
    start_date = timezone.now() - timedelta(days=days)
    
    # Popular searches
    popular_searches = SearchHistory.objects.filter(
        timestamp__gte=start_date
    ).values('query').annotate(
        count=Count('id'),
        success_rate=Count('id', filter=Q(found_results=True)) * 100.0 / Count('id'),
        click_rate=Count('id', filter=Q(clicked_result=True)) * 100.0 / Count('id')
    ).order_by('-count')[:10]
    
    # Searches with no results
    no_results = SearchHistory.objects.filter(
        found_results=False,
        timestamp__gte=start_date
    ).values('query').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    # Search trends over time
    search_trends = SearchHistory.objects.filter(
        timestamp__gte=start_date
    ).annotate(
        date=TruncDate('timestamp')
    ).values('date').annotate(
        count=Count('id')
    ).order_by('date')
    
    context = {
        'popular_searches': popular_searches,
        'no_results': no_results,
        'search_trends': search_trends,
        'days': days,
    }
    return render(request, 'pharmacy/search/analytics.html', context)

@login_required
def pos_add_to_cart(request):
    if request.method == 'POST':
        try:
            barcode = request.POST.get('barcode')
            quantity = int(request.POST.get('quantity', 1))
            unit_type = request.POST.get('unit_type', 'BOX')
            customer_id = request.POST.get('customer_id')
            
            medicine = Medicine.objects.get(barcode_number=barcode)
            customer = Customer.objects.get(id=customer_id) if customer_id else None
            
            # Check if can sell strips
            if unit_type == 'STRIP' and not medicine.can_sell_strips:
                messages.error(request, f'Cannot sell {medicine.name} by strip')
                return redirect('pharmacy:pos')
            
            # Calculate box quantity for stock check
            if unit_type == 'STRIP':
                box_quantity = quantity / medicine.strips_per_box
            else:
                box_quantity = quantity
            
            # Check stock
            if medicine.stock < box_quantity:
                messages.error(request, 'Insufficient stock')
                return redirect('pharmacy:pos')
            
            # Calculate original unit price
            original_price = medicine.get_strip_price() if unit_type == 'STRIP' else medicine.price
            
            # Calculate minimum profitable price (cost + 10%)
            min_profitable_price = medicine.purchase_price * Decimal('1.10')
            if unit_type == 'STRIP':
                min_profitable_price = min_profitable_price / medicine.strips_per_box
            
            # Calculate discounted price if customer exists
            if customer:
                if customer.customer_type == 'FAMILY':
                    # For family type, always use minimum profitable price
                    discounted_price = min_profitable_price
                else:
                    # For regular customers with discount percentage
                    discount = customer.discount_percentage / 100
                    discounted_price = original_price * (1 - discount)
                    
                    # Ensure price doesn't go below minimum profitable price
                    if discounted_price < min_profitable_price:
                        discounted_price = min_profitable_price
            else:
                discounted_price = original_price
            
            # Calculate totals
            original_total = float(original_price * quantity)
            discounted_total = float(discounted_price * quantity)
            
            # Add to cart
            cart = request.session.get('cart', [])
            cart.append({
                'medicine_id': medicine.id,
                'name': medicine.name,
                'quantity': quantity,
                'unit_type': unit_type,
                'original_price': float(original_price),
                'discounted_price': float(discounted_price),
                'total': discounted_total
            })
            request.session['cart'] = cart
            request.session.modified = True
            
            messages.success(request, f'Added {quantity} {unit_type} of {medicine.name} to cart')
            
        except Medicine.DoesNotExist:
            messages.error(request, 'Product not found')
        except Customer.DoesNotExist:
            messages.error(request, 'Customer not found')
        except Exception as e:
            messages.error(request, str(e))
    
    return redirect('pharmacy:pos')

class ProfitAnalyticsView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    template_name = 'pharmacy/profit_analytics.html'
    allowed_roles = ['ADMIN']  # Only allow admin users
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get date range from query params or default to last 30 days
        end_date = timezone.now().date()
        start_date = self.request.GET.get('start_date')
        end_date_param = self.request.GET.get('end_date')
        
        if start_date and end_date_param:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_param, '%Y-%m-%d').date()
        else:
            start_date = end_date - timedelta(days=30)
        
        # Get analytics data for date range
        analytics = ProfitAnalytics.objects.filter(
            date__range=[start_date, end_date]
        ).order_by('date')
        
        # Calculate summary metrics
        summary = {
            'total_sales': sum(a.total_sales for a in analytics),
            'total_profit': sum(a.total_profit for a in analytics),
            'average_margin': statistics.mean([a.profit_margin for a in analytics]) if analytics else 0,
            'total_transactions': sum(a.number_of_sales for a in analytics),
            'avg_profit_per_sale': statistics.mean([a.average_profit_per_sale for a in analytics]) if analytics else 0
        }
        
        # Get category performance
        category_profits = {}
        for analytic in analytics:
            if analytic.most_profitable_category:
                category_profits[analytic.most_profitable_category] = \
                    category_profits.get(analytic.most_profitable_category, 0) + analytic.total_profit
        
        # Get top performing medicines
        top_medicines = Medicine.objects.filter(
            top_profit_days__date__range=[start_date, end_date]
        ).annotate(
            total_profit=Sum('top_profit_days__total_profit')
        ).order_by('-total_profit')[:10]
        
        context.update({
            'analytics': analytics,
            'summary': summary,
            'category_profits': category_profits,
            'top_medicines': top_medicines,
            'start_date': start_date,
            'end_date': end_date,
        })
        return context

@login_required
def barcode_print(request):
    """View for printing barcodes for products"""
    barcode = request.GET.get('barcode')
    medicine = None
    printed = False
    error_message = None
    debug_info = []
    
    if barcode:
        medicine = Medicine.objects.filter(barcode_number=barcode).first()
        
        # Handle thermal printing
        if request.GET.get('thermal_print') and medicine:
            try:
                copies = int(request.GET.get('copies', 1))
                printer_path = request.GET.get('printer', '/dev/usb/lp0')
                
                # Add debug info about printer
                debug_info.append(f"Printer path: {printer_path}")
                debug_info.append(f"File exists: {os.path.exists(printer_path)}")
                if os.path.exists(printer_path):
                    debug_info.append(f"Permissions: {oct(os.stat(printer_path).st_mode)[-3:]}")
                    debug_info.append(f"Owner: {os.stat(printer_path).st_uid}")
                    debug_info.append(f"Group: {os.stat(printer_path).st_gid}")
                
                logger.info(f"Attempting to print barcode {barcode} to {printer_path}")
                for info in debug_info:
                    logger.debug(info)

                # Try direct printing with sudo
                import subprocess
                import shlex
                
                cmd = [
                    'sudo',
                    '-n',  # Non-interactive
                    'python3',
                    'manage.py',
                    'print_label',
                    medicine.barcode_number,
                    '--printer', printer_path,
                    '--copies', str(copies),
                    '--verbose'  # Enable verbose logging
                ]
                
                logger.debug(f"Running command: {' '.join(cmd)}")
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                )
                
                if result.returncode == 0:
                    printed = True
                    logger.info("Print job completed successfully")
                    messages.success(request, "تمت الطباعة بنجاح")
                else:
                    error_message = f"Error printing: {result.stderr}"
                    logger.error(f"Print command failed: {error_message}")
                    logger.debug(f"Command output: {result.stdout}")
                    raise Exception(error_message)
                
            except ValueError as e:
                error_message = f"Invalid parameter: {str(e)}"
                logger.error(error_message)
                messages.error(request, error_message)
            except subprocess.SubprocessError as e:
                error_message = f"Error running print command: {str(e)}"
                logger.error(error_message)
                messages.error(request, error_message)
            except Exception as e:
                error_message = f"Error printing label: {str(e)}"
                logger.error(error_message, exc_info=True)
                messages.error(request, error_message)
        
    context = {
        'medicine': medicine,
        'printed': printed,
        'error_message': error_message,
        'debug_info': debug_info if settings.DEBUG else None
    }
    
    return render(request, 'pharmacy/barcode_print.html', context)
