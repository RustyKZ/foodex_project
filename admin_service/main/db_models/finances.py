from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal

class TariffPlan(models.Model):
    
    #    tariff_id = models.IntegerField('Tariff ID', unique=True, blank=True, null=True)
    slug = models.CharField('Slug', max_length=255, unique=True, blank=True, null=True)
    name = models.CharField('Default name', max_length=255, blank=True, default="")
    active = models.BooleanField(default=False)

    local_names = models.JSONField('Tariff local names', blank=True, default=dict)

    day_cost = models.DecimalField('Day cost', max_digits=16, decimal_places=2, default=0)
    month_cost = models.DecimalField('Month cost', max_digits=16, decimal_places=2, default=0)
    year_cost = models.DecimalField('Year cost', max_digits=16, decimal_places=2, default=0)
    
    features = models.JSONField('Features', blank=True, default=dict)

    class Meta:
        db_table = 'tariff_plan'

    def __str__(self):
        return self.slug


class AdCampaignBusinessPromo(models.Model):
    business_id = models.IntegerField('Business ID', default=0)
    initiator_user_id = models.IntegerField('Initiator user ID', default=0)
    deposit_credits = models.DecimalField('Deposit credits', max_digits=16, decimal_places=2, default=0)
    daily_credits = models.DecimalField('Daily credits', max_digits=16, decimal_places=2, default=0)
    remaining_credits = models.DecimalField('Remaining credits', max_digits=16, decimal_places=2, default=0)
    date_start = models.IntegerField('Campaign date start', default=0)
    date_end = models.IntegerField('Campaign date end', default=0)    
    log = models.JSONField('Campaign log', blank=True, default=list)
    active = models.BooleanField(default=True)
    deleted = models.BooleanField(default=False)
    date_next_charge = models.IntegerField('Next charge date', default=0)

    class Meta:
        db_table = 'ad_campaign_business_promo'

    def __str__(self):
        return str(self.id)

class PaymentMethodType(models.TextChoices):
    INSTANT = "instant", "Instant"
    REDIRECT = "redirect", "Redirect"
    SDK = "sdk", "SDK"


class PaymentMethod(models.Model):
    code = models.CharField('Code of method', max_length=50, unique=True)    
    type = models.CharField(max_length=50, choices=PaymentMethodType.choices, default=PaymentMethodType.REDIRECT,)
    name = models.CharField('Name of payment method', max_length=255, blank=True, default="")
    name_translations = models.JSONField('Name translations', blank=True, default=dict)
    description = models.TextField('Payment description', blank=True, default="")
    description_translations = models.JSONField('Description translations', blank=True, default=dict)
    logo = models.CharField('Logo filename', max_length=255, blank=True, default="")
    currency = models.CharField(max_length=50, blank=True, default="USD")
    merchant_id = models.CharField('Merchant ID (Optional)', max_length=255, blank=True, default="")
    credits_per_unit = models.DecimalField('App credits per 1 unit of currency', max_digits=16, decimal_places=2, default=0)
    custom_options = models.JSONField('Custom options', blank=True, default=dict)
    active = models.BooleanField(default=False)
    show_on_frontend = models.BooleanField(default=False)
    referrer_payback = models.BooleanField(default=False)
    payback_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100),])    
    min_payment_value = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("1"))
    max_payment_value = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("1000000"))
    priority = models.IntegerField('Priority', default=0)

    class Meta:
        db_table = 'payment_methods'

    def __str__(self):
        return self.code
    

class Payment(models.Model):
    date = models.IntegerField('Payment date', default=0)
    method_code = models.CharField('Code of payment method', max_length=50, default="")
    user_id = models.IntegerField('User ID', default=0)
    amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    currency = models.CharField(max_length=50, blank=True, default="USD")
    credits_received = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    referrer_id = models.IntegerField('Referrer user ID', default=0)
    credits_payback = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    details = models.JSONField('Payment details', blank=True, default=dict)
    confirmed = models.BooleanField('Payments COMFIRMED via API', default=False)
    processed = models.BooleanField('Payment PROCESSED - Credits have been awarded to the user', default=False)
    deleted = models.BooleanField('Payment DELETED', default=False)
    order_id = models.CharField('Transaction order ID', max_length=255, blank=True, default="")

    class Meta:
        db_table = 'payments'

    def __str__(self):
        return str(self.id)
    

class StarPaymentData(models.Model):
    date = models.IntegerField('Payment date', default=0)
    tg_id = models.BigIntegerField('User TG_ID', blank=True, null=True)
    amount = models.IntegerField('Stars amount', default=0)
    charge_id = models.CharField('Charghe ID', max_length=255, unique=True, blank=True, null=True)
    payload = models.CharField('Payload', max_length=255, default="")
    processed = models.BooleanField(help_text='Payment PROCESSED - Credits have been awarded to the user', default=False)
    payment_id = models.IntegerField('Payment ID', unique=True, blank=True, null=True)

    class Meta:
        db_table = 'star_payment_data'

    def __str__(self):
        return str(self.id)
