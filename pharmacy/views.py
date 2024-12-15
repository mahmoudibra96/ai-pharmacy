from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import F, Sum, Count, Avg, Max
from django.db.models.functions import ExtractMonth
from django.utils import timezone
from django.db import transaction
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST, require_http_methods
from .models import Medicine, StockEntry, Sale, SaleItem, Supplier, Purchase, Customer, Prescription
from .forms import MedicineForm, SupplierForm, PurchaseForm, PurchaseItemForm, CustomerForm, CustomerSearchForm, PrescriptionForm, PrescriptionItemFormSet
from django.contrib.auth.forms import UserCreationForm
from .mixins import RoleRequiredMixin
from .forms import CustomUserCreationForm
import csv
from datetime import datetime
from django.db.models import Q
from .forms import UserProfileForm, ChangePasswordForm
from django.core.exceptions import ValidationError

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
            
            # Update total stock
            total_stock = StockEntry.objects.filter(
                medicine=medicine
            ).aggregate(total=Sum('quantity'))['total'] or 0
            
            medicine.stock = total_stock
            medicine.save()
            
            print(f"Updated stock to: {total_stock}")
            
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
        
        print(f"Debug - Medicine: {medicine.name}")  # Debug print
        print(f"Debug - Stock entries: {stock_entries.count()}")  # Debug print
        
        # Calculate totals
        total_stock = medicine.stock
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
            'total_stock': total_stock,
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
            # Create new stock entry
            StockEntry.objects.create(
                medicine=medicine,
                quantity=quantity,
                expiration_date=expiration_date
            )
            
            # Update total stock
            total_stock = StockEntry.objects.filter(
                medicine=medicine
            ).aggregate(total=Sum('quantity'))['total'] or 0
            
            medicine.stock = total_stock
            medicine.save()
            
            messages.success(request, f'Updated stock for {medicine.name}')
            return redirect('pharmacy:stock_view')
    
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
            
            # Update total stock
            total_stock = StockEntry.objects.filter(
                medicine=medicine
            ).aggregate(
                total=Sum('quantity')
            )['total'] or 0
            
            medicine.stock = total_stock
            medicine.save()
            
            messages.success(
                request, 
                f'Added {total_added} units to {medicine.name} with different expiration dates. New total: {total_stock}'
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
    if not request.user.userprofile.role in ['ADMIN', 'CASHIER', 'PHARMACIST']:
        messages.error(request, "You don't have permission to access POS")
        return redirect('pharmacy:home')
    
    # Get or create an incomplete sale
    sale = Sale.objects.filter(user=request.user, is_completed=False).first()
    if not sale:
        sale = Sale.objects.create(user=request.user)
    
    if request.method == 'POST':
        barcode = request.POST.get('barcode')
        quantity = int(request.POST.get('quantity', 1))
        selected_expiry = request.POST.get('expiry_date')  # For when expiry date is selected
        customer_id = request.POST.get('customer_id')  # Get customer_id from POST
        
        # Update customer if provided
        if customer_id:
            try:
                customer = Customer.objects.get(id=customer_id)
                sale.customer = customer
                sale.save()
            except Customer.DoesNotExist:
                pass
        
        try:
            medicine = Medicine.objects.get(barcode_number=barcode)
            
            # Check stock availability
            if medicine.stock < quantity:
                messages.error(request, 'Insufficient stock')
                return redirect('pharmacy:pos')
            
            # Get valid stock entries (not expired)
            valid_stock_entries = StockEntry.objects.filter(
                medicine=medicine,
                quantity__gt=0,
                expiration_date__gt=timezone.now().date()
            ).order_by('expiration_date')
            
            if not valid_stock_entries.exists():
                messages.error(request, 'No valid stock available')
                return redirect('pharmacy:pos')
            
            # If only one expiry date or expiry date was selected
            if valid_stock_entries.count() == 1 or selected_expiry:
                stock_entry = valid_stock_entries.first() if not selected_expiry else valid_stock_entries.get(expiration_date=selected_expiry)
                
                # Create sale item
                SaleItem.objects.create(
                    sale=sale,
                    medicine=medicine,
                    quantity=quantity,
                    price=medicine.price,
                    expiry_date=stock_entry.expiration_date
                )
                
                # Update total
                sale.calculate_total()
                messages.success(request, f'Added {quantity} {medicine.name} to cart')
                return redirect('pharmacy:pos')
            else:
                # Multiple expiry dates available - show selection form
                context = {
                    'sale': sale,
                    'sale_items': sale.items.all(),
                    'total': sale.total_amount,
                    'show_expiry_modal': True,
                    'medicine': medicine,
                    'quantity': quantity,
                    'stock_entries': valid_stock_entries,
                }
                return render(request, 'pharmacy/pos.html', context)
                
        except Medicine.DoesNotExist:
            messages.error(request, 'Product not found')
        except Exception as e:
            messages.error(request, str(e))
        
        return redirect('pharmacy:pos')
    
    context = {
        'sale': sale,
        'sale_items': sale.items.all(),
        'total': sale.total_amount,
        'show_receipt': False
    }
    return render(request, 'pharmacy/pos.html', context)

@login_required
def pos_remove_item(request, item_id):
    if request.method == 'POST':
        try:
            item = SaleItem.objects.get(id=item_id)
            sale = item.sale
            item.delete()
            sale.calculate_total()
            messages.success(request, 'Item removed from cart')
        except SaleItem.DoesNotExist:
            messages.error(request, 'Item not found')
    
    return redirect('pharmacy:pos')

@login_required
def pos_complete_sale(request):
    if request.method == 'POST':
        try:
            sale_id = request.POST.get('sale_id')
            payment_method = request.POST.get('payment_method')
            customer_id = request.POST.get('customer_id')
            
            # Get the sale
            try:
                sale = Sale.objects.get(id=sale_id, is_completed=False)
            except Sale.DoesNotExist:
                # If refreshing after completion, redirect to new sale
                last_sale_id = request.session.get('last_completed_sale_id')
                if last_sale_id:
                    messages.info(request, 'Sale was already completed. Starting new sale.')
                    # Clear the session variable
                    del request.session['last_completed_sale_id']
                    return redirect('pharmacy:pos')
                else:
                    messages.error(request, 'Invalid sale. Please try again.')
                return redirect('pharmacy:pos')
            
            # Check if sale has items
            if not sale.items.exists():
                messages.error(request, 'Cannot complete sale with no items')
                return redirect('pharmacy:pos')
            
            # Add customer if selected
            if customer_id:
                try:
                    customer = Customer.objects.get(id=customer_id)
                    sale.customer = customer
                    # Add loyalty points based on total sale amount
                    points_added = customer.add_points(sale.total_amount)
                    messages.success(
                        request, 
                        f'Added {points_added} points to {customer.name}\'s account!'
                    )
                except Customer.DoesNotExist:
                    messages.warning(request, 'Selected customer not found')
            
            # Update stock for each item
            for item in sale.items.all():
                medicine = item.medicine
                medicine.stock -= item.quantity
                medicine.save()
            
            # Complete the sale
            sale.payment_method = payment_method
            sale.is_completed = True
            sale.save()
            
            # Store completed sale ID in session
            request.session['last_completed_sale_id'] = sale.id
            
            # Create new sale for next transaction
            new_sale = Sale.objects.create(user=request.user)
            
            messages.success(request, f'Sale #{sale.id} completed successfully!')
            
            return render(request, 'pharmacy/pos.html', {
                'sale': new_sale,
                'sale_items': [],
                'total': 0,
                'show_receipt': True,
                'completed_sale': sale,
                'completed_items': sale.items.all(),
                'completed_total': sale.total_amount,
            })
            
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
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    sales = Sale.objects.filter(is_completed=True)
    if start_date:
        sales = sales.filter(created_at__date__gte=start_date)
    if end_date:
        sales = sales.filter(created_at__date__lte=end_date)
    
    # Calculate statistics
    total_sales = sales.count()
    total_revenue = sales.aggregate(total=Sum('total_amount'))['total'] or 0
    avg_sale = total_revenue / total_sales if total_sales > 0 else 0
    
    # Group by payment method
    payment_stats = sales.values('payment_method').annotate(
        count=Count('id'),
        total=Sum('total_amount')
    )
    
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
        'sales': sales,
        'total_sales': total_sales,
        'total_revenue': total_revenue,
        'avg_sale': avg_sale,
        'payment_stats': payment_stats,
        'top_products': top_products,
        'start_date': start_date,
        'end_date': end_date,
    }
    return render(request, 'pharmacy/reports/sales_report.html', context)

