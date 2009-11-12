# -*- coding: utf-8 -*-

from django import forms
from django.forms.util import flatatt
from django.utils.encoding import force_unicode
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe


class RangeWidget(forms.MultiWidget):
    def __init__(self, attrs=None):
        widgets = (forms.TextInput(attrs=attrs), forms.TextInput(attrs=attrs))
        attrs = attrs or {}
        attrs.update({'class': 'range'})
        super(RangeWidget, self).__init__(widgets, attrs)

    def decompress(self, value):
        if value:
            return [value.start, value.stop]
        return [None, None]

    def format_output(self, rendered_widgets):
        return u'-'.join(rendered_widgets)
