"""
Application service for handling Grist application logic.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor

from apps.v1.product.constants import ApplicationStages, TimeConstants
from apps.v1.order.models import Orders, OrderItems

logger = logging.getLogger(__name__)


class ApplicationService:
    """Service for handling application-related business logic"""
    
    @staticmethod
    def has_active_orders(user) -> bool:
        """
        Check if user has any active orders (not FINISHED).
        
        Args:
            user: CustomUser instance
            
        Returns:
            bool: True if user has active orders, False otherwise
        """
        if not user:
            return False
        
        active_orders = Orders.objects.filter(
            user=user,
            status__in=[Orders.Status.PREPARING, Orders.Status.READY, Orders.Status.DELIVERING]
        ).exists()
        
        return active_orders
    
    @staticmethod
    def has_denied_by_client_for_products(
        applications: List[Dict],
        counterparty_id: int,
        product_list: List[Dict]
    ) -> bool:
        """
        Check if there's a 'Denied by client' application for specific products.
        
        Args:
            applications: List of application records from Grist
            counterparty_id: Counterparty ID
            product_list: List of products from request
            
        Returns:
            bool: True if denied by client for these products
        """
        if not applications or not counterparty_id or not product_list:
            return False
        
        try:
            from apps.v1.product.views import compare_application_products_with_request
            
            for app in applications:
                app_counterparty_id = app.get('fields', {}).get('counterparty_id')
                app_stage = app.get('fields', {}).get('stage', '')
                
                if (app_counterparty_id == counterparty_id and 
                    app_stage == ApplicationStages.DENIED_BY_CLIENT):
                    app_products_match = compare_application_products_with_request(app, product_list)
                    if app_products_match:
                        return True
            
            return False
        except Exception as e:
            logger.error(f"Error checking denied by client: {e}", exc_info=True)
            return False
    
    @staticmethod
    def has_accepted_but_not_in_orders(
        user,
        applications: List[Dict],
        counterparty_id: int,
        product_list: List[Dict]
    ) -> bool:
        """
        Check if there's an 'Accepted' application but products are not in OrderItems.
        Agar oxirgi application "Accepted" bo'lsa va hali Order tablega qo'shilmagan bo'lsa,
        har qanday yangi zayavka yaratilmasligi kerak (mahsulotlar mos kelmasa ham).
        
        Args:
            user: CustomUser instance
            applications: List of application records from Grist
            counterparty_id: Counterparty ID
            product_list: List of products from request
            
        Returns:
            bool: True if accepted but not in orders
        """
        if not user or not applications or not counterparty_id:
            return False
        
        try:
            from apps.v1.product.views import get_latest_application_by_counterparty, get_product_names_and_variation_ids_from_price_table_record_ids
            from apps.v1.product.models import Products, ProductIDs
            
            # Oxirgi application'ni topish
            latest_app = get_latest_application_by_counterparty(applications, counterparty_id)
            
            if not latest_app:
                return False
            
            latest_stage = latest_app.get('fields', {}).get('stage', '')
            
            # Agar oxirgi application "Accepted" bo'lsa
            if latest_stage == ApplicationStages.ACCEPTED:
                # Application'dagi barcha mahsulotlarni olish
                app_products = latest_app.get('fields', {}).get('products', [])
                
                if not app_products:
                    return False
                
                # Application'dagi mahsulotlarni Order tablega qo'shilganligini tekshirish
                app_product_data = get_product_names_and_variation_ids_from_price_table_record_ids(app_products)
                
                # Har bir application mahsuloti uchun Order tablega qo'shilganligini tekshirish
                for product_name, variation_id_str in app_product_data:
                    try:
                        # Product name orqali product_id ni topish
                        product = Products.objects.filter(name=product_name).first()
                        if not product:
                            continue
                        
                        product_id = product.id
                        
                        # Variation_id bo'lsa, uni topish
                        if variation_id_str:
                            product_id_obj = ProductIDs.objects.filter(
                                product_id=product_id,
                                variation_id=variation_id_str
                            ).first()
                            
                            if product_id_obj:
                                order_item_exists = OrderItems.objects.filter(
                                    order__user=user,
                                    product_id=product_id,
                                    variation__variation_id=variation_id_str
                                ).exists()
                            else:
                                # Variation topilmasa, faqat product_id bilan tekshirish
                                order_item_exists = OrderItems.objects.filter(
                                    order__user=user,
                                    product_id=product_id
                                ).exists()
                        else:
                            # Variation_id bo'lmasa, faqat product_id bilan tekshirish
                            order_item_exists = OrderItems.objects.filter(
                                order__user=user,
                                product_id=product_id,
                                variation__isnull=True
                            ).exists()
                        
                        # Agar bitta ham mahsulot Order tablega qo'shilmagan bo'lsa, True qaytarish
                        if not order_item_exists:
                            return True
                    except Exception:
                        continue
                
                # Agar barcha mahsulotlar Order tablega qo'shilgan bo'lsa, False qaytarish
                return False
            
            return False
        except Exception as e:
            logger.error(f"Error checking accepted but not in orders: {e}", exc_info=True)
            return False
    
    @staticmethod
    def has_denied_within_cooldown(
        applications: List[Dict],
        counterparty_id: int,
        cooldown_days: int = TimeConstants.DENIED_COOLDOWN_DAYS
    ) -> bool:
        """
        Check if there's a 'Denied' application within cooldown period.
        
        Args:
            applications: List of application records from Grist
            counterparty_id: Counterparty ID
            cooldown_days: Number of days to wait after denial (default: 30)
            
        Returns:
            bool: True if denied within cooldown period
        """
        if not applications or not counterparty_id:
            return False
        
        try:
            for app in applications:
                app_counterparty_id = app.get('fields', {}).get('counterparty_id')
                app_stage = app.get('fields', {}).get('stage', '')
                
                if (app_counterparty_id == counterparty_id and 
                    app_stage == ApplicationStages.DENIED):
                    denied_date = app.get('fields', {}).get('date', 0)
                    
                    if denied_date:
                        if isinstance(denied_date, (int, float)):
                            denied_datetime = datetime.fromtimestamp(denied_date)
                            current_datetime = datetime.now()
                            days_passed = (current_datetime - denied_datetime).days
                            
                            if days_passed < cooldown_days:
                                return True
            
            return False
        except Exception as e:
            logger.error(f"Error checking denied within cooldown: {e}", exc_info=True)
            return False
    
    @staticmethod
    def should_post_to_grist(
        user,
        applications: List[Dict],
        counterparty_id: Optional[int],
        product_list: List[Dict]
    ) -> Tuple[bool, Optional[str]]:
        """
        Determine if application should be posted to Grist.
        
        Args:
            user: CustomUser instance
            applications: List of application records from Grist
            counterparty_id: Counterparty ID
            product_list: List of products from request
            
        Returns:
            tuple: (should_post: bool, reason: str or None)
        """
        # Check active orders
        if ApplicationService.has_active_orders(user):
            return False, "User has active orders"
        
        if not counterparty_id:
            return True, None
        
        # Note: "Denied by client" holatida ham yangi application yaratishga ruxsat beriladi
        # (xuddi "Success" kabi), shuning uchun bu tekshiruv olib tashlandi
        
        # Check accepted but not in orders
        if ApplicationService.has_accepted_but_not_in_orders(
            user, applications, counterparty_id, product_list
        ):
            return False, "Accepted application not yet in orders"
        
        # Check denied within cooldown
        if ApplicationService.has_denied_within_cooldown(applications, counterparty_id):
            return False, "Denied within cooldown period"
        
        return True, None

