from celery import shared_task
from apps.v1.product.integrations.product_import import import_all_products
import logging

logger = logging.getLogger(__name__)


@shared_task
def import_products_task():
    """Задача для автоматического импорта продуктов"""
    try:
        logger.info('Начинаю автоматический импорт продуктов')
        results = import_all_products()
        
        if results.get('overall_success'):
            logger.info('Автоматический импорт продуктов успешно завершен')
            return {'success': True, 'message': 'Импорт успешно завершен'}
        else:
            logger.error('Ошибка при автоматическом импорте продуктов', extra={'results': results})
            return {'success': False, 'message': 'Ошибка при импорте', 'results': results}
    except Exception as e:
        logger.error(f'Ошибка при выполнении автоматического импорта: {str(e)}', exc_info=True)
        return {'success': False, 'message': str(e)}

