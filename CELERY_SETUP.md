# Celery Setup va Ishga Tushirish

## 1. Redis Server ishga tushirish

Windows uchun Redis o'rnatilgan bo'lishi kerak. Agar yo'q bo'lsa:
- Redis Desktop Manager yoki WSL2 orqali Redis ishga tushiring
- Yoki Docker orqali: `docker run -d -p 6379:6379 redis`

## 2. Celery Worker ishga tushirish

Yangi terminal ochib quyidagi buyruqni bajaring:

```bash
celery -A config worker --loglevel=info --pool=solo
```

**Eslatma:** Windows uchun `--pool=solo` parametri majburiy!

## 3. Celery Beat ishga tushirish (Periodic Tasks uchun)

Yana bir yangi terminal ochib quyidagi buyruqni bajaring:

```bash
celery -A config beat --loglevel=info
```

## 4. Admin panel orqali Periodic Task sozlash

1. Django admin panelga kiring
2. `ProductAutomaticallyImportedTime` modeliga o'ting
3. Yangi yozuv yarating yoki mavjudni tahrirlang:
   - `time`: Interval (masalan: 30)
   - `time_type`: `minutes` yoki `hours`
   - `is_active`: ✅ (checkbox belgilang)
4. Saqlang - avtomatik ravishda periodic task yaratiladi

## 5. Barcha servislarni bir vaqtda ishga tushirish (Windows PowerShell)

```powershell
# Terminal 1: Django server
python manage.py runserver

# Terminal 2: Celery Worker
celery -A config worker --loglevel=info --pool=solo

# Terminal 3: Celery Beat
celery -A config beat --loglevel=info
```

## 6. Test qilish

Bir martalik taskni test qilish uchun:

```bash
python manage.py shell
```

```python
from apps.v1.product.tasks import import_products_task
result = import_products_task.delay()
print(result.get())
```

## 7. Loglarni ko'rish

Celery worker va beat loglarini terminalda ko'rasiz. Agar faylga saqlash kerak bo'lsa:

```bash
celery -A config worker --loglevel=info --pool=solo --logfile=celery_worker.log
celery -A config beat --loglevel=info --logfile=celery_beat.log
```

## 8. Redis'dagi eski tasklarni tozalash

Agar `Received unregistered task` xatoligi ko'rsangiz, Redis'dagi eski tasklarni tozalash kerak:

### Variant 1: Celery purge buyrug'i (Tavsiya etiladi)
```bash
celery -A config purge
```

### Variant 2: Python script orqali
```bash
python manage.py shell
```
```python
from clear_celery_tasks import *
# Script avtomatik ishlaydi
```

### Variant 3: Redis CLI orqali
```bash
redis-cli FLUSHDB
```
**Eslatma:** Bu barcha Redis ma'lumotlarini o'chiradi!

## Muammolar va Yechimlar

### "Received unregistered task" xatoligi
- Bu eski tasklar Redis'da qolgan bo'lishi mumkin
- **Yechim:** `celery -A config purge` buyrug'ini bajaring
- Yoki worker'ni to'xtatib, Redis'ni tozalang va qayta ishga tushiring

### Redis ulanmayapti
- Redis server ishga tushirilganligini tekshiring
- `.env` faylida `CELERY_BROKER_URL` va `CELERY_RESULT_BACKEND` to'g'ri sozlanganligini tekshiring

### Task ishlamayapti
- Celery worker ishga tushirilganligini tekshiring
- Django server ishga tushirilganligini tekshiring
- Admin panelda periodic task `enabled=True` bo'lishi kerak

### Windows da muammo
- `--pool=solo` parametrini ishlatishni unutmang
- Eventlet yoki gevent o'rniga `solo` pool ishlating

