from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from .models import Location, Company, Partner, Lead, UserProfile, Client, Product


class LocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = ['name', 'code', 'status']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'id': 'location-name', 'required': True}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'id': 'location-code', 'required': True}),
            'status': forms.Select(attrs={'class': 'form-select', 'id': 'status', 'required': True}),
        }

    def clean_code(self):
        code = self.cleaned_data.get('code')
        if not code or not code.strip():
            raise forms.ValidationError('Location code is required.')

        code_str = code.strip()

        action = None
        try:
            action = (self.data.get('action') or 'publish').lower()
        except Exception:
            action = 'publish'

        if action != 'draft':
            qs = Location.objects.filter(code__iexact=code_str, is_draft=False)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError('Location code must be unique among published locations.')

        return code_str


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ['name', 'code', 'status', 'locations']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'id': 'company-name', 'required': True}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'id': 'company-code', 'required': True}),
            'status': forms.Select(attrs={'class': 'form-select', 'id': 'status', 'required': True}),
            'locations': forms.SelectMultiple(attrs={'class': 'form-select js-choice', 'id': 'locations'}),
        }

    def clean_code(self):
        code = self.cleaned_data.get('code')
        if not code or not code.strip():
            raise forms.ValidationError('Company code is required.')

        code_str = code.strip()

        action = None
        try:
            action = (self.data.get('action') or 'publish').lower()
        except Exception:
            action = 'publish'

        if action != 'draft':
            qs = Company.objects.filter(code__iexact=code_str, is_draft=False)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError('Company code must be unique among published companies.')

        return code_str


class PartnerForm(forms.ModelForm):
    relation = forms.ChoiceField(
        choices=[('', 'Select relation')] + Partner.RELATION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'partner-relation', 'required': True}),
        required=True,
    )

    class Meta:
        model = Partner
        fields = ['name', 'relation', 'status', 'companies', 'email', 'phone', 'address']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'id': 'partner-name', 'required': True}),
            'status': forms.Select(attrs={'class': 'form-select', 'id': 'partner-status'}),
            'companies': forms.SelectMultiple(attrs={'class': 'form-select js-choice', 'id': 'partner-companies'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'id': 'partner-email'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'id': 'partner-phone'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'id': 'partner-address', 'rows': 3}),
        }


class ProductForm(forms.ModelForm):
    companies = forms.ModelMultipleChoiceField(
        queryset=Company.objects.filter(is_deleted=False, is_draft=False).order_by('-created_at'),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-select js-choice', 'id': 'product-companies'})
    )

    locations = forms.ModelMultipleChoiceField(
        queryset=Location.objects.filter(is_deleted=False, is_draft=False).order_by('-created_at'),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-select js-choice', 'id': 'product-locations'})
    )

    class Meta:
        model = Product
        fields = ['name', 'sku', 'description', 'status', 'companies', 'locations']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'id': 'product-name', 'required': True}),
            'sku': forms.TextInput(attrs={'class': 'form-control', 'id': 'product-sku', 'required': True}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'id': 'product-description', 'rows': 4}),
            'status': forms.Select(attrs={'class': 'form-select', 'id': 'product-status'}),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        if commit:
            instance.save()
            comps = self.cleaned_data.get('companies')
            locs = self.cleaned_data.get('locations')
            if comps is not None:
                instance.companies.set(comps)
            if locs is not None:
                instance.locations.set(locs)
        return instance


class LeadForm(forms.ModelForm):
    assign_user = forms.ModelChoiceField(
        queryset=get_user_model().objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'lead-assign-user'})
    )

    approval_user = forms.ModelChoiceField(
        queryset=get_user_model().objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'lead-approval-user'})
    )

    partner = forms.ModelChoiceField(
        queryset=Partner.objects.filter(is_deleted=False, is_draft=False).order_by('-created_at'),
        required=False,
        empty_label='Select Partner',
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'partner'})
    )

    sales_person = forms.ModelChoiceField(
        queryset=get_user_model().objects.filter(is_active=True).order_by('-date_joined'),
        required=False,
        empty_label='Select Sales Person',
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'sales-person'})
    )

    client = forms.ModelChoiceField(
        queryset=Client.objects.filter(is_delete=False, is_draft=False).order_by('-created_at'),
        required=False,
        empty_label='Select Client',
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'bootstrap-wizard-wizard-client-name',
            'data-wizard-client-name': 'true'
        })
    )

    # Make status optional in the form so wizard partial-saves don't fail
    status = forms.ChoiceField(
        choices=[('', 'Select status')] + list(Lead.STATUS_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'lead-status'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Partner label: show name and relation (e.g. "Acme (reseller)")
        try:
            self.fields['partner'].label_from_instance = lambda obj: f"{obj.name} ({obj.get_relation_display()})"
        except Exception:
            pass

        # Sales person label: show username and full name if available
        def _user_label(u):
            try:
                full = u.get_full_name() or ''
            except Exception:
                full = ''
            if full:
                return f"{u.username} ({full})"
            return u.username

        try:
            self.fields['sales_person'].label_from_instance = _user_label
        except Exception:
            pass

    class Meta:
        model = Lead
        fields = ['name', 'client', 'assign_user', 'approval_user', 'status', 'is_draft', 'is_approved', 'companies']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'id': 'lead-name'}),
            'status': forms.Select(attrs={'class': 'form-select', 'id': 'lead-status'}),
            'is_draft': forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'lead-is-draft'}),
            'is_approved': forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'lead-is-approved'}),
            'companies': forms.SelectMultiple(attrs={'class': 'form-select js-choice', 'id': 'companies'}),
        }


