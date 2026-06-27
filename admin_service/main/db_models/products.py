from django.db import models


class Measure(models.Model):

    class MeasureSystem(models.IntegerChoices):
        BOTH = 0, 'Both'
        METRIC = 1, 'Metric'
        IMPERIAL = 2, 'Imperial'

    class MeasureType(models.IntegerChoices):
        OTHER = 0, 'Other'
        WEIGHT = 1, 'Weight'
        VOLUME = 2, 'Volume'
        LENGTH = 3, 'Length'
        COUNT = 4, 'Count'

    code = models.CharField('Code', max_length=50, unique=True, help_text='Stable code, e.g. kg, l, pcs')
    name = models.CharField('Full name (EN)', max_length=100)
    name_short = models.CharField('Short name (EN)', max_length=50)
    dict_names = models.JSONField('Localized full names', default=dict, blank=True)
    dict_names_short = models.JSONField('Localized short names', default=dict, blank=True)
    system = models.IntegerField('System of measure', choices=MeasureSystem.choices, default=MeasureSystem.BOTH)
    type = models.IntegerField('Type of measure', choices=MeasureType.choices, default=MeasureType.OTHER)
    active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)

    class Meta:
        db_table = 'measures'
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.code} ({self.name_short})"


class Product(models.Model):
    
    business_id = models.IntegerField('Business ID (creator)', default=0)
    date = models.IntegerField('Create date (Unixtime)', default=0)
    avatar_name = models.CharField('Avatar path', max_length=255, blank=True, default="")
    name = models.CharField('Product name', max_length=255, blank=True, default="")    
    description = models.TextField('Product description', blank=True, default="")
    measure_code = models.CharField('Unit of measure', max_length=50, blank=True, default="")
    pack_params = models.CharField('Pack params decription', max_length=255, blank=True, default="")
    price = models.DecimalField('Price for 1 unit of measure', max_digits=16, decimal_places=2, default=0)
    min_order_quantity = models.DecimalField(max_digits=16, decimal_places=2, default=1)
    max_order_quantity = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    sku = models.CharField('SKU', max_length=50, blank=True, default="")
    category_code = models.CharField(max_length=50, blank=True, default="")
    active = models.BooleanField(default=True)
    daily_limit = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    language = models.CharField('Product primary language', max_length=5, default="en")
    individual_customer = models.BooleanField(default=False)
    shipment_same_day = models.BooleanField(default=False)
    shipment_hours = models.IntegerField('Average shipment hours', default=0)
    shipment_price = models.DecimalField('Shipment price', max_digits=16, decimal_places=2, default=0)

    deleted = models.BooleanField(default=False)

    class Meta:
        db_table = 'products'

    def __str__(self):
        return str(self.id)
    

class ProductTranslation(models.Model):
    product_id = models.IntegerField('Product ID', default=0)
    language = models.CharField('Product interface language (tg)', max_length=5, default="en")
    
    name = models.CharField('Product name', max_length=255, blank=True, default="")
    description = models.TextField('Product description', blank=True, default="")
    pack_params = models.CharField('Pack params decription', max_length=255, blank=True, default="")
    
    class Meta:
        db_table = 'product_translation'

    def __str__(self):
        return str(self.id)
    

class Category(models.Model):
    code = models.CharField(max_length=50, unique=True, db_index=True, help_text="Stable code, e.g. fruits, dairy")
    name = models.CharField(max_length=255, help_text="Default name (EN)")
    dict_names = models.JSONField(default=dict, blank=True, help_text='Localized names, e.g. {"ru": "Фрукты"}')
    active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)

    class Meta:
        db_table = 'categories'
        ordering = ['order', 'id']

    def __str__(self):
        return self.code

