from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.http import HttpResponse, JsonResponse
from django.utils.html import escape
from django.utils.encoding import smart_str
import csv
import io
from django.contrib.auth import get_user_model
from .forms import LocationForm, CompanyForm, PartnerForm, LeadForm, UserRegistrationForm, EditUserForm
from .models import Location, Company, Partner, Lead, LeadPartner, UserProfile, Client, LeadCommissionSlab, LeadBilling


def _save_lead_billing_from_post(lead, post):
	"""Parse wizard POST data and create/update LeadBilling rows for the given lead.

	This function is defensive: parsing errors are swallowed so the main lead
	save doesn't fail because of billing parsing problems.
	"""
	try:
		lead_for_val = (post.get('lead_for') or '').strip()
		# If no lead_for provided, skip billing processing
		if not lead_for_val:
			return

		# Prevent partial AJAX saves (e.g. switching wizard tabs) from clearing
		# existing LeadBilling rows. Require at least one billing-related field
		# to be present and non-empty in the POST before processing billing.
		billing_fields = [
			'is_peremp_wise','emp_count','peremp_amount','another_amount','amount',
			'is_peremp_wise_software','emp_count_software','peremp_amount_software','another_amount_software',
			'another_amount_hardware','is_peremp_wise_hardware','emp_count_hardware','peremp_amount_hardware'
		]
		has_billing = False
		for k in billing_fields:
			try:
				vals = post.getlist(k)
			except Exception:
				vals = [post.get(k)]
			for v in vals:
				if v is None:
					continue
				if isinstance(v, str):
					if v.strip() == '':
						continue
					has_billing = True
					break
				else:
					has_billing = True
					break
			if has_billing:
				break
		if not has_billing:
			# nothing meaningful posted for billing - skip processing to preserve existing rows
			return
		from decimal import Decimal
		def parse_bool(v):
			if v is None: return False
			try:
				return str(v).strip().lower() in ('1', 'true', 'on', 'yes')
			except Exception:
				return False

		desired = []
		# combined software+hardware
		if lead_for_val == LeadCommissionSlab.LEAD_FOR_SOFTWARE_HARDWARE or (('software' in lead_for_val.lower()) and ('hardware' in lead_for_val.lower())):
			# software
			is_peremp_sw = parse_bool(post.get('is_peremp_wise_software'))
			try:
				emp_count_parsed_sw = int(post.get('emp_count_software')) if post.get('emp_count_software') not in (None, '') else None
			except Exception:
				emp_count_parsed_sw = None
			try:
				peremp_amount_parsed_sw = int(post.get('peremp_amount_software')) if post.get('peremp_amount_software') not in (None, '') else None
			except Exception:
				peremp_amount_parsed_sw = None
			another_amount_parsed_sw = None
			try:
				av = post.get('another_amount_software')
				if av not in (None, ''):
					another_amount_parsed_sw = Decimal(str(av))
			except Exception:
				another_amount_parsed_sw = None
			# compute total_sw
			try:
				total_sw = None
				if is_peremp_sw and emp_count_parsed_sw is not None and peremp_amount_parsed_sw is not None:
					total_sw = Decimal(emp_count_parsed_sw) * Decimal(peremp_amount_parsed_sw)
					if another_amount_parsed_sw is not None:
						total_sw += Decimal(another_amount_parsed_sw)
				else:
					if another_amount_parsed_sw is not None:
						total_sw = Decimal(another_amount_parsed_sw)
					else:
						amt_val_sw = post.get('amount_software') or post.get('amount_sw') or post.get('amount')
						if amt_val_sw not in (None, ''):
							try:
								total_sw = Decimal(str(amt_val_sw))
							except Exception:
								total_sw = None
			except Exception:
				total_sw = None

			# hardware
			is_peremp_hw = parse_bool(post.get('is_peremp_wise_hardware'))
			try:
				emp_count_parsed_hw = int(post.get('emp_count_hardware')) if post.get('emp_count_hardware') not in (None, '') else None
			except Exception:
				emp_count_parsed_hw = None
			try:
				peremp_amount_parsed_hw = int(post.get('peremp_amount_hardware')) if post.get('peremp_amount_hardware') not in (None, '') else None
			except Exception:
				peremp_amount_parsed_hw = None
			another_amount_parsed_hw = None
			try:
				av = post.get('another_amount_hardware')
				if av not in (None, ''):
					another_amount_parsed_hw = Decimal(str(av))
			except Exception:
				another_amount_parsed_hw = None
			# compute total_hw
			try:
				total_hw = None
				if is_peremp_hw and emp_count_parsed_hw is not None and peremp_amount_parsed_hw is not None:
					total_hw = Decimal(emp_count_parsed_hw) * Decimal(peremp_amount_parsed_hw)
					if another_amount_parsed_hw is not None:
						total_hw += Decimal(another_amount_parsed_hw)
				else:
					if another_amount_parsed_hw is not None:
						total_hw = Decimal(another_amount_parsed_hw)
					else:
						amt_val_hw = post.get('amount_hardware') or post.get('amount_hw')
						if amt_val_hw not in (None, ''):
							try:
								total_hw = Decimal(str(amt_val_hw))
							except Exception:
								total_hw = None
			except Exception:
				total_hw = None

			desired.append({
				'lead_for': LeadCommissionSlab.LEAD_FOR_SOFTWARE,
				'is_for_software': True,
				'is_peremp': is_peremp_sw,
				'emp_count': emp_count_parsed_sw,
				'peremp_amount': peremp_amount_parsed_sw,
				'another_amount': another_amount_parsed_sw,
				'amount': total_sw,
			})
			desired.append({
				'lead_for': LeadCommissionSlab.LEAD_FOR_HARDWARE,
				'is_for_software': False,
				'is_peremp': is_peremp_hw,
				'emp_count': emp_count_parsed_hw,
				'peremp_amount': peremp_amount_parsed_hw,
				'another_amount': another_amount_parsed_hw,
				'amount': total_hw,
			})
		else:
			# single lead_for case
			is_peremp = parse_bool(post.get('is_peremp_wise'))
			try:
				emp_count_parsed = int(post.get('emp_count')) if post.get('emp_count') not in (None, '') else None
			except Exception:
				emp_count_parsed = None
			try:
				peremp_amount_parsed = int(post.get('peremp_amount')) if post.get('peremp_amount') not in (None, '') else None
			except Exception:
				peremp_amount_parsed = None
			another_amount_parsed = None
			try:
				av = post.get('another_amount')
				if av not in (None, ''):
					another_amount_parsed = Decimal(str(av))
			except Exception:
				another_amount_parsed = None
			# compute total
			try:
				total = None
				if is_peremp and emp_count_parsed is not None and peremp_amount_parsed is not None:
					total = Decimal(emp_count_parsed) * Decimal(peremp_amount_parsed)
					if another_amount_parsed is not None:
						total += Decimal(another_amount_parsed)
				else:
					if another_amount_parsed is not None:
						total = Decimal(another_amount_parsed)
					else:
						amt_val = post.get('amount')
						if amt_val not in (None, ''):
							try:
								total = Decimal(str(amt_val))
							except Exception:
								total = None
			except Exception:
				total = None

			desired.append({
				'lead_for': lead_for_val,
				'is_for_software': (lead_for_val == LeadCommissionSlab.LEAD_FOR_SOFTWARE),
				'is_peremp': is_peremp,
				'emp_count': emp_count_parsed,
				'peremp_amount': peremp_amount_parsed,
				'another_amount': another_amount_parsed,
				'amount': total,
			})

		# Compare with existing LeadBilling rows and update/create/delete only when needed
		existing_lbs = list(LeadBilling.objects.filter(lead=lead))
		existing_map = { getattr(x, 'lead_for', ''): x for x in existing_lbs }
		to_keep = set()
		created = 0
		updated = 0
		deleted = 0
		from django.db import transaction
		with transaction.atomic():
			for d in desired:
				lf = d.get('lead_for')
				to_keep.add(lf)
				existing = existing_map.get(lf)
				def dec_or_none(v):
					if v is None: return None
					try:
						return Decimal(str(v))
					except Exception:
						return v
				if existing:
					changed = False
					if bool(existing.is_peremp_wise_amount) != bool(d.get('is_peremp')):
						changed = True
					if (existing.emp_count if existing.emp_count is not None else None) != (d.get('emp_count') if d.get('emp_count') is not None else None):
						changed = True
					if (existing.peremp_amount if existing.peremp_amount is not None else None) != (d.get('peremp_amount') if d.get('peremp_amount') is not None else None):
						changed = True
					if dec_or_none(existing.another_amount) != dec_or_none(d.get('another_amount')):
						changed = True
					if dec_or_none(existing.amount) != dec_or_none(d.get('amount')):
						changed = True
					if changed:
						existing.is_for_software = d.get('is_for_software', existing.is_for_software)
						existing.is_peremp_wise_amount = bool(d.get('is_peremp', False))
						existing.emp_count = d.get('emp_count')
						existing.peremp_amount = d.get('peremp_amount')
						existing.another_amount = d.get('another_amount')
						existing.amount = d.get('amount')
						existing.save()
						updated += 1
				else:
					LeadBilling.objects.create(
						lead=lead,
						lead_for=lf,
						is_for_software=d.get('is_for_software', False),
						is_peremp_wise_amount=bool(d.get('is_peremp', False)),
						emp_count=d.get('emp_count'),
						peremp_amount=d.get('peremp_amount'),
						another_amount=d.get('another_amount'),
						amount=d.get('amount')
					)
					created += 1
			# remove any existing billing rows not in desired set
			for ex in existing_lbs:
				if getattr(ex, 'lead_for', None) not in to_keep:
					ex.delete()
	except Exception:
		# swallow errors so lead save isn't blocked
		pass

