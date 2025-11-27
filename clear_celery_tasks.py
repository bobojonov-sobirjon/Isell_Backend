"""
Redis'dagi eski Celery tasklarini tozalash uchun script
"""
import redis
import os
from django.conf import settings

# Redis connection
redis_url = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
r = redis.from_url(redis_url)

# Celery queue'larni tozalash
try:
    # Celery queue'dagi barcha tasklarni o'chirish
    deleted = r.delete('celery')
    print(f"Celery queue tozalandi: {deleted} key o'chirildi")
    
    # Barcha Celery keylarini topish va o'chirish
    keys = r.keys('celery*')
    if keys:
        deleted_count = r.delete(*keys)
        print(f"Barcha Celery keylar tozalandi: {deleted_count} key o'chirildi")
    else:
        print("Celery keylar topilmadi")
    
    # Result backend'dagi eski resultlarni tozalash
    result_keys = r.keys('celery-task-meta-*')
    if result_keys:
        deleted_results = r.delete(*result_keys)
        print(f"Eski resultlar tozalandi: {deleted_results} key o'chirildi")
    else:
        print("Eski resultlar topilmadi")
    
    print("\n✅ Redis tozalandi! Endi Celery worker'ni qayta ishga tushiring.")
    
except Exception as e:
    print(f"❌ Xatolik: {e}")

