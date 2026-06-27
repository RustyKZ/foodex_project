from django.db import models

class AppUser(models.Model):
    
    tg_id = models.BigIntegerField('User TG_ID', unique=True, blank=True, null=True)
    tg_firstname = models.CharField('User TG_firstname', max_length=255, blank=True, default="")
    tg_lastname = models.CharField('User TG_lastname', max_length=255, blank=True, default="")
    tg_username = models.CharField('User TG_username', max_length=255, unique=True, blank=True, null=True)
    username = models.CharField('Application username', max_length=255, blank=True, default="")
    
    reg_date = models.IntegerField('User registration date (Unixtime)', default=0)
    referrer_id = models.IntegerField('Referer ID', default=0)
    referrer_username = models.CharField('Referer app username', max_length=255, blank=True, default="")
    language = models.CharField('User interface language (tg)', max_length=5, default="en")

    last_activity = models.IntegerField('User last activity (Unixtime)', default=0)
    instance_id = models.CharField('Instance ID', max_length=255, blank=True, default="")
    sid = models.CharField('Socket SID', max_length=255, blank=True, default="")
        
    tab_notify = models.JSONField('Tab notify', blank=True, default=dict)
    active = models.BooleanField(default=True)
    
    active_business_id = models.IntegerField('Active business ID', default=0)
    business_list = models.JSONField('Businesses list', blank=True, default=list)

    individual_id = models.IntegerField('Individual customer business ID', default=0)
        
    contacts_allowed = models.JSONField('Contact list ALLOWED', blank=True, default=list)
    contacts_incoming = models.JSONField('Contact list INCOMING', blank=True, default=list)
    contacts_outcoming = models.JSONField('Contact list OUTCOMING', blank=True, default=list)

    credits = models.DecimalField('Credits', max_digits=16, decimal_places=2, default=0)
    phone = models.CharField('Phone', max_length=255, unique=True, blank=True, null=True)
    is_phone_verified = models.BooleanField(default=False)
    email = models.CharField('Email', max_length=255, unique=True, blank=True, null=True)
    is_email_verified = models.BooleanField(default=False)

    settings = models.JSONField('Settings', blank=True, default=dict)

    referrals = models.JSONField('Referral list', blank=True, default=list)
    referral_bonus = models.DecimalField('Referral bonus', max_digits=16, decimal_places=2, default=0)

    limit_of_business = models.IntegerField('Limit of businesses', default=10)

    dict_of_username = models.JSONField('Dict of usernames', blank=True, default=dict)

    outcoming_employer_business_id = models.IntegerField('Business ID (Potential employer)', default=0)
    outcoming_employer_business_name = models.CharField('Business name (Potential employer)', max_length=255, blank=True, default="")
    outcoming_request_delete_date = models.IntegerField('User can delete join request (Unixtime)', default=0)

    favorite_businesses = models.JSONField('Favorite businesses', blank=True, default=list)
    favorite_products = models.JSONField('Favorite products', blank=True, default=list)    

    class Meta:
        db_table = 'app_users'

    def __str__(self):
        return self.username
    
    

class UserGreylist(models.Model):
    user_id = models.IntegerField('User App ID', unique=True, blank=True, null=True)
    tg_id = models.BigIntegerField('User TG_ID', unique=True, blank=True, null=True)
    phone = models.CharField('Phone', max_length=255, unique=True, blank=True, null=True)
    email = models.CharField('Email', max_length=255, unique=True, blank=True, null=True)
    ip_address = models.CharField('IP address', max_length=255, blank=True, default="")
    add_date = models.IntegerField('Add greylist date (Unixtime)', default=0)
    log = models.JSONField('Activity log', blank=True, default=list)

    class Meta:
        db_table = 'users_greylist'

    def __str__(self):
        return str(self.user_id)
    

class UserBlacklist(models.Model):
    user_id = models.IntegerField('User App ID', unique=True, blank=True, null=True)
    tg_id = models.BigIntegerField('User TG_ID', unique=True, blank=True, null=True)
    phone = models.CharField('Phone', max_length=255, unique=True, blank=True, null=True)
    email = models.CharField('Email', max_length=255, unique=True, blank=True, null=True)
    ip_address = models.CharField('IP address', max_length=255, blank=True, default="")
    add_date = models.IntegerField('Add blacklist date (Unixtime)', default=0)
    log = models.JSONField('Activity log', blank=True, default=list)

    class Meta:
        db_table = 'users_blacklist'

    def __str__(self):
        return str(self.user_id)