from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin
from .models import Location, Company, Lead, LeadPartner, LeadFollowup, LeadMeetingSchedule, LeadCommissionSlab, UserProfile


class LocationAdmin(admin.ModelAdmin):
	list_display = ('name', 'code', 'status', 'is_draft', 'created_at')
	list_filter = ('status', 'is_draft')
	search_fields = ('name', 'code')
	list_per_page = 25


admin.site.register(Location, LocationAdmin)


class CompanyAdmin(admin.ModelAdmin):
	list_display = ('name', 'code', 'status', 'is_draft', 'created_at')
	list_filter = ('status', 'is_draft')
	search_fields = ('name', 'code')
	filter_horizontal = ('locations',)
	list_per_page = 25


admin.site.register(Company, CompanyAdmin)


class LeadAdmin(admin.ModelAdmin):
	list_display = ('lead_unique_id', 'assign_user', 'status', 'is_draft', 'is_delete', 'is_approved', 'created_at')
	list_filter = ('status', 'is_draft', 'is_delete', 'is_approved')
	search_fields = ('lead_unique_id',)
	filter_horizontal = ('companies',)
	list_per_page = 25


admin.site.register(Lead, LeadAdmin)


class LeadPartnerAdmin(admin.ModelAdmin):
	list_display = ('lead', 'partner', 'created_at')
	list_filter = ('created_at',)
	search_fields = ('lead__lead_unique_id', 'partner__name')
	list_per_page = 25


admin.site.register(LeadPartner, LeadPartnerAdmin)


class LeadFollowupAdmin(admin.ModelAdmin):
	list_display = ('lead', 'followup_date', 'followup_type', 'created_at')
	list_filter = ('followup_type',)
	search_fields = ('lead__lead_unique_id', 'remark')
	raw_id_fields = ('lead',)
	list_per_page = 25


admin.site.register(LeadFollowup, LeadFollowupAdmin)


class LeadMeetingScheduleAdmin(admin.ModelAdmin):
	list_display = ('lead', 'schedule_start_datetime', 'schedule_end_datetime', 'status', 'created_at')
	list_filter = ('status',)
	search_fields = ('lead__lead_unique_id', 'schedule_remark', 'new_requirement')
	raw_id_fields = ('lead',)
	list_per_page = 25


admin.site.register(LeadMeetingSchedule, LeadMeetingScheduleAdmin)


class LeadCommissionSlabAdmin(admin.ModelAdmin):
	list_display = ('lead', 'lead_commission_type', 'commission_amount', 'created_at')
	list_filter = ('lead_commission_type',)
	search_fields = ('lead__lead_unique_id',)
	raw_id_fields = ('lead',)
	list_per_page = 25


admin.site.register(LeadCommissionSlab, LeadCommissionSlabAdmin)


# Integrate UserProfile with the Django User admin
User = get_user_model()

class UserProfileInline(admin.StackedInline):
	model = UserProfile
	can_delete = False
	verbose_name_plural = 'Profiles'
	fk_name = 'user'


class CustomUserAdmin(DefaultUserAdmin):
	inlines = (UserProfileInline,)


try:
	admin.site.unregister(User)
except Exception:
	pass

admin.site.register(User, CustomUserAdmin)
