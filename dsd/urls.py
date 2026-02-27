"""
DSD Price Book Management System
URL Configuration
pricebook_manager / dsd / urls.py
"""

from django.urls import path
from . import views

app_name = 'dsd'

urlpatterns = [

    # Dashboard
    path('',
         views.dashboard,
         name='dashboard'),

    # Vendor List
    path('vendors/',
         views.vendor_list,
         name='vendor_list'),

    # Price Book for a single vendor
    path('vendors/<str:vendor_code>/',
         views.price_book,
         name='price_book'),

    # Item Detail
    path('vendors/<str:vendor_code>/items/<str:upc>/',
         views.item_detail,
         name='item_detail'),

    # Cost Change Entry for an item
    path('vendors/<str:vendor_code>/items/<str:upc>/change/',
         views.cost_change_entry,
         name='cost_change_entry'),

    # Pending Changes worklist
    path('pending/',
         views.pending_changes,
         name='pending_changes'),

    # Approve or Reject a change
    path('pending/<int:change_id>/approve/',
         views.approve_change,
         name='approve_change'),

    # Apply an approved change to live pricing
    path('pending/<int:change_id>/apply/',
         views.apply_change,
         name='apply_change'),

    # BRData Export
    path('export/brdata/',
         views.brdata_export,
         name='brdata_export'),
]
