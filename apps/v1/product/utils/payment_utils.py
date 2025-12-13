"""
Payment calculation utilities.
"""

from datetime import datetime, timedelta
from calendar import monthrange


def get_tariff_coefficient_ratio(tariff):
    """
    Calculate tariff coefficient ratio safely, avoiding division by zero.
    
    Args:
        tariff: Tariffs instance with coefficient and payments_count attributes
        
    Returns:
        float: Coefficient ratio (coefficient / payments_count)
    """
    coefficient = tariff.coefficient if tariff.coefficient and tariff.coefficient > 0 else 1
    payments_count = tariff.payments_count if tariff.payments_count and tariff.payments_count > 0 else 1
    return coefficient / payments_count


def calculate_monthly_payment_amount(total_amount, tariff):
    """
    Calculate monthly payment amount based on total amount and tariff.
    
    Args:
        total_amount: float - Total amount after down payment
        tariff: Tariffs instance
        
    Returns:
        int: Monthly payment amount (rounded)
    """
    if total_amount <= 0:
        return 0
    
    coefficient_ratio = get_tariff_coefficient_ratio(tariff)
    return round(total_amount * coefficient_ratio)


def generate_monthly_payments(tariff, total_amount, start_date=None):
    """
    Generate monthly payment schedule.
    
    Args:
        tariff: Tariffs instance
        total_amount: float - Total amount to pay monthly
        start_date: datetime - Start date (defaults to now)
        
    Returns:
        list: List of payment dictionaries with number, date, and payment amount
    """
    if start_date is None:
        start_date = datetime.now()
    
    monthly_payments = []
    safe_payments_count = tariff.payments_count if tariff.payments_count and tariff.payments_count > 0 else 1
    
    for month_num in range(1, safe_payments_count + 1):
        year = start_date.year
        month = start_date.month + month_num
        day = start_date.day
        
        # Handle year overflow
        while month > 12:
            month -= 12
            year += 1
        
        # Handle day overflow (e.g., Feb 30 -> Feb 28/29)
        max_day = monthrange(year, month)[1]
        if day > max_day:
            day = max_day
        
        payment_date = datetime(year, month, day)
        
        # Apply offset days if tariff has it
        if tariff.offset_days:
            payment_date = payment_date + timedelta(days=tariff.offset_days)
        
        monthly_payments.append({
            "number": month_num,
            "date": payment_date.strftime("%d/%m/%y"),
            "payment": total_amount
        })
    
    return monthly_payments