# Dashboard view
def dashboard(request):
	"""Render the default dashboard page."""
	return render(request, 'dashboard/dashboard.html')

# Location views
def location_list(request):
	"""Render the location list page.

	Also supports server-side export when GET param `export` is present.
	Supported formats: csv, txt, xlsx (Excel via HTML table). PDF is not implemented.
	The client may pass `export_scope=page|all`. For `page` the view will attempt
	to use `page` and `per_page` GET params to slice the queryset; if not present it
	will fall back to exporting all rows.
	"""
	# Support showing drafts or deleted records via GET params
	show_drafts = str(request.GET.get('show_drafts', '')).lower() in ['1', 'true', 'on', 'yes']
	show_deleted = str(request.GET.get('show_deleted', '')).lower() in ['1', 'true', 'on', 'yes']
	if show_deleted:
		# Show only soft-deleted records
		locations = Location.objects.filter(is_deleted=True).order_by('-created_at')
	elif show_drafts:
		locations = Location.objects.filter(is_draft=True, is_deleted=False).order_by('-created_at')
	else:
		locations = Location.objects.filter(is_draft=False, is_deleted=False).order_by('-created_at')

	# Server-side export handling
	export_fmt = str(request.GET.get('export', '')).lower()
	if export_fmt:
		export_scope = str(request.GET.get('export_scope', 'all')).lower()
		# determine queryset slice for page vs all
		qs = locations
		if export_scope == 'page':
			try:
				page = int(request.GET.get('page', '1'))
				per_page = int(request.GET.get('per_page', request.GET.get('per_page', '')) or 0)
			except Exception:
				page = None
				per_page = 0
			if page and per_page:
				start = (page - 1) * per_page
				end = start + per_page
				qs = locations[start:end]

		# collect rows
		rows = []
		for loc in qs:
			rows.append([loc.code, loc.name, loc.status, loc.created_at.strftime('%Y-%m-%d %H:%M')])

		if export_fmt == 'csv':
			resp = HttpResponse(content_type='text/csv')
			resp['Content-Disposition'] = 'attachment; filename="locations.csv"'
			writer = csv.writer(resp)
			writer.writerow(['Code', 'Name', 'Status', 'Created'])
			for r in rows:
				writer.writerow([smart_str(x) for x in r])
			return resp

		if export_fmt == 'txt':
			resp = HttpResponse(content_type='text/plain; charset=utf-8')
			resp['Content-Disposition'] = 'attachment; filename="locations.txt"'
			for r in rows:
				resp.write('\t'.join([smart_str(x) for x in r]) + '\n')
			return resp

		if export_fmt in ('xlsx', 'excel'):
			# Excel can open an HTML table; return as application/vnd.ms-excel
			html = '<table><thead><tr><th>Code</th><th>Name</th><th>Status</th><th>Created</th></tr></thead><tbody>'
			for r in rows:
				row_html = ''.join(['<td>%s</td>' % escape(str(c)) for c in r])
				html += '<tr>%s</tr>' % row_html
			html += '</tbody></table>'
			resp = HttpResponse(html, content_type='application/vnd.ms-excel')
			resp['Content-Disposition'] = 'attachment; filename="locations.xls"'
			return resp

		# PDF not implemented server-side
		resp = HttpResponse('PDF export is not implemented on the server. Please choose CSV or Excel.', content_type='text/plain')
		resp.status_code = 501
		return resp

	return render(request, 'locations/location-list.html', {'locations': locations, 'show_drafts': show_drafts, 'show_deleted': show_deleted})


def add_location(request):
	"""Handle creating or editing a location (publish or draft).

	Supports:
	- GET with `id` query param to load an existing Location into the form
	- POST with `id` form field to update an existing Location
	"""
	location = None
	if request.method == 'POST':
		# Try to find an id in POST (preferred) or GET (fallback)
		loc_id = request.POST.get('id') or request.GET.get('id')
		if loc_id:
			location = get_object_or_404(Location, pk=loc_id, is_deleted=False)
			form = LocationForm(request.POST, instance=location)
		else:
			form = LocationForm(request.POST)

		action = request.POST.get('action')  # 'draft' or 'publish'
		if form.is_valid():
			location = form.save(commit=False)
			location.is_draft = (action == 'draft')
			location.save()
			# Feedback message differs for create vs update
			if loc_id:
				messages.success(request, 'Location updated successfully.')
			else:
				if location.is_draft:
					messages.success(request, 'Location saved as draft.')
				else:
					messages.success(request, 'Location added successfully.')
			return redirect('location_list')
		else:
			messages.error(request, 'Please correct the errors below.')
	else:
		# GET — if id provided, load the instance into the form for editing
		loc_id = request.GET.get('id')
		if loc_id:
			location = get_object_or_404(Location, pk=loc_id, is_deleted=False)
			form = LocationForm(instance=location)
		else:
			form = LocationForm()

	return render(request, 'locations/add-location.html', {'form': form, 'location': location})


