import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('isell_ecommerce')

app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()

app.conf.task_routes = {
    'apps.v1.product.tasks.import_products_task': {'queue': 'celery'},
}

app.conf.task_ignore_result = False
app.conf.task_reject_on_worker_lost = True