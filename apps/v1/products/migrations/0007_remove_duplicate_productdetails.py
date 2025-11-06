# Generated manually to remove duplicates

from django.db import migrations


def remove_duplicate_productdetails(apps, schema_editor):
    ProductDetails = apps.get_model('products', 'ProductDetails')
    
    # Barcha ProductDetails yozuvlarini olamiz
    all_details = ProductDetails.objects.all()
    
    # Unikal kombinatsiyalarni saqlaymiz
    seen_combinations = set()
    to_delete = []
    
    for detail in all_details:
        combination = (
            detail.product_id,
            detail.color or '',
            detail.storage or '',
            detail.sim_card or ''
        )
        
        if combination in seen_combinations:
            to_delete.append(detail.id)
        else:
            seen_combinations.add(combination)
    
    # Dublikatlarni o'chiramiz
    if to_delete:
        ProductDetails.objects.filter(id__in=to_delete).delete()
        print(f"Deleted {len(to_delete)} duplicate ProductDetails entries")


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0005_remove_productcolor_product_and_more'),
    ]

    operations = [
        migrations.RunPython(remove_duplicate_productdetails),
    ]