@require_POST
def delete_location(request):
	"""Soft-delete a Location by setting `is_deleted=True`.
	Expects: POST with `id` form field.
	"""
	loc_id = request.POST.get('id')
	if not loc_id:
		messages.error(request, 'No location id provided.')
		return redirect('location_list')
	location = get_object_or_404(Location, pk=loc_id)
	if location.is_deleted:
		messages.info(request, 'Location already deleted.')
	else:
		location.is_deleted = True
		location.save()
		messages.success(request, 'Location deleted successfully.')
	return redirect('location_list')


@require_POST
def restore_location(request):
	"""Restore a soft-deleted Location by setting `is_deleted=False`.
	Expects: POST with `id` form field.
	"""
	loc_id = request.POST.get('id')
	if not loc_id:
		messages.error(request, 'No location id provided.')
		return redirect('location_list')
	location = get_object_or_404(Location, pk=loc_id)
	if not location.is_deleted:
		messages.info(request, 'Location is not deleted.')
	else:
		location.is_deleted = False
		location.save()
		messages.success(request, 'Location restored successfully.')
	return redirect('location_list')


# Company views (mirror of Location views)

# Detail view for a single Location
def location_detail(request):
	"""Render details for a single location. Expects GET param `id`."""
	location_id = request.GET.get('id')
	if not location_id:
		messages.error(request, 'No location id provided.')
		return redirect('location_list')
	location = get_object_or_404(Location, pk=location_id)
	return render(request, 'locations/location-detail.html', {'location': location})
def company_list(request):
	"""Render the company list page and support export like locations."""
	show_drafts = str(request.GET.get('show_drafts', '')).lower() in ['1', 'true', 'on', 'yes']
	show_deleted = str(request.GET.get('show_deleted', '')).lower() in ['1', 'true', 'on', 'yes']
	if show_deleted:
		companies = Company.objects.filter(is_deleted=True).order_by('-created_at')
	elif show_drafts:
		companies = Company.objects.filter(is_draft=True, is_deleted=False).order_by('-created_at')
	else:
		companies = Company.objects.filter(is_draft=False, is_deleted=False).order_by('-created_at')

	export_fmt = str(request.GET.get('export', '')).lower()
	if export_fmt:
		export_scope = str(request.GET.get('export_scope', 'all')).lower()
		qs = companies
		if export_scope == 'page':
			try:
				page = int(request.GET.get('page', '1'))
				per_page = int(request.GET.get('per_page', request.GET.get('per_page', '')) or 0)
			except Exception:
				page = None
				per_page = 0
			if page and per_page:
				start = (page - 1) * per_page
				end = start + per_page
				qs = companies[start:end]

		rows = []
		for comp in qs:
			rows.append([comp.code, comp.name, comp.status, comp.created_at.strftime('%Y-%m-%d %H:%M')])

		if export_fmt == 'csv':
			resp = HttpResponse(content_type='text/csv')
			resp['Content-Disposition'] = 'attachment; filename="companies.csv"'
			writer = csv.writer(resp)
			writer.writerow(['Code', 'Name', 'Status', 'Created'])
			for r in rows:
				writer.writerow([smart_str(x) for x in r])
			return resp

		if export_fmt == 'txt':
			resp = HttpResponse(content_type='text/plain; charset=utf-8')
			resp['Content-Disposition'] = 'attachment; filename="companies.txt"'
			for r in rows:
				resp.write('\t'.join([smart_str(x) for x in r]) + '\n')
			return resp

		if export_fmt in ('xlsx', 'excel'):
			html = '<table><thead><tr><th>Code</th><th>Name</th><th>Status</th><th>Created</th></tr></thead><tbody>'
			for r in rows:
				row_html = ''.join(['<td>%s</td>' % escape(str(c)) for c in r])
				html += '<tr>%s</tr>' % row_html
			html += '</tbody></table>'
			resp = HttpResponse(html, content_type='application/vnd.ms-excel')
			resp['Content-Disposition'] = 'attachment; filename="companies.xls"'
			return resp

		resp = HttpResponse('PDF export is not implemented on the server. Please choose CSV or Excel.', content_type='text/plain')
		resp.status_code = 501
		return resp

	return render(request, 'companies/company-list.html', {'companies': companies, 'show_drafts': show_drafts, 'show_deleted': show_deleted})

def company_detail(request):
	"""Render details for a single company. Expects GET param `id`."""
	company_id = request.GET.get('id')
	if not company_id:
		messages.error(request, 'No company id provided.')
		return redirect('company_list')
	company = get_object_or_404(Company, pk=company_id)
	return render(request, 'companies/company-detail.html', {'company': company})


def add_company(request):
	"""Create or edit a Company (publish or draft)."""
	company = None
	if request.method == 'POST':
		company_id = request.POST.get('id') or request.GET.get('id')
		if company_id:
			company = get_object_or_404(Company, pk=company_id, is_deleted=False)
			form = CompanyForm(request.POST, instance=company)
		else:
			form = CompanyForm(request.POST)

		action = request.POST.get('action')
		if form.is_valid():
			company = form.save(commit=False)
			company.is_draft = (action == 'draft')
			company.save()
			form.save_m2m()
			if company_id:
				messages.success(request, 'Company updated successfully.')
			else:
				if company.is_draft:
					messages.success(request, 'Company saved as draft.')
				else:
					messages.success(request, 'Company added successfully.')
			return redirect('company_list')
		else:
			messages.error(request, 'Please correct the errors below.')
	else:
		company_id = request.GET.get('id')
		if company_id:
			company = get_object_or_404(Company, pk=company_id, is_deleted=False)
			form = CompanyForm(instance=company)
		else:
			form = CompanyForm()

	return render(request, 'companies/add-company.html', {'form': form, 'company': company})


@require_POST
def delete_company(request):
	company_id = request.POST.get('id')
	if not company_id:
		messages.error(request, 'No company id provided.')
		return redirect('company_list')
	company = get_object_or_404(Company, pk=company_id)
	if company.is_deleted:
		messages.info(request, 'Company already deleted.')
	else:
		company.is_deleted = True
		company.save()
		messages.success(request, 'Company deleted successfully.')
	return redirect('company_list')


@require_POST
def restore_company(request):
	company_id = request.POST.get('id')
	if not company_id:
		messages.error(request, 'No company id provided.')
		return redirect('company_list')
    
    
	company = get_object_or_404(Company, pk=company_id)
	if not company.is_deleted:
		messages.info(request, 'Company is not deleted.')
	else:
		company.is_deleted = False
		company.save()
		messages.success(request, 'Company restored successfully.')
	return redirect('company_list')


