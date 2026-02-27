"""
DSD Price Book - Utility Functions
pricebook_manager / dsd / utils / pricing.py
"""

import re
from decimal import Decimal, ROUND_UP


# ============================================================
# UPC UTILITIES
# ============================================================

def normalize_upc(raw_upc):
    """
    Strip all non-numeric characters from UPC.
    Handles hyphens, spaces, and any other formatting characters.
    Returns None if result is empty.
    """
    if raw_upc is None:
        return None
    cleaned = re.sub(r'\D', '', str(raw_upc)).strip()
    return cleaned if cleaned else None


def validate_upc(upc):
    """
    Validate a normalized UPC.
    Valid lengths: 12 (UPC-A), 13 (EAN-13), 14 (ITF-14)
    Returns (is_valid, message)
    """
    if not upc:
        return False, 'UPC is empty'
    if not upc.isdigit():
        return False, f'UPC contains non-numeric characters: {upc}'
    if len(upc) not in (12, 13, 14):
        return False, f'UPC length {len(upc)} is invalid (expected 12, 13, or 14)'
    return True, 'OK'


# ============================================================
# RETAIL PRICING UTILITIES
# ============================================================

def suggest_retail(new_unit_cost, current_margin):
    """
    Calculate suggested retail price.
    - Maintains the current GM% as closely as possible
    - Final price always ends in .X8 (Cost Less pricing convention)

    Examples:
        unit_cost=$4.50, margin=29.5% -> theoretical=$6.38 -> suggested=$6.48
        unit_cost=$4.62, margin=29.5% -> theoretical=$6.55 -> suggested=$6.58
        unit_cost=$6.80, margin=29.5% -> theoretical=$9.65 -> suggested=$9.78

    Returns Decimal or None if inputs are invalid.
    """
    if new_unit_cost is None or current_margin is None:
        return None

    unit_cost = Decimal(str(new_unit_cost))
    margin = Decimal(str(current_margin))

    if margin <= 0 or margin >= 1:
        return None
    if unit_cost <= 0:
        return None

    # Theoretical retail at exact margin
    theoretical = unit_cost / (1 - margin)

    # Find the next price ending in .X8 >= theoretical
    # Candidate endings: .08, .18, .28, .38, .48, .58, .68, .78, .88, .98
    # Then 1.08, 1.18, etc.

    # Work in cents to avoid float precision issues
    theoretical_cents = int(theoretical * 100)

    # Find remainder when dividing by 10
    remainder = theoretical_cents % 10

    if remainder <= 8:
        # Round up to the 8 in the current ten-cent band
        suggested_cents = theoretical_cents - remainder + 8
    else:
        # Already past the 8, go to next band
        suggested_cents = theoretical_cents - remainder + 18

    # Ensure we didn't go below theoretical due to rounding
    if suggested_cents < theoretical_cents:
        suggested_cents += 10

    suggested = Decimal(suggested_cents) / 100

    return suggested.quantize(Decimal('0.01'))


def calculate_margin(retail_price, unit_cost):
    """
    Calculate GM% given retail price and unit cost.
    Returns Decimal or None.
    """
    if not retail_price or not unit_cost:
        return None
    retail = Decimal(str(retail_price))
    cost = Decimal(str(unit_cost))
    if retail <= 0:
        return None
    return ((retail - cost) / retail).quantize(Decimal('0.0001'))


def calculate_margin_pct_display(retail_price, unit_cost):
    """Returns margin as a display string e.g. '28.5%'"""
    margin = calculate_margin(retail_price, unit_cost)
    if margin is None:
        return None
    return f'{margin * 100:.1f}%'
