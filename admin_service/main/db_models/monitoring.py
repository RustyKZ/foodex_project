
from django.db import models

class AppError(models.Model):
    date = models.IntegerField('Error date (Unixtime)', default=0)
    service = models.CharField('Service Name', max_length=255, blank=True, default="")
    function = models.CharField('Function Name', max_length=255, blank=True, default="")
    error_short = models.CharField('Error short description', max_length=255, blank=True, default="")
    error_text = models.TextField("Error description", default="", blank=True)
    context = models.JSONField('Error context', blank=True, default=dict)

    class Meta:
        db_table = 'app_error'

    def __str__(self):
        return f"[{self.service}] {self.function}: {self.error_short}"
    

class UserAction(models.Model):
    user_id = models.IntegerField('User ID', default=0)
    date = models.IntegerField('Action date (Unixtime)', default=0)
    action_type = models.CharField('Action type', max_length=255, blank=True, default="")
    entity_type = models.CharField('Entity type', max_length=255, blank=True, default="")
    entity_id = models.BigIntegerField('Entity ID', default=0)
    ip_address = models.CharField('IP address', max_length=255, blank=True, default="")
    extra_data = models.JSONField('Extra data', blank=True, default=dict)

    class Meta:
        db_table = 'user_action'

    def __str__(self):
        return str(self.id)
    

class SystemAction(models.Model):
    date = models.IntegerField('Action date (Unixtime)', default=0)
    service = models.CharField('Service Name', max_length=255, blank=True, default="")
    event = models.CharField('Event name', max_length=255, blank=True, default="")
    status = models.CharField('Action status', max_length=50, blank=True, default="")
    description = models.TextField("Action description", default="", blank=True)
    meta_json = models.JSONField('Action data', blank=True, default=dict)
    duration = models.FloatField('Action duration (seconds)', default=0)

    class Meta:
        db_table = 'system_action'

    def __str__(self):
        return f"[{self.service}] {self.event}: {self.status}"