from django.db import models

class LanguageInterface(models.Model):
    
    label = models.CharField('Language label', max_length=5)
    name_english = models.CharField('Language name (English)', max_length=255, default="")
    name_native = models.CharField('Language name (Native)', max_length=255, default="")
    interface = models.JSONField('Interface data JSON', blank=True,  default=dict)
    available = models.BooleanField(default=False)

    class Meta:
        db_table = 'language_interfaces'

    def __str__(self):
        return self.label
