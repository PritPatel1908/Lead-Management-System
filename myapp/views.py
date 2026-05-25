from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.http import HttpResponse, JsonResponse
from django.utils.html import escape
from django.utils.encoding import smart_str
import csv
import io
from django.contrib.auth import get_user_model, authenticate, login
from django.views.decorators.csrf import csrf_protect
from django.conf import settings
from .forms import LocationForm, CompanyForm, PartnerForm, LeadForm, UserRegistrationForm, EditUserForm, ProductForm
from .models import Location, Company, Partner, Lead, LeadPartner, UserProfile, Client, LeadCommissionSlab, LeadBilling, Product, LeadBillingProduct


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
			'another_amount_hardware','is_peremp_wise_hardware','emp_count_hardware','peremp_amount_hardware',
			'bill_type','custome_month','bill_type_software','custome_month_software','bill_type_hardware','custome_month_hardware'
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
		# existing billing rows map (by lead_for) - used to read id-specific POST keys
		existing_lbs = list(LeadBilling.objects.filter(lead=lead))
		existing_map_by_lead_for = { getattr(x, 'lead_for', ''): x for x in existing_lbs }

		# helper: detect whether any of the provided POST keys contain a meaningful value
		def _post_has_value(*keys):
			for k in keys:
				try:
					v = post.get(k)
				except Exception:
					v = None
				if v is None:
					continue
				try:
					if str(v).strip() != '':
						return True
				except Exception:
					return True
			return False
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

			# try to parse bill_type and custom month for software (several possible input names)
			bill_type_sw = (post.get('bill_type_software') or post.get('bill_type') or post.get('bill_type_sw'))
			try:
				lb_sw = existing_map_by_lead_for.get(LeadCommissionSlab.LEAD_FOR_SOFTWARE)
				if lb_sw:
					bill_type_sw = post.get(f'bill_type_{getattr(lb_sw, "id", "")}') or bill_type_sw
			except Exception:
				pass
			custome_month_sw = None
			try:
				cm = post.get('custome_month_software') or post.get('custome_month') or post.get('custome_month_sw')
				if cm not in (None, ''):
					custome_month_sw = int(cm)
			except Exception:
				custome_month_sw = None

			desired.append({
				'lead_for': LeadCommissionSlab.LEAD_FOR_SOFTWARE,
				'is_for_software': True,
				'is_peremp': is_peremp_sw,
				'emp_count': emp_count_parsed_sw,
				'peremp_amount': peremp_amount_parsed_sw,
				'another_amount': another_amount_parsed_sw,
				'amount': total_sw,
				# presence flags: only persist/update these fields when non-empty values were posted
				'provided_is_peremp': _post_has_value('is_peremp_wise_software'),
				'provided_emp_count': _post_has_value('emp_count_software'),
				'provided_peremp_amount': _post_has_value('peremp_amount_software'),
				'provided_another_amount': _post_has_value('another_amount_software'),
				'provided_amount': _post_has_value('amount_software', 'amount_sw', 'amount'),
				'provided_bill_type': _post_has_value('bill_type_software', 'bill_type', 'bill_type_sw') or (_post_has_value(f'bill_type_{getattr(existing_map_by_lead_for.get(LeadCommissionSlab.LEAD_FOR_SOFTWARE), "id", "")}') if existing_map_by_lead_for.get(LeadCommissionSlab.LEAD_FOR_SOFTWARE) else False),
				'provided_custome_month': _post_has_value('custome_month_software', 'custome_month', 'custome_month_sw'),
				'bill_type': bill_type_sw,
				'custome_month': custome_month_sw,
			})
			# try to parse bill_type and custom month for hardware
			bill_type_hw = (post.get('bill_type_hardware') or post.get('bill_type') or post.get('bill_type_hw'))
			try:
				lb_hw = existing_map_by_lead_for.get(LeadCommissionSlab.LEAD_FOR_HARDWARE)
				if lb_hw:
					bill_type_hw = post.get(f'bill_type_{getattr(lb_hw, "id", "")}') or bill_type_hw
			except Exception:
				pass
			custome_month_hw = None
			try:
				cm = post.get('custome_month_hardware') or post.get('custome_month') or post.get('custome_month_hw')
				if cm not in (None, ''):
					custome_month_hw = int(cm)
			except Exception:
				custome_month_hw = None

			desired.append({
				'lead_for': LeadCommissionSlab.LEAD_FOR_HARDWARE,
				'is_for_software': False,
				'is_peremp': is_peremp_hw,
				'emp_count': emp_count_parsed_hw,
				'peremp_amount': peremp_amount_parsed_hw,
				'another_amount': another_amount_parsed_hw,
				'amount': total_hw,
				'provided_is_peremp': _post_has_value('is_peremp_wise_hardware'),
				'provided_emp_count': _post_has_value('emp_count_hardware'),
				'provided_peremp_amount': _post_has_value('peremp_amount_hardware'),
				'provided_another_amount': _post_has_value('another_amount_hardware'),
				'provided_amount': _post_has_value('amount_hardware', 'amount_hw'),
				'provided_bill_type': _post_has_value('bill_type_hardware', 'bill_type', 'bill_type_hw') or (_post_has_value(f'bill_type_{getattr(existing_map_by_lead_for.get(LeadCommissionSlab.LEAD_FOR_HARDWARE), "id", "")}') if existing_map_by_lead_for.get(LeadCommissionSlab.LEAD_FOR_HARDWARE) else False),
				'provided_custome_month': _post_has_value('custome_month_hardware', 'custome_month', 'custome_month_hw'),
				'bill_type': bill_type_hw,
				'custome_month': custome_month_hw,
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

			# try to parse generic bill_type / custome_month for single-slot case
			bill_type_single = (post.get('bill_type') or '')
			try:
				# if there's an existing LeadBilling row for this lead_for, allow id-based POST key
				if existing_map_by_lead_for:
					existing_any = next(iter(existing_map_by_lead_for.values()))
					if existing_any:
						bill_type_single = post.get(f'bill_type_{getattr(existing_any, "id", "")}') or bill_type_single
			except Exception:
				pass
			custome_month_single = None
			try:
				cm = post.get('custome_month')
				if cm not in (None, ''):
					custome_month_single = int(cm)
			except Exception:
				custome_month_single = None

			desired.append({
				'lead_for': lead_for_val,
				'is_for_software': (lead_for_val == LeadCommissionSlab.LEAD_FOR_SOFTWARE),
				'is_peremp': is_peremp,
				'emp_count': emp_count_parsed,
				'peremp_amount': peremp_amount_parsed,
				'another_amount': another_amount_parsed,
				'amount': total,
				'provided_is_peremp': _post_has_value('is_peremp_wise'),
				'provided_emp_count': _post_has_value('emp_count'),
				'provided_peremp_amount': _post_has_value('peremp_amount'),
				'provided_another_amount': _post_has_value('another_amount'),
				'provided_amount': _post_has_value('amount'),
				'provided_bill_type': _post_has_value('bill_type') or (_post_has_value(f'bill_type_{getattr(next(iter(existing_map_by_lead_for.values()), None), "id", "")}') if existing_map_by_lead_for else False),
				'provided_custome_month': _post_has_value('custome_month'),
				'bill_type': bill_type_single,
				'custome_month': custome_month_single,
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
						# only consider checkbox change if user actually posted a value for it
						if d.get('provided_is_peremp'):
							changed = True
					if (existing.emp_count if existing.emp_count is not None else None) != (d.get('emp_count') if d.get('emp_count') is not None else None):
						if d.get('provided_emp_count'):
							changed = True
					if (existing.peremp_amount if existing.peremp_amount is not None else None) != (d.get('peremp_amount') if d.get('peremp_amount') is not None else None):
						if d.get('provided_peremp_amount'):
							changed = True
					if dec_or_none(existing.another_amount) != dec_or_none(d.get('another_amount')):
						if d.get('provided_another_amount'):
							changed = True
					if dec_or_none(existing.amount) != dec_or_none(d.get('amount')):
						if d.get('provided_amount'):
							changed = True
					# billing type / custom-month changes
					if d.get('provided_bill_type') and ((getattr(existing, 'bill_type', None) or '') != (d.get('bill_type') or '')):
						changed = True
					if d.get('provided_custome_month') and ((getattr(existing, 'custome_month', None) if getattr(existing, 'custome_month', None) is not None else None) != (d.get('custome_month') if d.get('custome_month') is not None else None)):
						changed = True
					if changed:
						existing.is_for_software = d.get('is_for_software', existing.is_for_software)
						existing.is_peremp_wise_amount = bool(d.get('is_peremp', False))
						existing.emp_count = d.get('emp_count')
						existing.peremp_amount = d.get('peremp_amount')
						existing.another_amount = d.get('another_amount')
						existing.amount = d.get('amount')
						existing.bill_type = d.get('bill_type', getattr(existing, 'bill_type', None))
						existing.custome_month = d.get('custome_month', getattr(existing, 'custome_month', None))
						existing.save()
						updated += 1
					obj = existing
				else:
					obj = LeadBilling.objects.create(
						lead=lead,
						lead_for=lf,
						is_for_software=d.get('is_for_software', False),
						is_peremp_wise_amount=bool(d.get('is_peremp', False)),
						emp_count=d.get('emp_count'),
						peremp_amount=d.get('peremp_amount'),
						another_amount=d.get('another_amount'),
						amount=d.get('amount'),
						bill_type=(d.get('bill_type') or LeadBilling.BILL_TYPE_ONE_TIME),
						custome_month=d.get('custome_month', None)
					)
					created += 1

				# Persist product selections for this LeadBilling row when provided in POST
				try:
					# decide which POST keys to consider (id-based, lead_for-based, generic)
					product_keys = []
					try:
						if obj and getattr(obj, 'id', None):
							product_keys.append(f'products_{getattr(obj, "id", "")}')
					except Exception:
						pass
					if lf:
						product_keys.append(f'products_{lf}')
					product_keys.append('products')

					# helper to read list-like values from POST
					def _read_list_for_keys(*keys):
						for k in keys:
							if not k:
								continue
							try:
								vals = post.getlist(k)
							except Exception:
								v = post.get(k)
								if v in (None, ''):
									vals = []
								else:
									if isinstance(v, str) and ',' in v:
										vals = [x.strip() for x in v.split(',') if x.strip()]
									else:
										vals = [v]
							# normalize and yield ids
							ids = []
							for vv in vals:
								if vv in (None, ''):
									continue
								try:
									ids.append(int(str(vv).strip()))
								except Exception:
									continue
							if ids:
								return ids
						return []

					selected_ids = _read_list_for_keys(*product_keys)
					if selected_ids:
						# validate product ids
						valid_ids = list(Product.objects.filter(id__in=selected_ids).values_list('id', flat=True))
						# current linked product ids
						cur_ids = list(LeadBillingProduct.objects.filter(lead_billing=obj).values_list('product_id', flat=True))
						to_add = set(valid_ids) - set(cur_ids)
						to_remove = set(cur_ids) - set(valid_ids)
						for pid in to_add:
							try:
								LeadBillingProduct.objects.create(lead_billing=obj, product_id=pid)
							except Exception:
								pass
						if to_remove:
							LeadBillingProduct.objects.filter(lead_billing=obj, product_id__in=list(to_remove)).delete()
				except Exception:
					# swallow product persistence errors to avoid blocking billing save
						pass

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


@require_POST
@csrf_protect
def ajax_login(request):
	"""Handle AJAX login requests and return JSON responses.

	Expects `username`, `password`, optional `remember`, and optional `next`.
	"""
	username = (request.POST.get('username') or '').strip()
	password = request.POST.get('password') or ''

	if not username or not password:
		return JsonResponse({'success': False, 'errors': 'Username and password are required.'}, status=400)

	# Try normal username authentication first
	user = authenticate(request, username=username, password=password)

	# If that fails and the provided identifier looks like an email, try email lookup
	if user is None and '@' in username:
		try:
			user_candidate = get_user_model().objects.filter(email__iexact=username).first()
		except Exception:
			user_candidate = None
		if user_candidate:
			user = authenticate(request, username=getattr(user_candidate, get_user_model().USERNAME_FIELD, user_candidate.username), password=password)

	if user is None:
		return JsonResponse({'success': False, 'errors': 'Invalid email or password.'}, status=401)
	if not getattr(user, 'is_active', True):
		return JsonResponse({'success': False, 'errors': 'This account is disabled.'}, status=403)

	# Log the user in and set session expiry based on "remember me"
	login(request, user)
	remember = request.POST.get('remember')
	if not remember:
		# expire on browser close
		request.session.set_expiry(0)
	else:
		request.session.set_expiry(settings.SESSION_COOKIE_AGE)

	next_url = request.POST.get('next') or request.GET.get('next') or settings.LOGIN_REDIRECT_URL or '/'
	return JsonResponse({'success': True, 'next': next_url})

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
				from decimal import Decimal

				def _parse_decimal(v):
					if v is None:
						return None
					try:
						s = str(v).strip()
						if s == '':
							return None
						return Decimal(s)
					except Exception:
						return None

				for lb in LeadBilling.objects.filter(lead=lead).order_by('id'):
					key_id = f'commission_type_{getattr(lb, "id", "")}'
					key_lf = f'commission_type_{(getattr(lb, "lead_for", "") or "").strip()}'
					ct = ''
					try:
						ct = (post_data.get(key_id) or post_data.get(key_lf) or post_data.get('commission_type') or '')
						ct = (ct or '').strip()
					except Exception:
						ct = ''

					# commission amount keys (per-slot, per-lead_for, or generic)
					amt_key_id = f'commission_amount_{getattr(lb, "id", "")}'
					amt_key_lf = f'commission_amount_{(getattr(lb, "lead_for", "") or "").strip()}'
					try:
						amt_raw = (post_data.get(amt_key_id) or post_data.get(amt_key_lf) or post_data.get('commission_amount') or '')
						amt_raw = (amt_raw or '').strip()
					except Exception:
						amt_raw = ''
					amt_val = _parse_decimal(amt_raw)

					# detect per-slot / generic "is percentage" toggle (commission_is_percentage_<id>)
					is_pct_toggle = False
					try:
						toggle_key_id = f'commission_is_percentage_{getattr(lb, "id", "")}'
						toggle_key_lf = f'commission_is_percentage_{(getattr(lb, "lead_for", "") or "").strip()}'
						toggle_raw = (post_data.get(toggle_key_id) or post_data.get(toggle_key_lf) or post_data.get('commission_is_percentage'))
						if toggle_raw and str(toggle_raw).strip().lower() in ('1', 'true', 'on', 'yes'):
							is_pct_toggle = True
					except Exception:
						is_pct_toggle = False

					# commission percentage / type value keys (per-slot, per-lead_for, or generic)
					ctval_key_id = f'commission_type_value_{getattr(lb, "id", "")}'
					ctval_key_lf = f'commission_type_value_{(getattr(lb, "lead_for", "") or "").strip()}'
					try:
						ctval_raw = (post_data.get(ctval_key_id) or post_data.get(ctval_key_lf) or post_data.get('commission_type_value') or '')
						ctval_raw = (ctval_raw or '').strip()
					except Exception:
						ctval_raw = ''
					ct_val = _parse_decimal(ctval_raw)

					# commission credit term keys (per-slot, per-lead_for, or generic)
					credit_key_id = f'commission_credit_{getattr(lb, "id", "")}'
					credit_key_lf = f'commission_credit_{(getattr(lb, "lead_for", "") or "").strip()}'
					try:
						credit_raw = (post_data.get(credit_key_id) or post_data.get(credit_key_lf) or post_data.get('commission_credit') or '')
						credit_raw = (credit_raw or '').strip()
					except Exception:
						credit_raw = ''
					credit_val = credit_raw or None
					# commission credit term value keys (per-slot, per-lead_for, or generic)
					credit_val_key_id = f'commission_credit_value_{getattr(lb, "id", "")}'
					credit_val_key_lf = f'commission_credit_value_{(getattr(lb, "lead_for", "") or "").strip()}'
					try:
						credit_val_raw = (post_data.get(credit_val_key_id) or post_data.get(credit_val_key_lf) or post_data.get('commission_credit_value') or '')
						credit_val_raw = (credit_val_raw or '').strip()
					except Exception:
						credit_val_raw = ''
					credit_term_val = _parse_decimal(credit_val_raw)

					# find existing slab for this billing
					slab = LeadCommissionSlab.objects.filter(lead=lead, lead_billing=lb).first()
					if slab:
						changed = False
						# persist credit-term when changed
						try:
							if credit_val is not None and getattr(slab, 'lead_commission_credit_term_condition', None) != credit_val:
								slab.lead_commission_credit_term_condition = credit_val
								changed = True
						except Exception:
							pass
						if ct:
							if slab.lead_commission_type != ct:
								slab.lead_commission_type = ct
								changed = True
							# persist whether this slab is percentage-based
							try:
									# For recurring-like types the client may toggle "Is Percentage" on/off
									new_is_pct = False
									if ct == LeadCommissionSlab.TYPE_PERCENTAGE:
										new_is_pct = True
									else:
										# treat recurring/first/every as percentage only when toggle is set
										if ct in (LeadCommissionSlab.TYPE_RECURRING, LeadCommissionSlab.TYPE_ONLY_FIRST, LeadCommissionSlab.TYPE_EVERY_BILLING) and is_pct_toggle:
											new_is_pct = True
									if getattr(slab, 'is_percentage_wise', False) != new_is_pct:
										slab.is_percentage_wise = new_is_pct
										changed = True
							except Exception:
								pass
						# Set commission_amount when commission type is fix amount, or when
						# recurring-like type is used with percentage-toggle OFF (user entered a fixed amount)
						if ct == LeadCommissionSlab.TYPE_FIX and amt_val is not None:
							if slab.commission_amount is None or slab.commission_amount != amt_val:
								slab.commission_amount = amt_val
								changed = True
						# When percentage type, persist the percentage value and computed amount (if provided)
						if ct == LeadCommissionSlab.TYPE_PERCENTAGE or (ct in (LeadCommissionSlab.TYPE_RECURRING, LeadCommissionSlab.TYPE_ONLY_FIRST, LeadCommissionSlab.TYPE_EVERY_BILLING) and is_pct_toggle):
							if ct_val is not None:
								if slab.lead_commission_type_value is None or slab.lead_commission_type_value != ct_val:
									slab.lead_commission_type_value = ct_val
									changed = True
							# also accept a computed commission_amount posted by the client-side
							if amt_val is not None:
								if slab.commission_amount is None or slab.commission_amount != amt_val:
									slab.commission_amount = amt_val
									changed = True
						# For recurring-like types with toggle OFF, accept explicit amt_val as fix amount
						# and clear any stale percentage value from the database
						if ct in (LeadCommissionSlab.TYPE_RECURRING, LeadCommissionSlab.TYPE_ONLY_FIRST, LeadCommissionSlab.TYPE_EVERY_BILLING) and (not is_pct_toggle):
							if amt_val is not None:
								if slab.commission_amount is None or slab.commission_amount != amt_val:
									slab.commission_amount = amt_val
									changed = True
							if getattr(slab, 'lead_commission_type_value', None) is not None:
								slab.lead_commission_type_value = None
								changed = True
						# persist credit-term value when applicable
						try:
							current_credit = getattr(slab, 'lead_commission_credit_term_condition', None)
							if current_credit in (LeadCommissionSlab.CREDIT_AFTER_PERCENT_COMPLETE, LeadCommissionSlab.CREDIT_AFTER_FEW_DAYS):
								if credit_term_val is not None:
									if slab.lead_commission_credit_term_condition_value is None or slab.lead_commission_credit_term_condition_value != credit_term_val:
										slab.lead_commission_credit_term_condition_value = credit_term_val
										changed = True
								else:
									if getattr(slab, 'lead_commission_credit_term_condition_value', None) is not None:
										slab.lead_commission_credit_term_condition_value = None
										changed = True
							else:
								# clear any stale value when credit-term is not one that accepts a value
								if getattr(slab, 'lead_commission_credit_term_condition_value', None) is not None:
									slab.lead_commission_credit_term_condition_value = None
									changed = True
						except Exception:
							pass
						if changed:
							slab.save()
					else:
						if ct:
							create_kwargs = {
								'lead': lead,
								'lead_commission_type': ct,
								'lead_commission_credit_term_condition': (credit_val or LeadCommissionSlab.CREDIT_AFTER_BILLING),
								'lead_billing': lb
							}
							# mark whether the slab is percentage-based — treat recurring-like as percentage only when toggle set
							create_kwargs['is_percentage_wise'] = True if (ct == LeadCommissionSlab.TYPE_PERCENTAGE or (ct in (LeadCommissionSlab.TYPE_RECURRING, LeadCommissionSlab.TYPE_ONLY_FIRST, LeadCommissionSlab.TYPE_EVERY_BILLING) and is_pct_toggle)) else False
							# If explicit fix amount or recurring-like with toggle OFF, store commission_amount
							if ct == LeadCommissionSlab.TYPE_FIX and amt_val is not None:
								create_kwargs['commission_amount'] = amt_val
							if ct in (LeadCommissionSlab.TYPE_RECURRING, LeadCommissionSlab.TYPE_ONLY_FIRST, LeadCommissionSlab.TYPE_EVERY_BILLING):
								if not is_pct_toggle and amt_val is not None:
									create_kwargs['commission_amount'] = amt_val
							# Percentage-based values
							if ct == LeadCommissionSlab.TYPE_PERCENTAGE or (ct in (LeadCommissionSlab.TYPE_RECURRING, LeadCommissionSlab.TYPE_ONLY_FIRST, LeadCommissionSlab.TYPE_EVERY_BILLING) and is_pct_toggle):
								if ct_val is not None:
									create_kwargs['lead_commission_type_value'] = ct_val
								if amt_val is not None:
									create_kwargs['commission_amount'] = amt_val
							# If credit-term accepts a numeric value, include it for creation
							try:
								if credit_term_val is not None and (create_kwargs.get('lead_commission_credit_term_condition') in (LeadCommissionSlab.CREDIT_AFTER_PERCENT_COMPLETE, LeadCommissionSlab.CREDIT_AFTER_FEW_DAYS)):
									create_kwargs['lead_commission_credit_term_condition_value'] = credit_term_val
							except Exception:
								pass
							LeadCommissionSlab.objects.create(**create_kwargs)
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
								'commission_type_value': getattr(slab, 'lead_commission_type_value', None) if slab else None,
								'commission_amount': getattr(slab, 'commission_amount', None) if slab else None,
								'commission_credit_term_condition_value': getattr(slab, 'lead_commission_credit_term_condition_value', None) if slab else None,
								'commission_credit_value': getattr(slab, 'lead_commission_credit_term_condition_value', None) if slab else None,
								'is_percentage_wise': bool(getattr(slab, 'is_percentage_wise', False)) if slab else False,
								'slab_id': getattr(slab, 'id', None) if slab else None,
								'products': list(LeadBillingProduct.objects.filter(lead_billing=b).values_list('product_id', flat=True)),
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
								'commission_type_value': getattr(slab, 'lead_commission_type_value', None) if slab else None,
								'commission_amount': getattr(slab, 'commission_amount', None) if slab else None,
								'commission_credit_term_condition_value': getattr(slab, 'lead_commission_credit_term_condition_value', None) if slab else None,
								'commission_credit_value': getattr(slab, 'lead_commission_credit_term_condition_value', None) if slab else None,
								'is_percentage_wise': bool(getattr(slab, 'is_percentage_wise', False)) if slab else False,
								'slab_id': getattr(slab, 'id', None) if slab else None,
								'products': list(LeadBillingProduct.objects.filter(lead_billing=b).values_list('product_id', flat=True)),
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
				# include posted keys to help debug missing/incorrect field names
				posted_keys_list = []
				try:
					posted_keys_list = sorted(list(post_data.keys()))
				except Exception:
					posted_keys_list = []
				# structured form errors
				form_errors = {}
				try:
					for k, v in form.errors.items():
						form_errors[k] = [str(x) for x in v]
				except Exception:
					form_errors = {}
				return JsonResponse({'ok': False, 'errors': errors, 'form_errors': form_errors, 'posted_keys': posted_keys_list}, status=400)
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
	# selected product lists for Details tab pre-selection
	selected_products = []
	selected_products_software = []
	selected_products_hardware = []
	# billing frequency selections
	selected_bill_type = ''
	selected_custome_month = None
	selected_bill_type_software = ''
	selected_custome_month_software = None
	selected_bill_type_hardware = ''
	selected_custome_month_hardware = None
	# selected commission type (populated from POST or existing LeadCommissionSlab)
	selected_commission_type = ''
	# selected commission credit term (from LeadCommissionSlab.CREDIT_CHOICES)
	selected_commission_credit = ''
	# selected commission credit term numeric value (percentage or days)
	selected_commission_credit_value = None
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
				# copy posted product selections so form redisplay keeps values
				try:
					vals = request.POST.getlist('products')
					if vals:
						selected_products = [int(x) for x in vals if x not in (None, '')]
				except Exception:
					pass
				try:
					vals = request.POST.getlist('products_software')
					if vals:
						selected_products_software = [int(x) for x in vals if x not in (None, '')]
				except Exception:
					pass
				try:
					vals = request.POST.getlist('products_hardware')
					if vals:
						selected_products_hardware = [int(x) for x in vals if x not in (None, '')]
				except Exception:
					pass
				# billing frequency posted values
				if request.POST.get('bill_type') is not None:
					selected_bill_type = (request.POST.get('bill_type') or '').strip()
				if request.POST.get('custome_month') is not None:
					try:
						selected_custome_month = int(request.POST.get('custome_month'))
					except Exception:
						selected_custome_month = None
				if request.POST.get('bill_type_software') is not None:
					selected_bill_type_software = (request.POST.get('bill_type_software') or '').strip()
				if request.POST.get('custome_month_software') is not None:
					try:
						selected_custome_month_software = int(request.POST.get('custome_month_software'))
					except Exception:
						selected_custome_month_software = None
				if request.POST.get('bill_type_hardware') is not None:
					selected_bill_type_hardware = (request.POST.get('bill_type_hardware') or '').strip()
				if request.POST.get('custome_month_hardware') is not None:
					try:
						selected_custome_month_hardware = int(request.POST.get('custome_month_hardware'))
					except Exception:
						selected_custome_month_hardware = None
				# commission type posted from the commission tab
				if request.POST.get('commission_type') is not None:
					selected_commission_type = (request.POST.get('commission_type') or '').strip()
				# commission credit term posted from the commission tab
				if request.POST.get('commission_credit') is not None:
					selected_commission_credit = (request.POST.get('commission_credit') or '').strip()
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
								# selected products for software slot
								try:
									selected_products_software = list(LeadBillingProduct.objects.filter(lead_billing=b).values_list('product_id', flat=True))
								except Exception:
									selected_products_software = []
								# billing frequency values from existing LeadBilling
								selected_bill_type_software = getattr(b, 'bill_type', '') or ''
								selected_custome_month_software = getattr(b, 'custome_month', None)
								# mirror into single-fields when only software present
								selected_is_peremp_wise = selected_is_peremp_wise_software
								selected_peremp_amount = selected_peremp_amount_software
								selected_emp_count = selected_emp_count_software
								selected_another_amount = selected_another_amount_software
							elif 'hardware' in lf:
								selected_another_amount_hardware = getattr(b, 'another_amount', 0) or 0
								selected_bill_type_hardware = getattr(b, 'bill_type', '') or ''
								selected_custome_month_hardware = getattr(b, 'custome_month', None)
								# mirror for single hardware-only case
								selected_another_amount = selected_another_amount_hardware
								# selected products for hardware slot
								try:
									selected_products_hardware = list(LeadBillingProduct.objects.filter(lead_billing=b).values_list('product_id', flat=True))
								except Exception:
									selected_products_hardware = []

					# Mirror billing frequency values into single-field variables when only
					# software or only hardware billing is present so the single-slot form
					# pre-selects the saved option on edit.
					try:
						if has_sw and not has_hw:
							selected_bill_type = selected_bill_type_software or ''
							selected_custome_month = selected_custome_month_software
						elif has_hw and not has_sw:
							selected_bill_type = selected_bill_type_hardware or ''
							selected_custome_month = selected_custome_month_hardware
					except Exception:
						pass
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
								# also derive selected commission credit term when available
								try:
									if first and getattr(first, 'lead_commission_credit_term_condition', None):
										selected_commission_credit = getattr(first, 'lead_commission_credit_term_condition') or ''
								except Exception:
									pass
									# also derive selected commission credit term numeric value when present
									try:
										if first and getattr(first, 'lead_commission_credit_term_condition_value', None) is not None:
											selected_commission_credit_value = getattr(first, 'lead_commission_credit_term_condition_value')
									except Exception:
										pass
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
				# collect selected product ids for this billing row
				try:
					selected_products = list(LeadBillingProduct.objects.filter(lead_billing=lb).values_list('product_id', flat=True))
				except Exception:
					selected_products = []
				lead_billing_rows.append({
					'id': getattr(lb, 'id', None),
					'lead_for': getattr(lb, 'lead_for', ''),
					'is_for_software': bool(getattr(lb, 'is_for_software', False)),
					'is_peremp': bool(getattr(lb, 'is_peremp_wise_amount', False)),
					'emp_count': getattr(lb, 'emp_count', None),
					'peremp_amount': getattr(lb, 'peremp_amount', None),
					'another_amount': getattr(lb, 'another_amount', None),
					'amount': getattr(lb, 'amount', None),
					'bill_type': getattr(lb, 'bill_type', None) or '',
					'custome_month': getattr(lb, 'custome_month', None),
					'commission_type': getattr(slab, 'lead_commission_type', '') if slab else '',
					'commission_type_value': getattr(slab, 'lead_commission_type_value', None) if slab else None,
					'commission_amount': getattr(slab, 'commission_amount', None) if slab else None,
					'commission_credit': getattr(slab, 'lead_commission_credit_term_condition', '') if slab else '',
					'commission_credit_value': getattr(slab, 'lead_commission_credit_term_condition_value', None) if slab else None,
					'is_percentage_wise': bool(getattr(slab, 'is_percentage_wise', False)) if slab else False,
					'slab_id': getattr(slab, 'id', None) if slab else None,
					'selected_products': selected_products,
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
		# credit-term choices from model
		'commission_credit_choices': LeadCommissionSlab.CREDIT_CHOICES,
		'selected_commission_type': selected_commission_type,
		'selected_commission_credit': selected_commission_credit,
		'selected_commission_credit_value': selected_commission_credit_value,
		# billing type choices for template
		'bill_type_choices': LeadBilling.BILL_TYPE_CHOICES,
		# billing frequency selected values (from POST or LeadBilling rows)
		'selected_bill_type': selected_bill_type,
		'selected_custome_month': selected_custome_month,
		'selected_bill_type_software': selected_bill_type_software,
		'selected_custome_month_software': selected_custome_month_software,
		'selected_bill_type_hardware': selected_bill_type_hardware,
		'selected_custome_month_hardware': selected_custome_month_hardware,
		'lead_billing_rows': lead_billing_rows,
		# available products for per-billing multi-select
		'products': Product.objects.filter(is_deleted=False, is_draft=False).order_by('-created_at') if hasattr(Product, 'is_deleted') and hasattr(Product, 'is_draft') else Product.objects.all().order_by('-created_at'),
		# billing template values (populated from POST or LeadBilling rows)
		'selected_peremp_amount': selected_peremp_amount,
		'selected_emp_count': selected_emp_count,
		'selected_another_amount': selected_another_amount,
		'selected_is_peremp_wise_software': selected_is_peremp_wise_software,
		'selected_peremp_amount_software': selected_peremp_amount_software,
		'selected_emp_count_software': selected_emp_count_software,
		'selected_another_amount_software': selected_another_amount_software,
		'selected_another_amount_hardware': selected_another_amount_hardware,
		# Details tab product selections
		'selected_products': selected_products,
		'selected_products_software': selected_products_software,
		'selected_products_hardware': selected_products_hardware,
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


def product_list(request):
	"""Render the product list page and support export."""
	show_drafts = str(request.GET.get('show_drafts', '')).lower() in ['1', 'true', 'on', 'yes']
	show_deleted = str(request.GET.get('show_deleted', '')).lower() in ['1', 'true', 'on', 'yes']
	if show_deleted:
		if hasattr(Product, 'is_deleted'):
			products = Product.objects.filter(is_deleted=True).order_by('-created_at')
		else:
			products = Product.objects.none()
	elif show_drafts:
		if hasattr(Product, 'is_draft'):
			products = Product.objects.filter(is_draft=True, is_deleted=False).order_by('-created_at')
		else:
			products = Product.objects.none()
	else:
		# Default listing: exclude drafts and soft-deleted items when model supports them
		order_field = '-created_at' if hasattr(Product, 'created_at') else '-id'
		if hasattr(Product, 'is_draft') and hasattr(Product, 'is_deleted'):
			products = Product.objects.filter(is_draft=False, is_deleted=False).order_by(order_field)
		else:
			# fallback: return all products ordered by available field
			products = Product.objects.all().order_by(order_field)

	export_fmt = str(request.GET.get('export', '')).lower()
	if export_fmt:
		export_scope = str(request.GET.get('export_scope', 'all')).lower()
		qs = products
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
				qs = products[start:end]

		rows = []
		for p in qs:
			rows.append([p.sku, p.name, p.description or ''])

		if export_fmt == 'csv':
			resp = HttpResponse(content_type='text/csv')
			resp['Content-Disposition'] = 'attachment; filename="products.csv"'
			writer = csv.writer(resp)
			writer.writerow(['SKU', 'Name', 'Description'])
			for r in rows:
				writer.writerow([smart_str(x) for x in r])
			return resp

		if export_fmt == 'txt':
			resp = HttpResponse(content_type='text/plain; charset=utf-8')
			resp['Content-Disposition'] = 'attachment; filename="products.txt"'
			for r in rows:
				resp.write('\t'.join([smart_str(x) for x in r]) + '\n')
			return resp

		if export_fmt in ('xlsx', 'excel'):
			html = '<table><thead><tr><th>SKU</th><th>Name</th><th>Description</th></tr></thead><tbody>'
			for r in rows:
				row_html = ''.join(['<td>%s</td>' % escape(str(c)) for c in r])
				html += '<tr>%s</tr>' % row_html
			html += '</tbody></table>'
			resp = HttpResponse(html, content_type='application/vnd.ms-excel')
			resp['Content-Disposition'] = 'attachment; filename="products.xls"'
			return resp

		resp = HttpResponse('PDF export is not implemented on the server. Please choose CSV or Excel.', content_type='text/plain')
		resp.status_code = 501
		return resp

	return render(request, 'products/product-list.html', {'products': products, 'show_drafts': show_drafts, 'show_deleted': show_deleted})


def add_product(request):
	"""Create or edit a Product."""
	product = None
	if request.method == 'POST':
		product_id = request.POST.get('id') or request.GET.get('id')
		if product_id:
			product = get_object_or_404(Product, pk=product_id)
			form = ProductForm(request.POST, instance=product)
		else:
			form = ProductForm(request.POST)

		action = request.POST.get('action') or 'publish'
		if form.is_valid():
			product = form.save(commit=False)
			# if Product has draft flag, respect it; otherwise ignore
			try:
				if hasattr(product, 'is_draft'):
					product.is_draft = (action == 'draft')
			except Exception:
				pass
			product.save()
			# save many-to-many relations (companies, locations) when provided
			try:
				comps = form.cleaned_data.get('companies')
				if comps is not None:
					product.companies.set(comps)
				locs = form.cleaned_data.get('locations')
				if locs is not None:
					product.locations.set(locs)
			except Exception:
				# swallow errors to avoid blocking main save flow
				pass
			if product_id:
				messages.success(request, 'Product updated successfully.')
			else:
				if getattr(product, 'is_draft', False):
					messages.success(request, 'Product saved as draft.')
				else:
					messages.success(request, 'Product added successfully.')
			return redirect('product_list')
		else:
			messages.error(request, 'Please correct the errors below.')
	else:
		product_id = request.GET.get('id')
		if product_id:
			product = get_object_or_404(Product, pk=product_id)
			form = ProductForm(instance=product)
		else:
			form = ProductForm()

	return render(request, 'products/add-product.html', {'form': form, 'product': product})


def product_detail(request):
	product_id = request.GET.get('id')
	if not product_id:
		messages.error(request, 'No product id provided.')
		return redirect('product_list')
	product = get_object_or_404(Product, pk=product_id)
	return render(request, 'products/product-detail.html', {'product': product})


@require_POST
def delete_product(request):
	product_id = request.POST.get('id')
	if not product_id:
		messages.error(request, 'No product id provided.')
		return redirect('product_list')
	product = get_object_or_404(Product, pk=product_id)
	try:
		if hasattr(product, 'is_deleted'):
			product.is_deleted = True
			product.save()
		else:
			product.delete()
		messages.success(request, 'Product deleted successfully.')
	except Exception as e:
		messages.error(request, 'Failed to delete product: %s' % str(e))
	return redirect('product_list')


@require_POST
def restore_product(request):
	product_id = request.POST.get('id')
	if not product_id:
		messages.error(request, 'No product id provided.')
		return redirect('product_list')
	if hasattr(Product, 'is_deleted'):
		product = get_object_or_404(Product, pk=product_id)
		if not product.is_deleted:
			messages.info(request, 'Product is not deleted.')
		else:
			product.is_deleted = False
			product.save()
			messages.success(request, 'Product restored successfully.')
	else:
		messages.error(request, 'Restore is not supported for products.')
	return redirect('product_list')