def partner_list(request):
	"""Render the partner list page and support export / draft / deleted filters like companies."""
	show_drafts = str(request.GET.get('show_drafts', '')).lower() in ['1', 'true', 'on', 'yes']
	show_deleted = str(request.GET.get('show_deleted', '')).lower() in ['1', 'true', 'on', 'yes']
	if show_deleted:
		partners = Partner.objects.filter(is_deleted=True).order_by('-created_at')
	elif show_drafts:
		partners = Partner.objects.filter(is_draft=True, is_deleted=False).order_by('-created_at')
	else:
		partners = Partner.objects.filter(is_draft=False, is_deleted=False).order_by('-created_at')

	export_fmt = str(request.GET.get('export', '')).lower()
	if export_fmt:
		export_scope = str(request.GET.get('export_scope', 'all')).lower()
		qs = partners
		if export_scope == 'page':
			try:
				page = int(request.GET.get('page', '1'))
				per_page = int(request.GET.get('per_page', request.GET.get('per_page', '')) or 0)
			except Exception:
				page = None
				per_page = 0
			if page and per_page:
				start = (page - 1) * per_page
				end = start + per_page
				qs = partners[start:end]

		rows = []
		for p in qs:
			# include companies names in export (comma-separated)
			try:
				companies_str = ', '.join([c.name for c in p.companies.all()])
			except Exception:
				companies_str = ''
			rows.append([p.name, p.get_relation_display(), p.status, companies_str, p.email or '', p.created_at.strftime('%Y-%m-%d %H:%M')])

		if export_fmt == 'csv':
			resp = HttpResponse(content_type='text/csv')
			resp['Content-Disposition'] = 'attachment; filename="partners.csv"'
			writer = csv.writer(resp)
			writer.writerow(['Name', 'Relation', 'Status', 'Companies', 'Email', 'Created'])
			for r in rows:
				writer.writerow([smart_str(x) for x in r])
			return resp

		if export_fmt == 'txt':
			resp = HttpResponse(content_type='text/plain; charset=utf-8')
			resp['Content-Disposition'] = 'attachment; filename="partners.txt"'
			for r in rows:
				resp.write('\t'.join([smart_str(x) for x in r]) + '\n')
			return resp

			if export_fmt in ('xlsx', 'excel'):
				html = '<table><thead><tr><th>Name</th><th>Relation</th><th>Status</th><th>Companies</th><th>Email</th><th>Created</th></tr></thead><tbody>'
			for r in rows:
				row_html = ''.join(['<td>%s</td>' % escape(str(c)) for c in r])
				html += '<tr>%s</tr>' % row_html
			html += '</tbody></table>'
			resp = HttpResponse(html, content_type='application/vnd.ms-excel')
			resp['Content-Disposition'] = 'attachment; filename="partners.xls"'
			return resp

		resp = HttpResponse('PDF export is not implemented on the server. Please choose CSV or Excel.', content_type='text/plain')
		resp.status_code = 501
		return resp

	return render(request, 'partners/partner-list.html', {'partners': partners, 'show_drafts': show_drafts, 'show_deleted': show_deleted})


def partner_detail(request):
	"""Render details for a single partner. Expects GET param `id`."""
	partner_id = request.GET.get('id')
	if not partner_id:
		messages.error(request, 'No partner id provided.')
		return redirect('partner_list')
	partner = get_object_or_404(Partner, pk=partner_id)
	return render(request, 'partners/partner-detail.html', {'partner': partner})


def add_partner(request):
	"""Create or edit a Partner (supports draft/publish action)."""
	partner = None
	if request.method == 'POST':
		partner_id = request.POST.get('id') or request.GET.get('id')
		if partner_id:
			partner = get_object_or_404(Partner, pk=partner_id)
			form = PartnerForm(request.POST, instance=partner)
		else:
			form = PartnerForm(request.POST)

		action = request.POST.get('action') or 'publish'
		if form.is_valid():
			partner = form.save(commit=False)
			partner.is_draft = (action == 'draft')
			partner.save()
			# ensure many-to-many relations (companies) are saved
			try:
				form.save_m2m()
			except Exception:
				pass
			if partner_id:
				messages.success(request, 'Partner updated successfully.')
			else:
				if partner.is_draft:
					messages.success(request, 'Partner saved as draft.')
				else:
					messages.success(request, 'Partner added successfully.')
			return redirect('partner_list')
		else:
			messages.error(request, 'Please correct the errors below.')
	else:
		partner_id = request.GET.get('id')
		if partner_id:
			partner = get_object_or_404(Partner, pk=partner_id, is_deleted=False)
			form = PartnerForm(instance=partner)
		else:
			form = PartnerForm()

	return render(request, 'partners/add-partner.html', {'form': form, 'partner': partner})


@require_POST
def delete_partner(request):
	partner_id = request.POST.get('id')
	if not partner_id:
		messages.error(request, 'No partner id provided.')
		return redirect('partner_list')
	partner = get_object_or_404(Partner, pk=partner_id)
	if partner.is_deleted:
		messages.info(request, 'Partner already deleted.')
	else:
		partner.is_deleted = True
		partner.save()
		messages.success(request, 'Partner deleted successfully.')
	return redirect('partner_list')


@require_POST
def restore_partner(request):
	partner_id = request.POST.get('id')
	if not partner_id:
		messages.error(request, 'No partner id provided.')
		return redirect('partner_list')
	partner = get_object_or_404(Partner, pk=partner_id)
	if not partner.is_deleted:
		messages.info(request, 'Partner is not deleted.')
		# Prepare a friendly error response with posted data to aid debugging
		errors = []
		for f, v in form.errors.items():
			for e in v:
				errors.append(f"{f}: {e}")

		# collect posted values (preserve multi-value lists)
		posted = {}
		try:
			for k in request.POST.keys():
				vals = request.POST.getlist(k)
				posted[k] = vals if len(vals) > 1 else (vals[0] if vals else '')
		except Exception:
			posted = {k: request.POST.get(k) for k in request.POST.keys()}

		# log minimal debug info to server console
		try:
			print('create_partner_ajax invalid, errors=', errors, 'posted=', posted)
		except Exception:
			pass

		# As a pragmatic fallback, if form validation failed but minimal required
		# fields are present, try saving a Partner directly so the modal 'Save'
		# works for the user. This helps during development; keep defensive checks.
		try:
			name_val = (request.POST.get('name') or '').strip()
			relation_val = (request.POST.get('relation') or '').strip()
			if name_val and relation_val:
				try:
					partner = Partner.objects.create(
						name=name_val,
						relation=relation_val,
						status=(request.POST.get('status') or Partner.STATUS_ACTIVE),
						email=request.POST.get('email') or None,
						phone=request.POST.get('phone') or '',
						address=request.POST.get('address') or ''
					)
					# attach companies if provided
					try:
						comp_ids = request.POST.getlist('companies')
						if comp_ids:
							companies_qs = Company.objects.filter(pk__in=comp_ids)
							partner.companies.set(companies_qs)
					except Exception:
						pass
					label = f"{partner.name} ({partner.get_relation_display()})"
					return JsonResponse({'ok': True, 'id': partner.id, 'name': label, 'warning': 'created_using_fallback_due_to_validation_errors', 'posted': posted})
				except Exception as e:
					# fallback create failed; fall through to returning errors
					print('create_partner_ajax fallback create failed:', str(e))
		except Exception:
			pass

		return JsonResponse({'ok': False, 'errors': errors, 'posted': posted}, status=400)