class EditUserForm(forms.ModelForm):
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_username'}))
    first_name = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_first_name'}))
    last_name = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_last_name'}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'class': 'form-control', 'id': 'id_email'}))
    middle_name = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_middle_name'}))
    phone = forms.CharField(max_length=50, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_phone'}))
    locations = forms.ModelMultipleChoiceField(
        queryset=Location.objects.filter(is_deleted=False, is_draft=False).order_by('-created_at'),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-select js-choice', 'id': 'locations'})
    )
    companies = forms.ModelMultipleChoiceField(
        queryset=Company.objects.filter(is_deleted=False, is_draft=False).order_by('-created_at'),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-select js-choice', 'id': 'companies'})
    )
    # optional password fields for edit
    password1 = forms.CharField(label='Password', required=False, widget=forms.PasswordInput(attrs={'class': 'form-control', 'id': 'id_password1'}))
    password2 = forms.CharField(label='Password confirmation', required=False, widget=forms.PasswordInput(attrs={'class': 'form-control', 'id': 'id_password2'}))
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]
    status = forms.ChoiceField(choices=STATUS_CHOICES, required=False, widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_status'}), initial='active')

    class Meta:
        model = get_user_model()
        fields = ('username', 'first_name', 'last_name', 'email')

    def clean(self):
        cleaned = super().clean()
        pw1 = cleaned.get('password1')
        pw2 = cleaned.get('password2')
        if pw1 or pw2:
            if not pw1:
                self.add_error('password1', 'Password is required to change the password.')
            elif not pw2:
                self.add_error('password2', 'Please confirm the password.')
            elif pw1 != pw2:
                self.add_error('password2', 'Passwords do not match.')
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        # set active/inactive based on status field
        status_val = self.cleaned_data.get('status')
        if status_val is not None:
            user.is_active = True if status_val == 'active' else False

        # set password if provided
        pw = self.cleaned_data.get('password1')
        if pw:
            user.set_password(pw)

        if commit:
            user.save()
            profile, created = UserProfile.objects.get_or_create(user=user)
            profile.middle_name = self.cleaned_data.get('middle_name', '') or profile.middle_name
            profile.phone = self.cleaned_data.get('phone', '') or profile.phone
            profile.save()
            # set many-to-many relations
            locs = self.cleaned_data.get('locations')
            if locs is not None:
                profile.locations.set(locs)
            comps = self.cleaned_data.get('companies')
            if comps is not None:
                profile.companies.set(comps)
        return user

class UserRegistrationForm(UserCreationForm):
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_username'}))
    first_name = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_first_name'}))
    last_name = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_last_name'}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'class': 'form-control', 'id': 'id_email'}))
    middle_name = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_middle_name'}))
    phone = forms.CharField(max_length=50, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_phone'}))
    locations = forms.ModelMultipleChoiceField(
        queryset=Location.objects.filter(is_deleted=False, is_draft=False).order_by('-created_at'),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-select js-choice', 'id': 'locations'})
    )
    companies = forms.ModelMultipleChoiceField(
        queryset=Company.objects.filter(is_deleted=False, is_draft=False).order_by('-created_at'),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-select js-choice', 'id': 'companies'})
    )
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]
    status = forms.ChoiceField(choices=STATUS_CHOICES, required=False, widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_status'}), initial='active')
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput(attrs={'class': 'form-control', 'id': 'id_password1'}))
    password2 = forms.CharField(label='Password confirmation', widget=forms.PasswordInput(attrs={'class': 'form-control', 'id': 'id_password2'}))

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data.get('first_name', '')
        user.last_name = self.cleaned_data.get('last_name', '')
        user.email = self.cleaned_data.get('email', '')
        # set active/inactive based on status field
        status_val = self.cleaned_data.get('status')
        if status_val is not None:
            user.is_active = True if status_val == 'active' else False
        if commit:
            user.save()
            profile, created = UserProfile.objects.get_or_create(user=user)
            profile.middle_name = self.cleaned_data.get('middle_name', '')
            profile.phone = self.cleaned_data.get('phone', '')
            profile.save()
            # set many-to-many relations for registration
            locs = self.cleaned_data.get('locations')
            if locs is not None:
                profile.locations.set(locs)
            comps = self.cleaned_data.get('companies')
            if comps is not None:
                profile.companies.set(comps)
        return user
