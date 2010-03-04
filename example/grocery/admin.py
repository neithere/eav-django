# django
from django.contrib import admin

# 3rd-party
from eav.admin import BaseEntityAdmin, BaseSchemaAdmin

# this app
from models import Fruit, Schema, Choice
from forms import FruitForm


class FruitAdmin(BaseEntityAdmin):
    form = FruitForm


admin.site.register(Fruit, FruitAdmin)
admin.site.register(Schema, BaseSchemaAdmin)
admin.site.register(Choice)