@login_required
def inventory_report(request):
    medicines = Medicine.objects.all()
    
    # Calculate inventory value
    total_value = sum(medicine.stock * medicine.price for medicine in medicines)
    
    # Low stock items (using fixed threshold of 10)
    low_stock = medicines.filter(stock__lte=10)
    
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
    # Overall statistics
    total_customers = Customer.objects.count()
    active_customers = Customer.objects.filter(is_active=True).count()
    
    # Top customers by purchase amount
    top_customers = Customer.objects.annotate(
        total_purchases=Count('sale'),
        total_spent=Sum('sale__total_amount'),
        avg_purchase=Avg('sale__total_amount'),
        last_purchase=Max('sale__created_at')
    ).filter(total_spent__gt=0).order_by('-total_spent')[:10]
    
    # Customer loyalty statistics
    loyalty_stats = Customer.objects.aggregate(
        total_points=Sum('points'),
        avg_points=Avg('points')
    )
    
    # Monthly new customers
    current_year = timezone.now().year
    monthly_new_customers = Customer.objects.filter(
        created_at__year=current_year
    ).annotate(
        month=ExtractMonth('created_at')
    ).values('month').annotate(
        count=Count('id')
    ).order_by('month')
    
    context = {
        'total_customers': total_customers,
        'active_customers': active_customers,
        'top_customers': top_customers,
        'loyalty_stats': loyalty_stats,
        'monthly_new_customers': monthly_new_customers,
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
