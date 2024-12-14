from django import forms
from .models import Medicine
from django.contrib.auth.forms import UserCreationForm
from .models import UserProfile
from .models import Supplier
from .models import Purchase
from .models import PurchaseItem
from .models import Customer

class MedicineForm(forms.ModelForm):
    barcode_number = forms.CharField(
        max_length=13,
        required=True,
        help_text="Enter product barcode"
    )
    
    class Meta:
        model = Medicine
        fields = [
            'barcode_number',
            'name',
            'description',
            'price',
            'category',
            'image',
            'is_active'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'price': forms.NumberInput(attrs={'min': 0, 'step': 0.01}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.initial.get('barcode_number'):
            self.fields['barcode_number'].widget.attrs['readonly'] = True

class POSItemForm(forms.Form):
    barcode = forms.CharField(max_length=13, required=True)
    quantity = forms.IntegerField(min_value=1, initial=1)

class CustomUserCreationForm(UserCreationForm):
    role = forms.ChoiceField(choices=UserProfile.ROLE_CHOICES)
    phone = forms.CharField(max_length=20, required=False)
    address = forms.CharField(widget=forms.Textarea, required=False)

    class Meta(UserCreationForm.Meta):
        fields = UserCreationForm.Meta.fields + ('email', 'first_name', 'last_name')

    def save(self, commit=True):
        user = super().save(commit=True)
        UserProfile.objects.create(
            user=user,
            role=self.cleaned_data['role'],
            phone=self.cleaned_data['phone'],
            address=self.cleaned_data['address']
        )
        return user

class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['name', 'contact_person', 'phone', 'email', 'address', 'is_active']
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
        }

class PurchaseForm(forms.ModelForm):
    class Meta:
        model = Purchase
        fields = ['supplier', 'invoice_number', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

class PurchaseItemForm(forms.ModelForm):
    class Meta:
        model = PurchaseItem
        fields = ['medicine', 'quantity', 'price', 'expiry_date']
        widgets = {
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
        }

class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['name', 'phone', 'email', 'address']
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
        }

class CustomerSearchForm(forms.Form):
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Search by name or phone'})
    )