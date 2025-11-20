from django.core.management.base import BaseCommand
from apps.v1.product.models import ProductAutomaticallyImportedTime
from apps.v1.product.integrations.product_import import import_all_products
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Автоматический импорт продуктов на основе настроек времени'

    def handle(self, *args, **options):
        try:
            auto_import_time = ProductAutomaticallyImportedTime.objects.first()
            
            if not auto_import_time or not auto_import_time.time:
                self.stdout.write(
                    self.style.WARNING('Время автоматического импорта не настроено')
                )
                return
            
            self.stdout.write(
                self.style.SUCCESS(f'Начинаю автоматический импорт продуктов...')
            )
            
            results = import_all_products()
            
            if results.get('overall_success'):
                self.stdout.write(
                    self.style.SUCCESS('Автоматический импорт продуктов успешно завершен')
                )
                logger.info('Автоматический импорт продуктов успешно завершен')
            else:
                self.stdout.write(
                    self.style.ERROR('Ошибка при автоматическом импорте продуктов')
                )
                logger.error('Ошибка при автоматическом импорте продуктов', extra={'results': results})
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Ошибка при выполнении автоматического импорта: {str(e)}')
            )
            logger.error(f'Ошибка при выполнении автоматического импорта: {str(e)}', exc_info=True)

