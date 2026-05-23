from django.db import models
import random
import string
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model


class Location(models.Model):
	STATUS_ACTIVE = 'active'
	STATUS_INACTIVE = 'inactive'
	STATUS_CHOICES = [
		(STATUS_ACTIVE, 'Active'),
		(STATUS_INACTIVE, 'Inactive'),
	]

	name = models.CharField(max_length=255)
	# `code` must be required and unique
	code = models.CharField(max_length=50, unique=True, blank=False, null=False, default='')
	status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
	is_draft = models.BooleanField(default=False)
	# soft-delete flag: when True the record is considered deleted
	is_deleted = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['-created_at']
		verbose_name = 'Location'
		verbose_name_plural = 'Locations'

	def __str__(self):
		return f"{self.name} ({self.code})" if self.code else self.name


class Company(models.Model):
	STATUS_ACTIVE = 'active'
	STATUS_INACTIVE = 'inactive'
	STATUS_CHOICES = [
		(STATUS_ACTIVE, 'Active'),
		(STATUS_INACTIVE, 'Inactive'),
	]

	name = models.CharField(max_length=255)
	# `code` should be required and unique
	code = models.CharField(max_length=50, unique=True, blank=False, null=False, default='')
	status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
	is_draft = models.BooleanField(default=False)
	# soft-delete flag: when True the record is considered deleted
	is_deleted = models.BooleanField(default=False)
	# relation to Location - multiple locations selectable
	locations = models.ManyToManyField(Location, related_name='companies', blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['-created_at']
		verbose_name = 'Company'
		verbose_name_plural = 'Companies'

	def __str__(self):
		return f"{self.name} ({self.code})" if self.code else self.name


class Partner(models.Model):
	RELATION_EMPLOYEE = 'employee'
	RELATION_CLIENT = 'client'
	RELATION_VENDOR = 'vendor'
	RELATION_CONSULTANT = 'consultant'
	RELATION_SERVICE_PROVIDER = 'service_provider'
	RELATION_HARDWARE_PARTNER = 'hardware_partner'
	RELATION_SOFTWARE_PARTNER = 'software_partner'
	RELATION_SUPPORT_PARTNER = 'support_partner'
	RELATION_RESELLER = 'reseller'
	RELATION_DISTRIBUTOR = 'distributor'
	RELATION_TECHNICIAN = 'technician'
	RELATION_CONTRACT_STAFF = 'contract_staff'
	RELATION_FREELANCER = 'freelancer'
	RELATION_BUSINESS_ASSOCIATE = 'business_associate'
	RELATION_SYSTEM_INTEGRATOR = 'system_integrator'

	RELATION_CHOICES = [
		(RELATION_EMPLOYEE, 'Employee'),
		(RELATION_CLIENT, 'Client'),
		(RELATION_VENDOR, 'Vendor'),
		(RELATION_CONSULTANT, 'Consultant'),
		(RELATION_SERVICE_PROVIDER, 'Service Provider'),
		(RELATION_HARDWARE_PARTNER, 'Hardware Partner'),
		(RELATION_SOFTWARE_PARTNER, 'Software Partner'),
		(RELATION_SUPPORT_PARTNER, 'Support Partner'),
		(RELATION_RESELLER, 'Reseller'),
		(RELATION_DISTRIBUTOR, 'Distributor'),
		(RELATION_TECHNICIAN, 'Technician'),
		(RELATION_CONTRACT_STAFF, 'Contract Staff'),
		(RELATION_FREELANCER, 'Freelancer'),
		(RELATION_BUSINESS_ASSOCIATE, 'Business Associate'),
		(RELATION_SYSTEM_INTEGRATOR, 'System Integrator'),
	]

	name = models.CharField(max_length=255)
	relation = models.CharField(max_length=30, choices=RELATION_CHOICES)
	STATUS_ACTIVE = 'active'
	STATUS_INACTIVE = 'inactive'
	STATUS_CHOICES = [
		(STATUS_ACTIVE, 'Active'),
		(STATUS_INACTIVE, 'Inactive'),
	]
	status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
	email = models.EmailField(blank=True, null=True)
	phone = models.CharField(max_length=50, blank=True)
	address = models.TextField(blank=True)
	# allow linking one Partner to many Companies (similar to Company -> Locations)
	companies = models.ManyToManyField(Company, related_name='partners', blank=True)
	is_draft = models.BooleanField(default=False)
	# soft-delete flag: when True the record is considered deleted
	is_deleted = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['-created_at']
		verbose_name = 'Partner'
		verbose_name_plural = 'Partners'

	def __str__(self):
		return self.name



class Lead(models.Model):
	STATUS_WON = 'won'
	STATUS_LOSS = 'loss'
	STATUS_CHOICES = [
		(STATUS_WON, 'Won'),
		(STATUS_LOSS, 'Loss'),
	]

	lead_unique_id = models.CharField(max_length=20, unique=True, editable=False)
	# Lead's display name
	name = models.CharField(max_length=255, null=True, blank=True)
	# Optional client associated with this lead
	client = models.ForeignKey('Client', null=True, blank=True, on_delete=models.SET_NULL, related_name='leads')
	assign_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='assigned_leads')
	status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_LOSS)
	is_draft = models.BooleanField(default=False)
	is_delete = models.BooleanField(default=False)
	is_approved = models.BooleanField(default=False)
	approval_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='approved_leads')
	companies = models.ManyToManyField(Company, related_name='leads', blank=True)
	# Persist the last opened wizard step (1=Basic, 2=Details, 3=Billing, 4=Done)
	last_wizard_step = models.PositiveSmallIntegerField(default=1)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['-created_at']
		verbose_name = 'Lead'
		verbose_name_plural = 'Leads'
		db_table = 'lead'

	def save(self, *args, **kwargs):
		if not self.lead_unique_id:
			prefix = 'LD'
			while True:
				rand = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
				candidate = f"{prefix}{rand}"
				if not self.__class__.objects.filter(lead_unique_id=candidate).exists():
					self.lead_unique_id = candidate
					break
		super().save(*args, **kwargs)

	def __str__(self):
		try:
			return self.name or self.lead_unique_id
		except Exception:
			return self.lead_unique_id


