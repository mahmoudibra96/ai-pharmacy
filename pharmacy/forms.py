from django import forms
from .models import Medicine
from django.contrib.auth.forms import UserCreationForm
from .models import UserProfile
from .models import Supplier
from .models import Purchase
from .models import PurchaseItem
from .models import Customer
from django.forms import inlineformset_factory
from .models import Prescription, PrescriptionItem

class MedicineForm(forms.ModelForm):
    barcode_number = forms.CharField(
        max_length=13,
        required=True,
        help_text="Enter product barcode"
    )
    
    class Meta:
        model = Medicine
        fields = [
            'name', 'description', 'category', 'price',
            'barcode_number', 'reorder_level', 'image',
            'strips_per_box', 'can_sell_strips', 'strip_price'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
            'barcode_number': forms.TextInput(attrs={'class': 'form-control'}),
            'reorder_level': forms.NumberInput(attrs={'class': 'form-control'}),
            'strips_per_box': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'can_sell_strips': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'strip_price': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
            'image': forms.FileInput(attrs={'class': 'form-control'})
        }

    def clean_barcode_number(self):
        barcode = self.cleaned_data['barcode_number']
        if not self.instance.pk:  # Only check on create, not update
            if Medicine.objects.filter(barcode_number=barcode).exists():
                raise forms.ValidationError('This barcode is already in use.')
        return barcode

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:  # If editing existing medicine
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

class UserProfileForm(forms.ModelForm):
    first_name = forms.CharField(max_length=30)
    last_name = forms.CharField(max_length=30)
    email = forms.EmailField()

    class Meta:
        model = UserProfile
        fields = ['phone', 'address', 'profile_pic', 'bio', 'date_of_birth']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'bio': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.user:
            self.fields['first_name'].initial = self.instance.user.first_name
            self.fields['last_name'].initial = self.instance.user.last_name
            self.fields['email'].initial = self.instance.user.email

class ChangePasswordForm(forms.Form):
    current_password = forms.CharField(widget=forms.PasswordInput)
    new_password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get('new_password')
        confirm_password = cleaned_data.get('confirm_password')

        if new_password and confirm_password and new_password != confirm_password:
            raise forms.ValidationError("New passwords don't match!")
        return cleaned_data

class PrescriptionForm(forms.ModelForm):
    class Meta:
        model = Prescription
        fields = [
            'customer', 'doctor_name', 'doctor_contact', 
            'prescription_date', 'expiry_date', 'refills_allowed',
            'notes', 'image'
        ]
        widgets = {
            'prescription_date': forms.DateInput(attrs={'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

class PrescriptionItemForm(forms.ModelForm):
    class Meta:
        model = PrescriptionItem
        fields = ['medicine', 'quantity', 'dosage', 'duration', 'instructions']
        widgets = {
            'instructions': forms.Textarea(attrs={'rows': 2}),
        }

# Create formset for prescription items
PrescriptionItemFormSet = inlineformset_factory(
    Prescription,
    PrescriptionItem,
    form=PrescriptionItemForm,
    extra=1,  # Number of empty forms to display
    can_delete=True,  # Allow deleting items
    min_num=1,  # Minimum number of forms
    validate_min=True,  # Enforce minimum number
)