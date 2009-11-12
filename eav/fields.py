# -*- coding: utf-8 -*-

# django
from django import forms

# this app
from widgets import RangeWidget


class RangeField(forms.MultiValueField):
    widget = RangeWidget

    def __init__(self, *args, **kwargs):
        fields = (
            forms.IntegerField(),
            forms.IntegerField(),
        )
        super(RangeField, self).__init__(fields, *args, **kwargs)

    def compress(self, data_list):
        if data_list:
            return slice(*data_list)
        return None