class LeadPartner(models.Model):
	lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='partner_links')
	partner = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name='lead_links')
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		unique_together = ('lead', 'partner')
		ordering = ['-created_at']
		verbose_name = 'Lead Partner'
		verbose_name_plural = 'Lead Partners'
		db_table = 'lead_partner'

	def __str__(self):
		try:
			return f"{self.lead.lead_unique_id} - {self.partner.name}"
		except Exception:
			return str(self.pk)


class LeadFollowup(models.Model):
	FOLLOWUP_CALL = 'call'
	FOLLOWUP_MESSAGE = 'message'
	FOLLOWUP_EMAIL = 'email'
	FOLLOWUP_TYPE_CHOICES = [
		(FOLLOWUP_CALL, 'Call'),
		(FOLLOWUP_MESSAGE, 'Message'),
		(FOLLOWUP_EMAIL, 'Email'),
	]

	lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='followups')
	followup_date = models.DateTimeField()
	followup_type = models.CharField(max_length=10, choices=FOLLOWUP_TYPE_CHOICES)
	remark = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['-followup_date']
		verbose_name = 'Lead Followup'
		verbose_name_plural = 'Lead Followups'
		db_table = 'lead_followup'

	def __str__(self):
		try:
			return f'{self.lead.lead_unique_id} - {self.followup_date}'
		except Exception:
			return str(self.pk)


class LeadMeetingSchedule(models.Model):
	STATUS_PENDING = 'pending'
	STATUS_COMPLETE = 'complete'
	STATUS_RESCHEDULE = 'reschedule'
	STATUS_CANCEL = 'cancel'
	STATUS_CHOICES = [
		(STATUS_PENDING, 'Pending'),
		(STATUS_COMPLETE, 'Complete'),
		(STATUS_RESCHEDULE, 'Reschedule'),
		(STATUS_CANCEL, 'Cancel'),
	]

	lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='meeting_schedules')
	schedule_start_datetime = models.DateTimeField()
	schedule_end_datetime = models.DateTimeField(null=True, blank=True)
	new_requirement = models.TextField(blank=True)
	schedule_remark = models.TextField(blank=True)
	status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_PENDING)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['-schedule_start_datetime']
		verbose_name = 'Lead Meeting Schedule'
		verbose_name_plural = 'Lead Meeting Schedules'
		db_table = 'lead_meeting_schedule'

	def __str__(self):
		try:
			return f'{self.lead.lead_unique_id} - {self.schedule_start_datetime}'
		except Exception:
			return str(self.pk)