def add_lead(request):
	"""Create a Lead using the wizard UI.

	Handles saving the main Lead record and creating LeadPartner links.
	"""
	companies = Company.objects.filter(is_deleted=False, is_draft=False).order_by('-created_at')
	partners_qs = Partner.objects.filter(is_deleted=False, is_draft=False).order_by('-created_at')

	if request.method == 'POST':
		# detect AJAX partial-save from the wizard
		is_ajax = (request.headers.get('x-requested-with') == 'XMLHttpRequest') or (str(request.POST.get('ajax') or '').lower() in ['1', 'true'])
		lead_instance = None
		# make a mutable copy of POST so we can map wizard-only field names
		post_data = request.POST.copy()
		# Normalize keys coming from some JS plugins which use `name[]` for multiselects
		# (e.g. `companies[]`) — map them to the expected form field name (`companies`).
		try:
			for k in list(post_data.keys()):
				if k.endswith('[]'):
					base = k[:-2]
					vals = post_data.getlist(k)
					# merge into existing base key if present, else set
					if post_data.getlist(base):
						post_data.setlist(base, post_data.getlist(base) + vals)
					else:
						post_data.setlist(base, vals)
					# remove the bracketed key
					try:
						del post_data[k]
					except Exception:
						pass
		except Exception:
			# defensive: don't let normalization break the request handling
			pass
		lead_id_post = post_data.get('lead_id') or post_data.get('leadId')
		# map wizard field `leadName` to ModelForm expected `name` so validation succeeds
		if post_data.get('leadName') and not post_data.get('name'):
			post_data['name'] = post_data.get('leadName')
		if lead_id_post:
			try:
				lead_instance = Lead.objects.get(pk=lead_id_post)
			except Lead.DoesNotExist:
				lead_instance = None

		form = LeadForm(post_data, instance=lead_instance)

		# handle raw inputs from wizard (not part of the ModelForm fields)
		lead_name = post_data.get('leadName')
		# Compute which POST keys actually carried non-empty values. Treat
		# blank strings/whitespace as not-provided so AJAX partial-saves don't
		# accidentally clear existing fields (fixes name being removed when
		# navigating wizard steps).
		def _posted_nonempty_keys(pdata):
			keys = set()
			try:
				for k in pdata.keys():
					try:
						vals = pdata.getlist(k)
					except Exception:
						vals = [pdata.get(k)]
					has_value = False
					for v in vals:
						if v is None:
							continue
						if isinstance(v, str):
							if v.strip() == '':
								continue
							has_value = True
							break
						else:
							has_value = True
							break
					if has_value:
						keys.add(k)
			except Exception:
				pass
			return keys

		posted_nonempty = _posted_nonempty_keys(post_data)

		if form.is_valid():
			lead = form.save(commit=False)
			# prefer explicit wizard field if provided
			if lead_name:
				lead.name = lead_name.strip()

			# If this is an AJAX partial-save, avoid clearing fields that were not
			# actually provided (or were provided as blank) in the POST payload.
			if is_ajax and lead_instance:
				# Preserve scalar fields that were not actually provided with values
				for field_name in ('client', 'assign_user', 'approval_user', 'status', 'is_draft', 'is_approved', 'name'):
					if field_name not in posted_nonempty:
						try:
							setattr(lead, field_name, getattr(lead_instance, field_name))
						except Exception:
							pass
				# Extra guard: never overwrite an existing non-empty lead.name with
				# an empty/whitespace value from a partial AJAX save. Only accept a
				# name change when the client posted a non-empty `leadName` or
				# `name` key (present in posted_nonempty).
				try:
					if ('name' not in posted_nonempty) and ('leadName' not in posted_nonempty):
						lead.name = getattr(lead_instance, 'name')
				except Exception:
					pass

			# Determine client object: prefer ModelForm `client`, otherwise fallback to wizard text input
			client_obj = None
			try:
				client_obj = form.cleaned_data.get('client')
			except Exception:
				client_obj = None
			if not client_obj:
				client_name = post_data.get('clientName')
				if client_name:
					client_name_clean = client_name.strip()
					if client_name_clean:
						client_obj = Client.objects.filter(name__iexact=client_name_clean).first()
						if not client_obj:
							client_obj = Client.objects.create(name=client_name_clean)

			# Preserve status: if user provided a non-empty status use it;
			# otherwise keep existing lead status (for updates) or model default (for new leads)
			status_val = form.cleaned_data.get('status')
			if status_val and str(status_val).strip() != '':
				lead.status = status_val
			else:
				if lead_instance:
					lead.status = lead_instance.status
				else:
					lead.status = Lead._meta.get_field('status').get_default()

			# assign sales person if selected (form field `sales_person`)
			sales_user = form.cleaned_data.get('sales_person')
			if sales_user:
				lead.assign_user = sales_user

			# handle draft flag from wizard draft button
			if str(post_data.get('is_draft') or '').strip() in ('1', 'true'):
				lead.is_draft = True

			lead.save()
			# persist wizard current step if provided (saved from JS or form)
			last_step = post_data.get('last_step') or post_data.get('wizard_step') or post_data.get('current_step') or post_data.get('step')
			if last_step:
				try:
					lead.last_wizard_step = int(last_step)
				except Exception:
					pass

			# Save the lead instance first (commit scalar fields)
			lead.save()

			# save many-to-many relations (companies).
			# For AJAX partial-saves we avoid clearing relations that were not posted;
			# but for full (non-AJAX) POSTs we must persist companies even when empty
			# so removals are reflected in the intermediate table.
			# consider companies posted only when a non-empty companies key exists
			companies_posted = any(k.startswith('companies') for k in posted_nonempty)
			if (not is_ajax) or companies_posted:
				try:
					form.save_m2m()
				except Exception:
					pass

			# Ensure last_wizard_step persisted after m2m save
			if last_step:
				try:
					lead.last_wizard_step = int(last_step)
					lead.save()
				except Exception:
					pass

			# Update LeadPartner links only when the partner field was included in the POST
			# (this avoids clearing partner links during AJAX partial-saves that did
			# not include the partner select). When posted:
			# - if a partner is selected: ensure only that partner link exists for the lead
			# - if no partner selected: remove all partner links for the lead
			partner_selected = form.cleaned_data.get('partner')
			try:
				partner_posted = any(k.startswith('partner') for k in posted_nonempty)
			except Exception:
				partner_posted = False
			if partner_posted:
				try:
					if partner_selected:
						# create or keep the selected partner link and remove others
						LeadPartner.objects.get_or_create(lead=lead, partner=partner_selected)
						LeadPartner.objects.filter(lead=lead).exclude(partner=partner_selected).delete()
					else:
						# explicit empty selection -> remove all partner links
						LeadPartner.objects.filter(lead=lead).delete()
				except Exception:
					pass

			# link client to lead if provided
			if client_obj:
				lead.client = client_obj
				lead.save()

			# Persist lead billing info (lead_for, is_peremp_wise) into LeadBilling table.
			# Use the normalized `post_data` (handles `name[]` keys) so the billing
			# parser receives the same data we validated with the form.
			try:
				_save_lead_billing_from_post(lead, post_data)
			except Exception:
				# swallow errors so lead save isn't blocked
				pass

			# Persist commission slabs associated with each LeadBilling row.
			# Expect POST names like `commission_type_<billing_id>`; fall back to
			# `commission_type_<lead_for>` or single `commission_type` when present.
			try:
				for lb in LeadBilling.objects.filter(lead=lead).order_by('id'):
					key_id = f'commission_type_{getattr(lb, "id", "")}'
					key_lf = f'commission_type_{(getattr(lb, "lead_for", "") or "").strip()}'
					ct = ''
					try:
						ct = (post_data.get(key_id) or post_data.get(key_lf) or post_data.get('commission_type') or '')
						ct = (ct or '').strip()
					except Exception:
						ct = ''
					# find existing slab for this billing
					slab = LeadCommissionSlab.objects.filter(lead=lead, lead_billing=lb).first()
					if slab:
						if ct:
							if slab.lead_commission_type != ct:
								slab.lead_commission_type = ct
								slab.save()
						# else: keep existing slab if user didn't post anything
					else:
						if ct:
							# create with a sane default for credit term
							LeadCommissionSlab.objects.create(
								lead=lead,
								lead_commission_type=ct,
								lead_commission_credit_term_condition=LeadCommissionSlab.CREDIT_AFTER_BILLING,
								lead_billing=lb
							)
			except Exception:
				# swallow errors so lead save isn't blocked
				pass

			# If this was an AJAX partial save, return JSON with the lead id
			if is_ajax:
				try:
					# include posted keys to aid debugging of missing fields from the wizard
					try:
						posted_keys_list = sorted(list(post_data.keys()))
					except Exception:
						posted_keys_list = []
					# include billing rows so client can verify what persisted
					billing_rows = []
					try:
						for b in LeadBilling.objects.filter(lead=lead).order_by('id'):
							# include slab info when available so client can pre-select
							try:
								slab = LeadCommissionSlab.objects.filter(lead=lead, lead_billing=b).first()
							except Exception:
								slab = None
							billing_rows.append({
								'id': getattr(b, 'id', None),
								'lead_for': b.lead_for,
								'is_for_software': bool(b.is_for_software),
								'is_peremp_wise_amount': bool(b.is_peremp_wise_amount),
								'emp_count': b.emp_count,
								'peremp_amount': b.peremp_amount,
								'another_amount': str(b.another_amount) if b.another_amount is not None else None,
								'amount': str(b.amount) if b.amount is not None else None,
								'commission_type': getattr(slab, 'lead_commission_type', '') if slab else '',
								'commission_amount': getattr(slab, 'commission_amount', None) if slab else None,
								'slab_id': getattr(slab, 'id', None) if slab else None,
							})
					except Exception:
						billing_rows = []
					return JsonResponse({'ok': True, 'lead_id': lead.id, 'saved_step': getattr(lead, 'last_wizard_step', None), 'posted_keys': posted_keys_list, 'billing': billing_rows})
				except Exception:
					# best-effort: still include billing snapshot
					billing_rows = []
					try:
						for b in LeadBilling.objects.filter(lead=lead).order_by('id'):
							try:
								slab = LeadCommissionSlab.objects.filter(lead=lead, lead_billing=b).first()
							except Exception:
								slab = None
							billing_rows.append({
								'id': getattr(b, 'id', None),
								'lead_for': b.lead_for,
								'is_for_software': bool(b.is_for_software),
								'is_peremp_wise_amount': bool(b.is_peremp_wise_amount),
								'emp_count': b.emp_count,
								'peremp_amount': b.peremp_amount,
								'another_amount': str(b.another_amount) if b.another_amount is not None else None,
								'amount': str(b.amount) if b.amount is not None else None,
								'commission_type': getattr(slab, 'lead_commission_type', '') if slab else '',
								'commission_amount': getattr(slab, 'commission_amount', None) if slab else None,
								'slab_id': getattr(slab, 'id', None) if slab else None,
							})
					except Exception:
						billing_rows = []
					return JsonResponse({'ok': True, 'lead_id': lead.id, 'billing': billing_rows})
			messages.success(request, 'Lead saved successfully.')
			return redirect('lead_list')
		else:
			# form invalid
			if is_ajax:
				# collect simple error messages to return to the client
				errors = []
				for f, v in form.errors.items():
					for e in v:
						errors.append(f"{f}: {e}")
				# include non-field errors
				for e in form.non_field_errors():
					errors.append(str(e))
				return JsonResponse({'ok': False, 'errors': errors}, status=400)
			messages.error(request, 'Please correct the errors below.')
	else:
		# If `id` query param provided, load existing Lead for editing so the form is pre-filled
		lead = None
		lead_id = request.GET.get('id') or request.GET.get('lead_id')
		if lead_id:
			try:
				lead = Lead.objects.get(pk=lead_id)
			except Lead.DoesNotExist:
				lead = None
		if lead:
			initial = {}
			# pre-select first partner if any
			try:
				first_partner_link = lead.partner_links.first()
				if first_partner_link:
					initial['partner'] = first_partner_link.partner.id
			except Exception:
				pass
			# pre-select sales person from assign_user
			try:
				if lead.assign_user:
					initial['sales_person'] = lead.assign_user.id
			except Exception:
				pass
			form = LeadForm(instance=lead, initial=initial)
		else:
			form = LeadForm()

	# determine selected lead_for value for template (prefer POST, otherwise derive from LeadBilling rows)
	selected_lead_for = ''
	selected_is_peremp_wise = False

	# initialize template variables used by billing UI with safe defaults
	selected_peremp_amount = 0
	selected_emp_count = 0
	selected_another_amount = 0
	# selected commission type (populated from POST or existing LeadCommissionSlab)
	selected_commission_type = ''
	selected_is_peremp_wise_software = False
	selected_peremp_amount_software = 0
	selected_emp_count_software = 0
	selected_another_amount_software = 0
	selected_another_amount_hardware = 0

	try:
		if request.method == 'POST':
			# prefer values from POST when available (keeps wizard behaviour intact)
			selected_lead_for = (request.POST.get('lead_for') or '').strip()
			val = request.POST.get('is_peremp_wise')
			if val is not None and str(val).strip().lower() in ('1', 'true', 'on', 'yes'):
				selected_is_peremp_wise = True
			# copy POSTed billing fields so redisplay keeps values
			try:
				if request.POST.get('peremp_amount') is not None:
					selected_peremp_amount = request.POST.get('peremp_amount')
				if request.POST.get('emp_count') is not None:
					selected_emp_count = request.POST.get('emp_count')
				if request.POST.get('another_amount') is not None:
					selected_another_amount = request.POST.get('another_amount')
				if request.POST.get('is_peremp_wise_software') is not None:
					selected_is_peremp_wise_software = str(request.POST.get('is_peremp_wise_software')).strip().lower() in ('1', 'true', 'on', 'yes')
				if request.POST.get('peremp_amount_software') is not None:
					selected_peremp_amount_software = request.POST.get('peremp_amount_software')
				if request.POST.get('emp_count_software') is not None:
					selected_emp_count_software = request.POST.get('emp_count_software')
				if request.POST.get('another_amount_software') is not None:
					selected_another_amount_software = request.POST.get('another_amount_software')
				if request.POST.get('another_amount_hardware') is not None:
					selected_another_amount_hardware = request.POST.get('another_amount_hardware')
				# commission type posted from the commission tab
				if request.POST.get('commission_type') is not None:
					selected_commission_type = (request.POST.get('commission_type') or '').strip()
			except Exception:
				pass
		else:
			# derive values from LeadBilling rows when editing an existing lead
			if lead:
				try:
					lbs = list(LeadBilling.objects.filter(lead=lead))
					if lbs:
						has_sw = any(('software' in (getattr(x, 'lead_for', '') or '').lower()) for x in lbs)
						has_hw = any(('hardware' in (getattr(x, 'lead_for', '') or '').lower()) for x in lbs)
						if has_sw and has_hw:
							selected_lead_for = LeadCommissionSlab.LEAD_FOR_SOFTWARE_HARDWARE
						elif has_sw:
							selected_lead_for = LeadCommissionSlab.LEAD_FOR_SOFTWARE
						elif has_hw:
							selected_lead_for = LeadCommissionSlab.LEAD_FOR_HARDWARE
						else:
							selected_lead_for = getattr(lbs[0], 'lead_for', '') or ''
						# populate per-item values
						for b in lbs:
							lf = (getattr(b, 'lead_for', '') or '').lower()
							if 'software' in lf:
								selected_is_peremp_wise_software = bool(getattr(b, 'is_peremp_wise_amount', False))
								selected_peremp_amount_software = getattr(b, 'peremp_amount', 0) or 0
								selected_emp_count_software = getattr(b, 'emp_count', 0) or 0
								selected_another_amount_software = getattr(b, 'another_amount', 0) or 0
								# mirror into single-fields when only software present
								selected_is_peremp_wise = selected_is_peremp_wise_software
								selected_peremp_amount = selected_peremp_amount_software
								selected_emp_count = selected_emp_count_software
								selected_another_amount = selected_another_amount_software
							elif 'hardware' in lf:
								selected_another_amount_hardware = getattr(b, 'another_amount', 0) or 0
								# mirror for single hardware-only case
								selected_another_amount = selected_another_amount_hardware
				except Exception:
					# swallow and continue with defaults
					pass
					# try to derive existing selected commission type from LeadCommissionSlab rows
					try:
						lcs = LeadCommissionSlab.objects.filter(lead=lead)
						if lcs:
							first = lcs.first()
							if first and getattr(first, 'lead_commission_type', None):
								selected_commission_type = getattr(first, 'lead_commission_type') or ''
					except Exception:
						pass
	except Exception:
		selected_lead_for = ''
		selected_is_peremp_wise = False

	# Build billing rows for template (one slot per LeadBilling row)
	lead_billing_rows = []
	try:
		if lead:
			for lb in LeadBilling.objects.filter(lead=lead).order_by('id'):
				try:
					slab = LeadCommissionSlab.objects.filter(lead=lead, lead_billing=lb).first()
				except Exception:
					slab = None
				lead_billing_rows.append({
					'id': getattr(lb, 'id', None),
					'lead_for': getattr(lb, 'lead_for', ''),
					'is_for_software': bool(getattr(lb, 'is_for_software', False)),
					'is_peremp': bool(getattr(lb, 'is_peremp_wise_amount', False)),
					'emp_count': getattr(lb, 'emp_count', None),
					'peremp_amount': getattr(lb, 'peremp_amount', None),
					'another_amount': getattr(lb, 'another_amount', None),
					'amount': getattr(lb, 'amount', None),
					'commission_type': getattr(slab, 'lead_commission_type', '') if slab else '',
					'commission_amount': getattr(slab, 'commission_amount', None) if slab else None,
					'slab_id': getattr(slab, 'id', None) if slab else None,
				})
	except Exception:
		lead_billing_rows = []

	return render(request, 'leads/add-lead-wizard.html', {
		'form': form,
		'companies': companies,
		'partners': partners_qs,
		'lead': lead,
		'initial_wizard_step': (lead.last_wizard_step if lead else 1),
		'lead_for_choices': LeadCommissionSlab.LEAD_FOR_CHOICES,
		'selected_lead_for': selected_lead_for,
		'selected_is_peremp_wise': selected_is_peremp_wise,
		# commission choices pulled from model
		'commission_type_choices': LeadCommissionSlab.TYPE_CHOICES,
		'selected_commission_type': selected_commission_type,
		'lead_billing_rows': lead_billing_rows,
		# billing template values (populated from POST or LeadBilling rows)
		'selected_peremp_amount': selected_peremp_amount,
		'selected_emp_count': selected_emp_count,
		'selected_another_amount': selected_another_amount,
		'selected_is_peremp_wise_software': selected_is_peremp_wise_software,
		'selected_peremp_amount_software': selected_peremp_amount_software,
		'selected_emp_count_software': selected_emp_count_software,
		'selected_another_amount_software': selected_another_amount_software,
		'selected_another_amount_hardware': selected_another_amount_hardware,
		'partner_relations': Partner.RELATION_CHOICES,
		'partner_status_choices': Partner.STATUS_CHOICES,
	})


