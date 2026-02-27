"""
DSD Price Book Management System
Django Models  v2
pricebook_manager / dsd / models.py

Terminology:
    Cost Change  = vendor-initiated change to what Cost Less pays
    Price Change = buyer-initiated change to what the customer pays
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal


# ============================================================
# VENDOR
# ============================================================
class Vendor(models.Model):

    COMM_METHOD_CHOICES = [
        ('EXCEL',   'Excel Spreadsheet'),
        ('EMAIL',   'Email'),
        ('EDI',     'EDI'),
        ('PORTAL',  'Vendor Portal'),
        ('PAPER',   'Paper / Fax'),
        ('OTHER',   'Other'),
    ]

    vendor_code     = models.CharField(max_length=20, primary_key=True)
    vendor_name     = models.CharField(max_length=100)
    rep_name        = models.CharField(max_length=100, blank=True, null=True)
    rep_email       = models.EmailField(max_length=100, blank=True, null=True)
    rep_phone       = models.CharField(max_length=20, blank=True, null=True)
    comm_method     = models.CharField(
                        max_length=30, choices=COMM_METHOD_CHOICES,
                        blank=True, null=True)
    target_margin   = models.DecimalField(
                        max_digits=5, decimal_places=4, default=Decimal('0.2800'),
                        help_text='Default target margin e.g. 0.2850 = 28.5%')
    is_active       = models.BooleanField(default=True)
    notes           = models.TextField(blank=True, null=True)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        db_table            = 'dsd_vendor'
        ordering            = ['vendor_code']
        verbose_name        = 'Vendor'
        verbose_name_plural = 'Vendors'

    def __str__(self):
        return f'{self.vendor_code} — {self.vendor_name}'

    @property
    def active_item_count(self):
        return self.items.filter(is_active=True).count()

    @property
    def pending_cost_change_count(self):
        return self.items.filter(
            pending_cost_changes__status='PENDING'
        ).distinct().count()


# ============================================================
# LINK GROUP
# ============================================================
class LinkGroup(models.Model):

    link_code       = models.CharField(max_length=20)
    vendor          = models.ForeignKey(
                        Vendor, on_delete=models.RESTRICT,
                        related_name='link_groups',
                        db_column='vendor_code')
    link_group_name = models.CharField(max_length=100)
    is_active       = models.BooleanField(default=True)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        db_table            = 'dsd_link_group'
        unique_together     = [('link_code', 'vendor')]
        ordering            = ['vendor', 'link_code']
        verbose_name        = 'Link Group'
        verbose_name_plural = 'Link Groups'

    def __str__(self):
        return f'{self.link_code} — {self.link_group_name}'


# ============================================================
# ITEM
# Composite natural key: (vendor_code, upc)
# UPC always stored normalized - no hyphens or spaces
# ============================================================
class Item(models.Model):

    vendor          = models.ForeignKey(
                        Vendor, on_delete=models.RESTRICT,
                        related_name='items',
                        db_column='vendor_code')
    upc             = models.CharField(
                        max_length=14,
                        help_text='Normalized UPC — no hyphens or spaces')
    seq             = models.IntegerField(null=True, blank=True,
                        help_text='Display sequence within vendor')
    link_group      = models.ForeignKey(
                        LinkGroup, on_delete=models.SET_NULL,
                        null=True, blank=True,
                        related_name='items')
    brdata_item_no  = models.CharField(max_length=20, blank=True, null=True,
                        help_text='BRData PLU / Vendor Item Number')
    description     = models.CharField(max_length=100)
    case_pack       = models.IntegerField(default=1)
    size_alpha      = models.CharField(max_length=20, blank=True, null=True)

    # Current Pricing — stored values
    case_cost       = models.DecimalField(max_digits=10, decimal_places=2,
                        default=Decimal('0.00'))
    allowance       = models.DecimalField(max_digits=10, decimal_places=2,
                        default=Decimal('0.00'))
    price_qty       = models.IntegerField(default=1)
    retail_price    = models.DecimalField(max_digits=10, decimal_places=2,
                        null=True, blank=True)

    # Separate tracking for cost vs price change dates
    last_cost_change    = models.DateField(null=True, blank=True,
                            help_text='Date of last vendor cost change')
    last_price_change   = models.DateField(null=True, blank=True,
                            help_text='Date of last buyer retail price change')

    # Status
    is_disco        = models.BooleanField(default=False)
    is_tpr          = models.BooleanField(default=False)
    movement        = models.IntegerField(null=True, blank=True,
                        help_text='Units sold — sourced from BRData')
    movement_updated_at = models.DateTimeField(null=True, blank=True)

    # Metadata
    vendor_comments = models.TextField(blank=True, null=True)
    notes           = models.TextField(blank=True, null=True)
    is_active       = models.BooleanField(default=True)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        db_table            = 'dsd_item'
        unique_together     = [('vendor', 'upc')]
        ordering            = ['vendor', 'seq', 'description']
        verbose_name        = 'Item'
        verbose_name_plural = 'Items'

    def __str__(self):
        return f'{self.upc} — {self.description}'

    # ---- Calculated properties (mirror MySQL generated columns) ----

    @property
    def net_case_cost(self):
        return self.case_cost - self.allowance

    @property
    def unit_cost(self):
        if self.case_pack and self.case_pack > 0:
            return self.net_case_cost / Decimal(str(self.case_pack))
        return None

    @property
    def margin(self):
        if self.retail_price and self.retail_price > 0 and self.unit_cost is not None:
            return (self.retail_price - self.unit_cost) / self.retail_price
        return None

    @property
    def margin_pct(self):
        """Margin as display string e.g. '28.5%'"""
        if self.margin is not None:
            return f'{float(self.margin) * 100:.1f}%'
        return '—'

    @property
    def has_pending_cost_change(self):
        return self.pending_cost_changes.filter(status='PENDING').exists()

    @property
    def pending_cost_change(self):
        """Returns the current pending cost change if one exists"""
        return self.pending_cost_changes.filter(status='PENDING').first()


# ============================================================
# PENDING COST CHANGE
# Vendor-initiated cost changes awaiting buyer review
# Buyer sets the approved retail (the resulting price change)
# ============================================================
class PendingCostChange(models.Model):

    STATUS_CHOICES = [
        ('PENDING',  'Pending Review'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('APPLIED',  'Applied'),
    ]

    SOURCE_CHOICES = [
        ('MANUAL',      'Manual Entry'),
        ('IMPORT',      'File Import'),
        ('PORTAL',      'Vendor Portal'),
        ('BRDATA_SYNC', 'BRData Sync'),
    ]

    item            = models.ForeignKey(
                        Item, on_delete=models.CASCADE,
                        related_name='pending_cost_changes')
    vendor_code     = models.CharField(max_length=20)
    upc             = models.CharField(max_length=14)

    # New Cost from Vendor
    new_case_cost   = models.DecimalField(max_digits=10, decimal_places=2)
    new_allowance   = models.DecimalField(max_digits=10, decimal_places=2,
                        default=Decimal('0.00'))
    effective_date  = models.DateField()

    # Retail — suggested by system, approved by buyer
    suggested_retail    = models.DecimalField(max_digits=10, decimal_places=2,
                            null=True, blank=True,
                            help_text='System calculated suggested retail')
    approved_retail     = models.DecimalField(max_digits=10, decimal_places=2,
                            null=True, blank=True,
                            help_text='Buyer accepted or overridden retail')

    # Snapshot of values at time of submission
    prev_case_cost  = models.DecimalField(max_digits=10, decimal_places=2,
                        null=True, blank=True)
    prev_allowance  = models.DecimalField(max_digits=10, decimal_places=2,
                        null=True, blank=True)
    prev_retail     = models.DecimalField(max_digits=10, decimal_places=2,
                        null=True, blank=True)
    prev_margin     = models.DecimalField(max_digits=5, decimal_places=4,
                        null=True, blank=True)

    # Workflow
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES,
                        default='PENDING')
    change_source   = models.CharField(max_length=20, choices=SOURCE_CHOICES,
                        default='MANUAL')
    submitted_by    = models.ForeignKey(
                        User, on_delete=models.SET_NULL,
                        null=True, blank=True,
                        related_name='submitted_cost_changes')
    approved_by     = models.ForeignKey(
                        User, on_delete=models.SET_NULL,
                        null=True, blank=True,
                        related_name='approved_cost_changes')
    approved_at     = models.DateTimeField(null=True, blank=True)
    applied_at      = models.DateTimeField(null=True, blank=True)
    notes           = models.TextField(blank=True, null=True)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        db_table            = 'dsd_pending_cost_change'
        ordering            = ['effective_date', 'vendor_code']
        verbose_name        = 'Pending Cost Change'
        verbose_name_plural = 'Pending Cost Changes'

    def __str__(self):
        return f'{self.vendor_code}/{self.upc} — {self.get_status_display()}'

    # ---- Calculated properties ----

    @property
    def new_net_case_cost(self):
        return self.new_case_cost - self.new_allowance

    @property
    def new_unit_cost(self):
        if self.item and self.item.case_pack > 0:
            return self.new_net_case_cost / Decimal(str(self.item.case_pack))
        return None

    @property
    def cost_change_amount(self):
        """Dollar change in unit cost"""
        if self.prev_case_cost is not None and self.item.case_pack > 0:
            old_unit = (self.prev_case_cost - (self.prev_allowance or 0)) / self.item.case_pack
            if self.new_unit_cost is not None:
                return self.new_unit_cost - old_unit
        return None

    @property
    def cost_change_pct(self):
        """Percentage change in unit cost"""
        if self.cost_change_amount is not None and self.prev_case_cost:
            old_unit = (self.prev_case_cost - (self.prev_allowance or 0)) / self.item.case_pack
            if old_unit > 0:
                return (float(self.cost_change_amount) / float(old_unit)) * 100
        return None

    @property
    def retail_is_overridden(self):
        """True if buyer changed the suggested retail"""
        if self.approved_retail and self.suggested_retail:
            return self.approved_retail != self.suggested_retail
        return False

    def approve(self, user, retail_override=None):
        """Approve this cost change, optionally overriding the suggested retail"""
        self.status     = 'APPROVED'
        self.approved_by = user
        self.approved_at = timezone.now()
        if retail_override:
            self.approved_retail = retail_override
        elif self.approved_retail is None:
            self.approved_retail = self.suggested_retail
        self.save()

    def apply_to_item(self, user):
        """
        Promote approved cost change to the live item record.
        Writes unified change history record.
        Determines change_type based on whether retail actually changed.
        """
        if self.status != 'APPROVED':
            raise ValueError('Cost change must be APPROVED before applying')

        item = self.item

        # Determine change type
        retail_changed = (
            self.approved_retail is not None and
            self.approved_retail != item.retail_price
        )
        change_type = 'COST_AND_PRICE' if retail_changed else 'COST_ONLY'

        # Write history before updating item
        ChangeHistory.objects.create(
            vendor_code             = item.vendor_id,
            upc                     = item.upc,
            change_type             = change_type,
            old_case_cost           = item.case_cost,
            old_allowance           = item.allowance,
            new_case_cost           = self.new_case_cost,
            new_allowance           = self.new_allowance,
            old_retail              = item.retail_price,
            new_retail              = self.approved_retail,
            old_margin              = item.margin,
            changed_by              = user.username if user else 'SYSTEM',
            change_source           = self.change_source,
            pending_cost_change_id  = self.id,
        )

        # Update item
        item.case_cost          = self.new_case_cost
        item.allowance          = self.new_allowance
        item.last_cost_change   = timezone.now().date()
        if retail_changed:
            item.retail_price       = self.approved_retail
            item.last_price_change  = timezone.now().date()
        item.save()

        # Mark change as applied
        self.status     = 'APPLIED'
        self.applied_at = timezone.now()
        self.save()


# ============================================================
# CHANGE HISTORY
# Unified audit trail for cost changes and price changes
#
# change_type:
#   COST_AND_PRICE  normal - vendor cost change triggers buyer retail adjustment
#   COST_ONLY       cost changed, buyer holds retail (margin absorbed)
#   PRICE_ONLY      retail adjusted for competitive/market reasons, no cost change
# ============================================================
class ChangeHistory(models.Model):

    CHANGE_TYPE_CHOICES = [
        ('COST_AND_PRICE', 'Cost & Price Change'),
        ('COST_ONLY',      'Cost Change Only'),
        ('PRICE_ONLY',     'Price Change Only'),
    ]

    SOURCE_CHOICES = [
        ('MANUAL',      'Manual Entry'),
        ('IMPORT',      'File Import'),
        ('PORTAL',      'Vendor Portal'),
        ('BRDATA_SYNC', 'BRData Sync'),
        ('SYSTEM',      'System'),
    ]

    PRICE_REASON_CHOICES = [
        ('COMPETITIVE', 'Competitive Response'),
        ('MARKET',      'Market Condition'),
        ('CORRECTION',  'Price Correction'),
        ('OTHER',       'Other'),
    ]

    # No FK to Item — history survives item deletion
    vendor_code     = models.CharField(max_length=20)
    upc             = models.CharField(max_length=14)
    change_date     = models.DateTimeField(auto_now_add=True)
    change_type     = models.CharField(max_length=20,
                        choices=CHANGE_TYPE_CHOICES,
                        default='COST_AND_PRICE')

    # Cost change (vendor side)
    old_case_cost   = models.DecimalField(max_digits=10, decimal_places=2,
                        null=True, blank=True)
    old_allowance   = models.DecimalField(max_digits=10, decimal_places=2,
                        null=True, blank=True)
    new_case_cost   = models.DecimalField(max_digits=10, decimal_places=2,
                        null=True, blank=True)
    new_allowance   = models.DecimalField(max_digits=10, decimal_places=2,
                        null=True, blank=True)

    # Price change (buyer side)
    old_retail      = models.DecimalField(max_digits=10, decimal_places=2,
                        null=True, blank=True)
    new_retail      = models.DecimalField(max_digits=10, decimal_places=2,
                        null=True, blank=True)
    old_margin      = models.DecimalField(max_digits=5, decimal_places=4,
                        null=True, blank=True)
    new_margin      = models.DecimalField(max_digits=5, decimal_places=4,
                        null=True, blank=True)

    # Attribution
    changed_by              = models.CharField(max_length=50, blank=True, null=True)
    change_source           = models.CharField(max_length=20,
                                choices=SOURCE_CHOICES, default='MANUAL')
    pending_cost_change_id  = models.IntegerField(null=True, blank=True,
                                help_text='ID of the PendingCostChange that triggered this')
    price_change_reason     = models.CharField(max_length=20,
                                choices=PRICE_REASON_CHOICES,
                                blank=True, null=True,
                                help_text='Required for PRICE_ONLY changes')
    notes                   = models.TextField(blank=True, null=True)

    class Meta:
        db_table            = 'dsd_change_history'
        ordering            = ['-change_date']
        verbose_name        = 'Change History'
        verbose_name_plural = 'Change History'
        indexes             = [
            models.Index(fields=['vendor_code', 'upc']),
            models.Index(fields=['change_date']),
            models.Index(fields=['change_type']),
        ]

    def __str__(self):
        return f'{self.vendor_code}/{self.upc} — {self.change_type} @ {self.change_date:%Y-%m-%d}'


# ============================================================
# BRDATA EXPORT LOG
# ============================================================
class BRDataExportLog(models.Model):

    EXPORT_TYPE_CHOICES = [
        ('PRICE_CHANGE', 'Price Change'),
        ('NEW_ITEM',     'New Item'),
        ('DISCO',        'Discontinue'),
        ('TPR',          'Temporary Price Reduction'),
    ]

    STATUS_CHOICES = [
        ('PENDING',   'Pending'),
        ('SENT',      'Sent'),
        ('CONFIRMED', 'Confirmed'),
        ('FAILED',    'Failed'),
    ]

    export_date     = models.DateTimeField(auto_now_add=True)
    export_type     = models.CharField(max_length=20, choices=EXPORT_TYPE_CHOICES)
    vendor_code     = models.CharField(max_length=20)
    upc             = models.CharField(max_length=14)
    brdata_item_no  = models.CharField(max_length=20, blank=True, null=True)
    new_retail      = models.DecimalField(max_digits=10, decimal_places=2,
                        null=True, blank=True)
    effective_date  = models.DateField(null=True, blank=True)
    export_status   = models.CharField(max_length=20, choices=STATUS_CHOICES,
                        default='PENDING')
    export_file     = models.CharField(max_length=200, blank=True, null=True)
    error_message   = models.TextField(blank=True, null=True)
    exported_by     = models.CharField(max_length=50, blank=True, null=True)
    confirmed_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table            = 'dsd_brdata_export_log'
        ordering            = ['-export_date']
        verbose_name        = 'BRData Export Log'
        verbose_name_plural = 'BRData Export Log'

    def __str__(self):
        return f'{self.export_type} / {self.vendor_code} / {self.upc} — {self.export_status}'


# ============================================================
# VENDOR IMPORT LOG
# ============================================================
class VendorImportLog(models.Model):

    SOURCE_CHOICES = [
        ('EXCEL',  'Excel Spreadsheet'),
        ('EMAIL',  'Email Attachment'),
        ('MANUAL', 'Manual Entry'),
        ('PORTAL', 'Vendor Portal'),
        ('API',    'API'),
    ]

    STATUS_CHOICES = [
        ('PENDING',  'Pending'),
        ('COMPLETE', 'Complete'),
        ('FAILED',   'Failed'),
    ]

    import_date         = models.DateTimeField(auto_now_add=True)
    vendor              = models.ForeignKey(
                            Vendor, on_delete=models.RESTRICT,
                            related_name='import_logs',
                            db_column='vendor_code')
    filename            = models.CharField(max_length=200, blank=True, null=True)
    import_source       = models.CharField(max_length=20, choices=SOURCE_CHOICES,
                            default='EXCEL')
    records_processed   = models.IntegerField(default=0)
    records_updated     = models.IntegerField(default=0)
    records_added       = models.IntegerField(default=0)
    records_skipped     = models.IntegerField(default=0)
    records_error       = models.IntegerField(default=0)
    import_status       = models.CharField(max_length=20, choices=STATUS_CHOICES,
                            default='PENDING')
    error_log           = models.TextField(blank=True, null=True)
    imported_by         = models.ForeignKey(
                            User, on_delete=models.SET_NULL,
                            null=True, blank=True,
                            related_name='import_logs')

    class Meta:
        db_table            = 'dsd_vendor_import_log'
        ordering            = ['-import_date']
        verbose_name        = 'Vendor Import Log'
        verbose_name_plural = 'Vendor Import Logs'

    def __str__(self):
        return f'{self.vendor_id} — {self.filename} ({self.import_status})'


# ============================================================
# VENDOR IMPORT COLUMN MAPPING
# Saves each vendor's Excel column layout for future imports
# ============================================================
class VendorImportMapping(models.Model):

    vendor          = models.ForeignKey(
                        Vendor, on_delete=models.CASCADE,
                        related_name='import_mappings',
                        db_column='vendor_code')
    mapping_name    = models.CharField(max_length=50, default='default')
    upc_column      = models.CharField(max_length=10, blank=True, null=True)
    description_column  = models.CharField(max_length=10, blank=True, null=True)
    case_cost_column    = models.CharField(max_length=10, blank=True, null=True)
    allowance_column    = models.CharField(max_length=10, blank=True, null=True)
    effective_date_column = models.CharField(max_length=10, blank=True, null=True)
    case_pack_column    = models.CharField(max_length=10, blank=True, null=True)
    header_row      = models.IntegerField(default=1)
    sheet_name      = models.CharField(max_length=100, blank=True, null=True,
                        help_text='Sheet name for multi-tab Excel files')
    notes           = models.TextField(blank=True, null=True)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        db_table            = 'dsd_vendor_import_mapping'
        unique_together     = [('vendor', 'mapping_name')]
        verbose_name        = 'Vendor Import Mapping'
        verbose_name_plural = 'Vendor Import Mappings'

    def __str__(self):
        return f'{self.vendor_id} — {self.mapping_name}'
