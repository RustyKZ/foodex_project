from django.db import models

class Order(models.Model):
    date = models.IntegerField('Order date', default=0)
    name = models.CharField('Order name', max_length=255, blank=True, default="")
    avatar = models.CharField('Avatar path', max_length=255, blank=True, default="")
    supplier_id = models.IntegerField('ID (supplier)', default=0)
    customer_id = models.IntegerField('ID (customer)', default=0)
    individual_id = models.IntegerField('ID (individual)', default=0)
    delivery_date = models.IntegerField('Delivery date (Unixtime)', default=0)    
    status = models.CharField('Order status', max_length=50, blank=True, default="")
    cart = models.JSONField(default=list, blank=True)
    cart_order_date = models.CharField('Delivery date', max_length=50, blank=True, default="")
    customer_comment = models.TextField("Reply", default="", blank=True)
    subtotal = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    delivery_cost = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    missed_price = models.BooleanField(default=False)
    last_update = models.IntegerField('Last update date', default=0)
    update_timeline = models.JSONField(default=dict, blank=True, help_text='Update statuses by Unixtime, e.g. {"1773134918": "created", "1773139923": "live", "1773148923": "completed"}')
    request_free_delivery = models.BooleanField(default=False)
    currency = models.CharField(max_length=100, blank=True, default="USD")
    deleted = models.BooleanField(default=False)
    dispute = models.JSONField(default=dict, blank=True, help_text='dispute detail between suuplier and customer')
    dispute_resolved_by_supplier_side = models.BooleanField(default=False)
    dispute_resolved_by_customer_side = models.BooleanField(default=False)
    rated_customer = models.BooleanField(default=False)
    rated_supplier = models.BooleanField(default=False)
    supplier_date = models.CharField('Supplier date', max_length=50, blank=True, default="")
    supplier_ttl = models.IntegerField('Supplier TTL', default=0)

    class Meta:
        db_table = 'orders'

    def __str__(self):
        return str(self.id)


class OrderItem(models.Model):
    order_id = models.IntegerField('Order ID (supplier)', default=0)
    product_id = models.IntegerField('Product ID (individual)', default=0)
    measure_code = models.CharField('Unit of measure', max_length=50, blank=True, default="")
    amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    price = models.DecimalField('Price for 1 unit of measure', max_digits=16, decimal_places=2, default=0)
    cost = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    confirmed = models.BooleanField(default=False)
    product_snapshot = models.JSONField(default=dict, blank=True)
    rated = models.BooleanField(default=False)

    class Meta:
        db_table = 'order_item'

    def __str__(self):
        return str(self.id)
    