@require_POST
def create_client_ajax(request):
	"""AJAX endpoint to create a Client record.

	Expects POST with 'name'. Returns JSON {ok: True, id: <id>, name: <name>}.
	If client with same name exists (case-insensitive) it will return that existing client.
	"""
	name = (request.POST.get('name') or '').strip()
	if not name:
		return JsonResponse({'ok': False, 'errors': ['Client name is required.']}, status=400)
	try:
		client = Client.objects.filter(name__iexact=name).first()
		if client:
			return JsonResponse({'ok': True, 'id': client.id, 'name': client.name, 'exists': True})
		client = Client.objects.create(name=name)
		return JsonResponse({'ok': True, 'id': client.id, 'name': client.name, 'exists': False})
	except Exception as e:
		return JsonResponse({'ok': False, 'errors': [str(e)]}, status=500)


@require_POST
def create_sales_person_ajax(request):
	"""AJAX endpoint to create a new user (sales person).

	Expects POST: username, password1, password2, first_name, last_name, email.
	Returns JSON {ok: True, id: <id>, name: <label>}.
	"""
	user_model = get_user_model()
	username = (request.POST.get('username') or '').strip()
	password1 = request.POST.get('password1') or ''
	password2 = request.POST.get('password2') or ''
	first_name = (request.POST.get('first_name') or '').strip()
	last_name = (request.POST.get('last_name') or '').strip()
	email = (request.POST.get('email') or '').strip()

	errors = []
	if not username:
		errors.append('Username is required.')
	elif user_model.objects.filter(username__iexact=username).exists():
		errors.append('A user with this username already exists.')
	if not password1:
		errors.append('Password is required.')
	elif password1 != password2:
		errors.append('Passwords do not match.')

	if errors:
		return JsonResponse({'ok': False, 'errors': errors}, status=400)

	try:
		user = user_model(username=username, first_name=first_name, last_name=last_name, email=email, is_active=True)
		user.set_password(password1)
		user.save()
		full = user.get_full_name() or ''
		label = f"{user.username} ({full})" if full else user.username
		return JsonResponse({'ok': True, 'id': user.id, 'name': label})
	except Exception as e:
		return JsonResponse({'ok': False, 'errors': [str(e)]}, status=500)


