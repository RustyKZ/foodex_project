
from django.db import models

class BotMessages(models.Model):
    date = models.DateTimeField('Creating date', auto_now=True)
    sending_date = models.IntegerField('Sending date (UNIX)', default=0)
    theme = models.CharField('Theme (for admin)', max_length=255, blank=True, default="")
    userlist = models.JSONField('List of users (TG IDs)', blank=True, default=list)
    message_data = models.JSONField('Message data JSON', blank=True,  default=dict)
    confirmed = models.BooleanField(default=False)
    sended = models.BooleanField(default=False)
    not_actual = models.BooleanField(default=False)

    class Meta:
        db_table = 'botmessages'

    def __str__(self):
        return self.theme
    
# message_data dict type:
# "image_path": string
# "message_text": string
# "button_name": string
# "button_link": string
# "html": boolean

    
class BotCommands(models.Model):
    command = models.CharField('Command', max_length=255, unique=True)
    description = models.CharField('Description (for admin)', max_length=255, blank=True, default="")    
    response_data = models.JSONField('Response data JSON', blank=True,  default=dict)

    class Meta:
        db_table = 'botcommands'

    def __str__(self):
        return self.command

# response_data dict type:
# "image_path": string
# "message_text": string
# "button_name": string
# "button_link": string
# "script_name": string
# "html": boolean
