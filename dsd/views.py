"""
DSD Price Book Management System
Django Views
pricebook_manager / dsd / views.py
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Q
from django.utils import timezone
from django.http import HttpResponse
import csv

from .models import (
    Vendor, LinkGroup, Item, PendingCostChange, ChangeHistory, BRDataExportLog
)
from .utils.pricing import suggest_retail, normalize_upc


# ============================================================
# DASHBOARD
# ============================================================
@login_required
def dashboard(request):
    today = timezone.now().date()

    # Summary counts
    vendor_count        = Vendor.objects.filter(is_active=True).count()
    item_count          = Item.objects.filter(is_active=True).count()
    pending_count       = PendingCostChange.objects.filter(status='PENDING').count()
    due_today_count     = PendingCostChange.objects.filter(
                            status='APPROVED',
                            effective_date__lte=today).count()

    # Vendors with pending changes
    vendors_with_pending = (
        Vendor.objects.filter(is_active=True)
        .annotate(pending=Count(
            'items__pending_cost_changes',
            filter=Q(items__pending_cost_changes__status='PENDING')))
        .filter(pending__gt=0)
        .order_by('-pending')
    )

    # Recent price history
    recent_history = ChangeHistory.objects.select_related().order_by(
                        '-change_date')[:10]

    # Changes due today or overdue
    due_changes = PendingCostChange.objects.filter(
                    status='APPROVED',
                    effective_date__lte=today
                  ).select_related('item__vendor').order_by('effective_date')

    context = {
        'vendor_count':         vendor_count,
        'item_count':           item_count,
        'pending_count':        pending_count,
        'due_today_count':      due_today_count,
        'vendors_with_pending': vendors_with_pending,
        'recent_history':       recent_history,
        'due_changes':          due_changes,
        'today':                today,
    }
    return render(request, 'dsd/dashboard.html', context)


# ============================================================
# VENDOR LIST
# ============================================================
@login_required
def vendor_list(request):
    vendors = (
        Vendor.objects.filter(is_active=True)
        .annotate(
            item_count=Count('items', filter=Q(items__is_active=True)),
            pending_count=Count(
                'items__pending_cost_changes',
                filter=Q(items__pending_cost_changes__status='PENDING'))
        )
        .order_by('vendor_code')
    )

    context = {'vendors': vendors}
    return render(request, 'dsd/vendor_list.html', context)


# ============================================================
# PRICE BOOK  (items for a single vendor)
# ============================================================
@login_required
def price_book(request, vendor_code):
    vendor = get_object_or_404(Vendor, vendor_code=vendor_code, is_active=True)

    # Get all active items grouped by link group
    items = (
        Item.objects.filter(vendor=vendor, is_active=True)
        .select_related('link_group')
        .prefetch_related('pending_cost_changes')
        .order_by('link_group__link_code', 'seq', 'description')
    )

    # Group items by link group for display
    groups = {}
    ungrouped = []
    for item in items:
        if item.link_group:
            key = item.link_group.link_code
            if key not in groups:
                groups[key] = {
                    'link_group': item.link_group,
                    'items': []
                }
            groups[key]['items'].append(item)
        else:
            ungrouped.append(item)

    context = {
        'vendor':    vendor,
        'groups':    groups,
        'ungrouped': ungrouped,
        'item_count': items.count(),
        'all_vendors': Vendor.objects.filter(is_active=True).order_by('vendor_code'),
    }
    return render(request, 'dsd/price_book.html', context)


# ============================================================
# ITEM DETAIL
# ============================================================
@login_required
def item_detail(request, vendor_code, upc):
    item = get_object_or_404(Item, vendor_id=vendor_code, upc=upc)

    pending = PendingCostChange.objects.filter(
                item=item, status='PENDING').first()

    history = ChangeHistory.objects.filter(
                vendor_code=vendor_code, upc=upc
              ).order_by('-change_date')[:20]

    context = {
        'item':    item,
        'pending': pending,
        'history': history,
    }
    return render(request, 'dsd/item_detail.html', context)


# ============================================================
# PENDING CHANGES  (buyer worklist)
# ============================================================
@login_required
def pending_changes(request):
    today = timezone.now().date()

    # Filter options
    vendor_filter   = request.GET.get('vendor', '')
    status_filter   = request.GET.get('status', 'PENDING')

    changes = (
        PendingCostChange.objects.filter(status=status_filter)
        .select_related('item__vendor', 'item__link_group',
                        'submitted_by', 'approved_by')
        .order_by('effective_date', 'vendor_code')
    )

    if vendor_filter:
        changes = changes.filter(vendor_code=vendor_filter)

    # Vendors for filter dropdown
    vendors = Vendor.objects.filter(is_active=True).order_by('vendor_code')

    context = {
        'changes':       changes,
        'vendors':       vendors,
        'vendor_filter': vendor_filter,
        'status_filter': status_filter,
        'today':         today,
        'status_choices': PendingCostChange.STATUS_CHOICES,
    }
    return render(request, 'dsd/pending_cost_changes.html', context)


# ============================================================
# COST CHANGE ENTRY
# ============================================================
@login_required
def cost_change_entry(request, vendor_code, upc):
    item = get_object_or_404(Item, vendor_id=vendor_code, upc=upc)

    # Check for existing pending change
    existing = PendingCostChange.objects.filter(
                    item=item, status='PENDING').first()

    if request.method == 'POST':
        new_case_cost   = request.POST.get('new_case_cost')
        new_allowance   = request.POST.get('new_allowance', 0)
        effective_date  = request.POST.get('effective_date')
        approved_retail = request.POST.get('approved_retail')
        notes           = request.POST.get('notes', '')

        try:
            new_case_cost   = float(new_case_cost)
            new_allowance   = float(new_allowance or 0)
            new_unit_cost   = (new_case_cost - new_allowance) / item.case_pack

            # Calculate suggested retail
            current_margin  = float(item.margin) if item.margin else float(
                                item.vendor.target_margin)
            suggested       = suggest_retail(new_unit_cost, current_margin)

            # If existing pending change, update it; otherwise create new
            if existing:
                change = existing
            else:
                change = PendingCostChange(
                    item        = item,
                    vendor_code = vendor_code,
                    upc         = upc,
                )

            change.new_case_cost    = new_case_cost
            change.new_allowance    = new_allowance
            change.effective_date   = effective_date
            change.suggested_retail = suggested
            change.approved_retail  = approved_retail or suggested
            change.prev_case_cost   = item.case_cost
            change.prev_allowance   = item.allowance
            change.prev_retail      = item.retail_price
            change.prev_margin      = item.margin
            change.change_source    = 'MANUAL'
            change.submitted_by     = request.user
            change.notes            = notes
            change.status           = 'PENDING'
            change.save()

            messages.success(
                request,
                f'Cost change saved for {item.description}. '
                f'Suggested retail: ${suggested}'
            )
            return redirect('dsd:price_book', vendor_code=vendor_code)

        except (ValueError, TypeError) as e:
            messages.error(request, f'Invalid data: {e}')

    # GET - show the form
    # Pre-calculate suggested retail if we have current data
    preview_suggested = None
    if item.unit_cost and item.margin:
        preview_suggested = suggest_retail(
            float(item.unit_cost), float(item.margin))

    context = {
        'item':              item,
        'existing':          existing,
        'preview_suggested': preview_suggested,
        'today':             timezone.now().date(),
    }
    return render(request, 'dsd/cost_change_entry.html', context)


# ============================================================
# APPROVE / REJECT CHANGE  (AJAX-friendly POST)
# ============================================================
@login_required
def approve_change(request, change_id):
    change = get_object_or_404(PendingCostChange, id=change_id, status='PENDING')

    if request.method == 'POST':
        action          = request.POST.get('action')  # 'approve' or 'reject'
        retail_override = request.POST.get('approved_retail')

        if action == 'approve':
            change.approve(
                user            = request.user,
                retail_override = retail_override or None
            )
            messages.success(
                request,
                f'Change approved for {change.item.description}'
            )
        elif action == 'reject':
            change.status = 'REJECTED'
            change.approved_by = request.user
            change.approved_at = timezone.now()
            change.save()
            messages.warning(
                request,
                f'Change rejected for {change.item.description}'
            )

    return redirect(request.POST.get('next', 'dsd:pending_cost_changes'))


# ============================================================
# APPLY APPROVED CHANGES  (promote to live pricing)
# ============================================================
@login_required
def apply_change(request, change_id):
    change = get_object_or_404(PendingCostChange, id=change_id, status='APPROVED')

    if request.method == 'POST':
        try:
            change.apply_to_item(request.user)
            messages.success(
                request,
                f'Price change applied for {change.item.description}. '
                f'New retail: ${change.approved_retail}'
            )
        except ValueError as e:
            messages.error(request, str(e))

    return redirect(request.POST.get('next', 'dsd:pending_cost_changes'))


# ============================================================
# BRDATA EXPORT
# Generate export file for BRData import
# ============================================================
@login_required
def brdata_export(request):
    """
    Export approved changes to a CSV file formatted for BRData import.
    Only exports APPROVED changes where effective_date <= today.
    """
    today = timezone.now().date()

    changes = PendingCostChange.objects.filter(
                status='APPROVED',
                effective_date__lte=today
              ).select_related('item__vendor')

    if not changes.exists():
        messages.warning(request, 'No approved changes ready for export.')
        return redirect('dsd:pending_cost_changes')

    # Generate CSV
    response = HttpResponse(content_type='text/csv')
    filename = f'brdata_export_{today.strftime("%Y%m%d")}.csv'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)

    # BRData import format - adjust columns to match BRData spec
    writer.writerow([
        'ITEM_NO', 'UPC', 'DESCRIPTION', 'NEW_RETAIL',
        'EFFECTIVE_DATE', 'VENDOR_CODE'
    ])

    export_records = []
    for change in changes:
        writer.writerow([
            change.item.brdata_item_no or '',
            change.upc,
            change.item.description,
            change.approved_retail,
            change.effective_date.strftime('%Y%m%d'),
            change.vendor_code,
        ])
        export_records.append(change.id)

    # Log the export
    for change_id in export_records:
        BRDataExportLog.objects.create(
            export_type     = 'PRICE_CHANGE',
            vendor_code     = changes.get(id=change_id).vendor_code,
            upc             = changes.get(id=change_id).upc,
            brdata_item_no  = changes.get(id=change_id).item.brdata_item_no,
            new_retail      = changes.get(id=change_id).approved_retail,
            effective_date  = changes.get(id=change_id).effective_date,
            export_status   = 'SENT',
            export_file     = filename,
            exported_by     = request.user.username,
        )

    return response