@require_POST
def create_partner_ajax(request):
	"""AJAX endpoint to create a Partner record using PartnerForm for validation."""
	# Use PartnerForm to validate and save
	data = request.POST.copy()
	# Ensure companies can come as multiple values
	form = None
	try:
		form = PartnerForm(data)
	except Exception:
		return JsonResponse({'ok': False, 'errors': ['Invalid data provided.']}, status=400)

	if form.is_valid():
		try:
			partner = form.save(commit=False)
			partner.is_draft = False
			partner.save()
			try:
				form.save_m2m()
			except Exception:
				pass
			label = f"{partner.name} ({partner.get_relation_display()})"
			return JsonResponse({'ok': True, 'id': partner.id, 'name': label})
		except Exception as e:
			return JsonResponse({'ok': False, 'errors': [str(e)]}, status=500)
	else:
		errors = []
		for f, v in form.errors.items():
			for e in v:
				errors.append(f"{f}: {e}")
		return JsonResponse({'ok': False, 'errors': errors}, status=400)


def lead_list(request):
	"""Render a simple list of Leads with optional draft/deleted filters."""
	show_drafts = str(request.GET.get('show_drafts', '')).lower() in ['1', 'true', 'on', 'yes']
	show_deleted = str(request.GET.get('show_deleted', '')).lower() in ['1', 'true', 'on', 'yes']
	if show_deleted:
		qs = Lead.objects.filter(is_delete=True)
	elif show_drafts:
		qs = Lead.objects.filter(is_draft=True, is_delete=False)
	else:
		qs = Lead.objects.filter(is_draft=False, is_delete=False)

	# Prefetch/select related for template performance and to access related names in template
	leads = qs.select_related('assign_user', 'client').prefetch_related('companies', 'partner_links__partner').order_by('-created_at')

	return render(request, 'leads/list.html', {'leads': leads, 'show_drafts': show_drafts, 'show_deleted': show_deleted})