class LeadCommissionSlab(models.Model):
	LEAD_FOR_SOFTWARE = 'software'
	LEAD_FOR_HARDWARE = 'hardware'
	LEAD_FOR_SOFTWARE_HARDWARE = 'software_hardware'
	LEAD_FOR_OTHER = 'other'
	LEAD_FOR_CHOICES = [
		(LEAD_FOR_SOFTWARE, 'Software'),
		(LEAD_FOR_HARDWARE, 'Hardware'),
		(LEAD_FOR_SOFTWARE_HARDWARE, 'Software & Hardware'),
		(LEAD_FOR_OTHER, 'Other'),
	]

	TYPE_FIX = 'fix_amount'
	TYPE_PERCENTAGE = 'percentage_wise'
	TYPE_RECURRING = 'recurring'
	TYPE_ONLY_FIRST = 'only_for_first_billing'
	TYPE_EVERY_BILLING = 'every_billing'
	TYPE_CHOICES = [
		(TYPE_FIX, 'Fix Amount'),
		(TYPE_PERCENTAGE, 'Percentage Wise'),
		(TYPE_RECURRING, 'Recurring'),
		(TYPE_ONLY_FIRST, 'Only For First Billing'),
		(TYPE_EVERY_BILLING, 'Every Billing'),
	]

	CREDIT_AFTER_BILLING = 'after_billing'
	CREDIT_BEFORE_BILLING = 'before_billing'
	CREDIT_AFTER_PERCENT_COMPLETE = 'after_billing_percentage_complate'
	CREDIT_AFTER_FEW_DAYS = 'after_billing_few_days'
	CREDIT_CHOICES = [
		(CREDIT_AFTER_BILLING, 'After Billing'),
		(CREDIT_BEFORE_BILLING, 'Before Billing'),
		(CREDIT_AFTER_PERCENT_COMPLETE, 'After Billing Percentage Complete'),
		(CREDIT_AFTER_FEW_DAYS, 'After Billing Few Days'),
	]

	lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='commission_slabs')
	lead_commission_type = models.CharField(max_length=32, choices=TYPE_CHOICES)
	lead_commission_credit_term_condition = models.CharField(max_length=48, choices=CREDIT_CHOICES)
	lead_commission_type_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
	lead_commission_credit_term_condition_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
	commission_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
	# Optional date range for which this commission slab is active
	commission_start_date = models.DateField(null=True, blank=True)
	commission_end_date = models.DateField(null=True, blank=True)
	# Optional relation to a LeadBilling record (creates `lead_billing_id` column)
	lead_billing = models.ForeignKey('LeadBilling', null=True, blank=True, on_delete=models.SET_NULL, related_name='commission_slabs_by_billing')
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['-created_at']
		verbose_name = 'Lead Commission Slab'
		verbose_name_plural = 'Lead Commission Slabs'
		db_table = 'lead_commission_slab'

	def __str__(self):
		try:
			return f"{self.lead.lead_unique_id} - {self.lead_commission_type} - {self.commission_amount}"
		except Exception:
			return str(self.pk)


class LeadBilling(models.Model):
	lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='billings')
	lead_for = models.CharField(max_length=50, choices=LeadCommissionSlab.LEAD_FOR_CHOICES)
	is_for_software = models.BooleanField(default=False)
	is_peremp_wise_amount = models.BooleanField(default=False)
	emp_count = models.PositiveIntegerField(null=True, blank=True)
	peremp_amount = models.PositiveIntegerField(null=True, blank=True)
	amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
	another_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['-created_at']
		verbose_name = 'Lead Billing'
		verbose_name_plural = 'Lead Billings'
		db_table = 'lead_billing'

	def __str__(self):
		try:
			return f"{self.lead.lead_unique_id} - {self.lead_for} - {self.amount}"
		except Exception:
			return str(self.pk)


class UserProfile(models.Model):
	user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
	middle_name = models.CharField(max_length=150, blank=True)
	phone = models.CharField(max_length=50, blank=True)
	# allow linking one user to multiple locations and companies
	locations = models.ManyToManyField(Location, related_name='users', blank=True)
	companies = models.ManyToManyField(Company, related_name='users', blank=True)
	is_draft = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		verbose_name = 'User Profile'
		verbose_name_plural = 'User Profiles'
		ordering = ['-created_at']

	def __str__(self):
		try:
			return f"{self.user.get_full_name() or self.user.username}"
		except Exception:
			return str(self.user.pk)


@receiver(post_save, sender=get_user_model())
def create_or_update_user_profile(sender, instance, created, **kwargs):
	if created:
		try:
			UserProfile.objects.create(user=instance)
		except Exception:
			pass
	else:
		# ensure profile exists and save
		try:
			if hasattr(instance, 'profile'):
				instance.profile.save()
			else:
				UserProfile.objects.get_or_create(user=instance)
		except Exception:
			pass


class Client(models.Model):
	name = models.CharField(max_length=255)
	address = models.TextField(blank=True)
	email = models.EmailField(blank=True, null=True)
	number = models.CharField(max_length=50, blank=True)
	is_draft = models.BooleanField(default=False)
	is_delete = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['-created_at']
		verbose_name = 'Client'
		verbose_name_plural = 'Clients'
		db_table = 'client'

	def __str__(self):
		try:
			return self.name or str(self.pk)
		except Exception:
			return str(self.pk)
