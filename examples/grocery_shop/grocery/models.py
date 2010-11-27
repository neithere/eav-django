# django
from django.db import models

# eav
from eav.models import BaseChoice, BaseEntity, BaseSchema, BaseAttribute


class Fruit(BaseEntity):
    title = models.CharField(max_length=50)

    @classmethod
    def get_schemata_for_model(self):
        return Schema.objects.all()

    def __unicode__(self):
        return self.title


class Schema(BaseSchema):
    pass


class Choice(BaseChoice):
    schema = models.ForeignKey(Schema, related_name='choices')


class Attribute(BaseAttribute):
    schema = models.ForeignKey(Schema, related_name='attrs')
    choice = models.ForeignKey(Choice, blank=True, null=True)