@require_POST
def delete_lead(request):
	"""Soft-delete a Lead by setting `is_delete=True`.
	Expects: POST with `id` form field.
	"""
	lead_id = request.POST.get('id')
	if not lead_id:
		messages.error(request, 'No lead id provided.')
		return redirect('lead_list')
	lead = get_object_or_404(Lead, pk=lead_id)
	if lead.is_delete:
		messages.info(request, 'Lead already deleted.')
	else:
		lead.is_delete = True
		lead.save()
		messages.success(request, 'Lead deleted successfully.')
	return redirect('lead_list')


@require_POST
def restore_lead(request):
	"""Restore a soft-deleted Lead by setting `is_delete=False`.
	Expects: POST with `id` form field.
	"""
	lead_id = request.POST.get('id')
	if not lead_id:
		messages.error(request, 'No lead id provided.')
		return redirect('lead_list')
	lead = get_object_or_404(Lead, pk=lead_id)
	if not lead.is_delete:
		messages.info(request, 'Lead is not deleted.')
	else:
		lead.is_delete = False
		lead.save()
		messages.success(request, 'Lead restored successfully.')
	return redirect('lead_list')


def user_list(request):
	"""Render the user list page and support showing inactive users and drafts via GET params."""
	show_deleted = str(request.GET.get('show_deleted', '')).lower() in ['1', 'true', 'on', 'yes']
	show_drafts = str(request.GET.get('show_drafts', '')).lower() in ['1', 'true', 'on', 'yes']
	User = get_user_model()
	if show_deleted:
		users = User.objects.filter(is_active=False).order_by('-date_joined')
	elif show_drafts:
		users = User.objects.filter(profile__is_draft=True).order_by('-date_joined')
	else:
		users = User.objects.filter(is_active=True, profile__is_draft=False).order_by('-date_joined')
	return render(request, 'users/user-list.html', {'users': users, 'show_deleted': show_deleted, 'show_drafts': show_drafts})


def user_detail(request):
	user_id = request.GET.get('id')
	if not user_id:
		messages.error(request, 'No user id provided.')
		return redirect('user_list')
	user_obj = get_object_or_404(get_user_model(), pk=user_id)
def add_user(request):
	user_obj = None
	if request.method == 'POST':
		form = UserRegistrationForm(request.POST)
		action = request.POST.get('action') or 'publish'
		if form.is_valid():
			user = form.save()
			# mark profile as draft/published
			try:
				profile = user.profile
			except Exception:
				profile = None
			if profile is not None:
				profile.is_draft = (action == 'draft')
				profile.save()
			if action == 'draft':
				messages.success(request, 'User saved as draft.')
			else:
				messages.success(request, 'User added successfully.')
			return redirect('user_list')
		else:
			messages.error(request, 'Please correct the errors below.')
	else:
		form = UserRegistrationForm()
	return render(request, 'users/add-user.html', {'form': form, 'user_obj': user_obj})


def edit_user(request):
	user_id = request.POST.get('id') or request.GET.get('id')
	if not user_id:
		messages.error(request, 'No user id provided.')
		return redirect('user_list')
	User = get_user_model()
	user_obj = get_object_or_404(User, pk=user_id)
	if request.method == 'POST':
		form = EditUserForm(request.POST, instance=user_obj)
		if form.is_valid():
			# save form and get the updated user
			user = form.save()
			# toggle draft state if action provided
			action = request.POST.get('action') or 'publish'
			# fetch a fresh profile instance to avoid overwriting fields
			profile, _ = UserProfile.objects.get_or_create(user=user)
			profile.is_draft = (action == 'draft')
			profile.save()
			messages.success(request, 'User updated successfully.')
			return redirect('user_list')
		else:
			messages.error(request, 'Please correct the errors below.')
	else:
		profile = getattr(user_obj, 'profile', None)
		initial = {}
		if profile:
			initial['middle_name'] = profile.middle_name
			initial['phone'] = profile.phone
			# populate initial many-to-many selections
			initial['locations'] = list(profile.locations.values_list('id', flat=True))
			initial['companies'] = list(profile.companies.values_list('id', flat=True))

		# set initial status from user active flag
		initial['status'] = 'active' if user_obj.is_active else 'inactive'
		form = EditUserForm(instance=user_obj, initial=initial)
	return render(request, 'users/add-user.html', {'form': form, 'user_obj': user_obj})


@require_POST
def delete_user(request):
	user_id = request.POST.get('id')
	if not user_id:
		messages.error(request, 'No user id provided.')
		return redirect('user_list')
	user_obj = get_object_or_404(get_user_model(), pk=user_id)
	if not user_obj.is_active:
		messages.info(request, 'User already inactive.')
	else:
		user_obj.is_active = False
		user_obj.save()
		messages.success(request, 'User deactivated successfully.')
	return redirect('user_list')


@require_POST
def restore_user(request):
	user_id = request.POST.get('id')
	if not user_id:
		messages.error(request, 'No user id provided.')
		return redirect('user_list')
	user_obj = get_object_or_404(get_user_model(), pk=user_id)
	if user_obj.is_active:
		messages.info(request, 'User is already active.')
	else:
		user_obj.is_active = True
		user_obj.save()
		messages.success(request, 'User restored successfully.')
	return redirect('user_list')

