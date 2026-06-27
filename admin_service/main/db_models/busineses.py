from django.db import models


class Business(models.Model):    

    business_type = models.IntegerField('Business type', default=1)

    owner_id = models.IntegerField('User ID', default=0)
    name = models.CharField('Business name', max_length=255, blank=True, default="")
    description = models.CharField('Business description', max_length=255, blank=True, default="")
    avatar_name = models.CharField('Avatar path', max_length=255, blank=True, default="")
    reg_date = models.IntegerField('Business registration date (Unixtime)', default=0)

    staff = models.JSONField('Staff IDs', blank=True, default=list)
    active_orders = models.JSONField('Active orders IDs', blank=True, default=list)
    closed_orders = models.JSONField('Closed orders IDs', blank=True, default=list)

    contacts_allowed = models.JSONField('Contact list ALLOWED', blank=True, default=list)
    contacts_incoming = models.JSONField('Contact list INCOMING', blank=True, default=list)
    contacts_outcoming = models.JSONField('Contact list OUTCOMING', blank=True, default=list)

    tariff = models.CharField('Tariff', max_length=50, default="free")
    end_tariff_date = models.IntegerField('End tariff date (Unixtime)', default=0)

    language = models.CharField('User interface language (tg)', max_length=5, default="en")
    extra_languages = models.JSONField('List of language labels', blank=True, default=list)

    address = models.CharField('Address', max_length=255, blank=True, default="")
    geopoint = models.BooleanField(default=False)
    latitude = models.DecimalField('Latitude', max_digits=9, decimal_places=6, default=0)
    longitude = models.DecimalField('Longitude', max_digits=9, decimal_places=6, default=0)

    timezone = models.CharField(max_length=255, blank=True, default="UTC")
    currency = models.CharField(max_length=50, blank=True, default="USD")

    schedule = models.JSONField('Schedule', blank=True, default=dict)

    staff_incoming = models.JSONField('Staff incoming orders', blank=True, default=list)
    
    active = models.BooleanField(default=True)

    deleted = models.BooleanField(default=False)    


    class Meta:
        db_table = 'businesses'

    def __str__(self):
        return str(self.id)

# business_type: 1=Supplier, 2=Customer, 3=Private person

# schedule expamples:
# {} - 24/7
# { "without_rest": True (PRIMARY KEY, if it True other keys will be ignored)
#   "0": {"restday": False, "start": 28800, "end": 64800, "breaks" (optional): [{"start": 43200, "end": 46800}]}, - inactive field
#   ...
# } - 24/7
# {
#   "0": {"restday": False, "start": 28800, "end": 64800, "breaks" (optional): [{"start": 43200, "end": 46800}]},
#   "1": {"restday": False, "start": 28800, "end": 64800, "breaks" (optional): [{"start": 43200, "end": 46800}]},
#   ... ,
#   "5": {"restday": True (it is priority key, other keys will be ignored), "start": 28800, "end": 64800, "breaks" (opcional): [{"start": 43200, "end": 46800}]},
#   "6": {"restday": True}
# }


class BusinessTranslation(models.Model):
    business_id = models.IntegerField('Business ID', default=0)
    language = models.CharField('Business interface language (tg)', max_length=5, default="en")
    
    name = models.CharField('Business name', max_length=255, blank=True, default="")
    description = models.CharField('Business description', max_length=255, blank=True, default="")
    address = models.CharField('Address', max_length=255, blank=True, default="")
    
    class Meta:
        db_table = 'business_translation'

    def __str__(self):
        return str(self.id)

