from django.db import models

class Message(models.Model):
    
    order_id = models.IntegerField('Order ID', default=0)
    date = models.IntegerField('Create date (Unixtime)', default=0)
    sender_business = models.IntegerField('Sender bisiness ID', default=0)
    sender_user = models.IntegerField('Sender user ID', default=0)
    receiver_business = models.IntegerField('Receiver bisiness ID', default=0)
    read_users = models.JSONField('Readed users IDs', blank=True, default=list)
    text = models.TextField("Text message", default="", blank=True)
    names_dict_users = models.JSONField('Users dict', blank=True, default=dict)
    names_dict_businesses = models.JSONField('Businesses dict', blank=True, default=dict)

    deleted = models.BooleanField(default=False)    

    class Meta:
        db_table = 'messages'

    def __str__(self):
        return str(self.id)
    


class Notification(models.Model):
        
    date = models.IntegerField('Create date (Unixtime)', default=0)
    receiver_user = models.IntegerField('Receiver user ID', default=0)
    receiver_business = models.IntegerField('Receiver bisiness ID (optional)', null=True)
    type = models.CharField('Type of notification', max_length=50, blank=True, default="")
    is_sample = models.BooleanField(default=False)
    sample_code = models.CharField('Sample code', max_length=255, null=True, blank=True)
    sample_text = models.TextField("Optional text for sample", null=True, blank=True)
    sample_data = models.JSONField('Sample data', blank=True, default=dict)
    text = models.TextField("Text message english (not sampled)", null=True, blank=True)
    translations = models.JSONField('Dict of text', blank=True, default=dict)
    read_date = models.IntegerField('Read date (Unixtime)', default=0)

    deleted = models.BooleanField(default=False)

    class Meta:
        db_table = 'notifications'
    
    def __str__(self):
        return str(self.id)
    