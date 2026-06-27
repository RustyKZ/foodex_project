from django.db import models


class ReviewBusiness(models.Model):
    banned_by_admin = models.BooleanField(default=False)
    ban_reason = models.TextField("Review ban reason (admin)", default="", blank=True)

    date = models.IntegerField('Review date (Unixtime)', default=0)
    order_id = models.IntegerField('Order ID', default=0)
    business_id = models.IntegerField('Rated business ID', default=0)
    author_user_id = models.IntegerField('Author user ID', default=0)
    author_business_id = models.IntegerField('Author business ID', default=0)
    comment = models.TextField("Comment", default="", blank=True)
    reply = models.TextField("Reply", default="", blank=True)
    rate = models.IntegerField('Rate 1-5', default=0)
    
    class Meta:
        db_table = 'review_business'
        constraints = [
            models.UniqueConstraint(
                fields=['order_id', 'author_user_id', 'business_id'],
                name='uniq_review_business_per_order_user'
            )
        ]

    def __str__(self):
        return str(self.id)


class ReviewProduct(models.Model):
    banned_by_admin = models.BooleanField(default=False)
    ban_reason = models.TextField("Review ban reason (admin)", default="", blank=True)

    date = models.IntegerField('Review date (Unixtime)', default=0)
    product_id = models.IntegerField('Product ID', default=0)
    order_id = models.IntegerField('Order ID', default=0)
    business_id = models.IntegerField('Rated business ID', default=0)
    author_user_id = models.IntegerField('Author user ID', default=0)
    author_business_id = models.IntegerField('Author business ID', default=0)
    comment = models.TextField("Comment", default="", blank=True)
    reply = models.TextField("Reply", default="", blank=True)
    rate = models.IntegerField('Rate 1-5', default=0)
    
    class Meta:
        db_table = 'review_product'
        constraints = [
            models.UniqueConstraint(
                fields=['order_id', 'author_user_id', 'product_id'],
                name='uniq_review_product_per_order_user'
            )
        ]

    def __str__(self):
        return str(self.id)