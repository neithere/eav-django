# -*- coding: utf-8 -*-
#
#    EAV-Django is a reusable Django application which implements EAV data model
#    Copyright © 2009—2010  Andrey Mikhaylenko
#
#    This file is part of EAV-Django.
#
#    EAV-Django is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as published
#    by the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    EAV-Django is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public License
#    along with EAV-Django.  If not, see <http://gnu.org/licenses/>.

# python
from copy import deepcopy

# django
from django.forms import (BooleanField, CharField, CheckboxSelectMultiple,
                          DateField, FloatField, ModelForm, ModelMultipleChoiceField,    #MultipleChoiceField,
                          ValidationError)
from django.contrib.admin.widgets import AdminDateWidget, FilteredSelectMultiple    #, RelatedFieldWidgetWrapper
from django.utils.translation import ugettext_lazy as _


__all__ = ['BaseSchemaForm', 'BaseDynamicEntityForm']


class BaseSchemaForm(ModelForm):

    def clean_name(self):
        "Avoid name clashes between static and dynamic attributes."
        name = self.cleaned_data['name']
        reserved_names = self._meta.model._meta.get_all_field_names()
        if name not in reserved_names:
            return name
        raise ValidationError(_('Attribute name must not clash with reserved names'
                                ' ("%s")') % '", "'.join(reserved_names))


class BaseDynamicEntityForm(ModelForm):
    """
    ModelForm for entity with support for EAV attributes. Form fields are created
    on the fly depending on Schema defined for given entity instance. If no schema
    is defined (i.e. the entity instance has not been saved yet), only static
    fields are used. However, on form validation the schema will be retrieved
    and EAV fields dynamically added to the form, so when the validation is
    actually done, all EAV fields are present in it (unless Rubric is not defined).
    """

    FIELD_CLASSES = {
        'text': CharField,
        'float': FloatField,
        'date': DateField,
        'bool': BooleanField,
        'many': ModelMultipleChoiceField,    #RelatedFieldWidgetWrapper(MultipleChoiceField),
    }
    FIELD_EXTRA = {
        'date': {'widget': AdminDateWidget},
        'many': lambda schema: {
            'widget': CheckboxSelectMultiple
                      if len(schema.get_choices()) <= 5 else
                      FilteredSelectMultiple(schema.title, is_stacked=False)
        },
    }
    def __init__(self, data=None, *args, **kwargs):
        super(BaseDynamicEntityForm, self).__init__(data, *args, **kwargs)
        self._build_dynamic_fields()

    def check_eav_allowed(self):
        """
        Returns True if dynamic attributes can be added to this form.
        If False is returned, only normal fields will be displayed.
        """
        return bool(self.instance)# and self.instance.check_eav_allowed()) # XXX would break form where stuff is _being_ defined

    def _build_dynamic_fields(self):
        # reset form fields
        self.fields = deepcopy(self.base_fields)

        # do not display dynamic fields if some fields are yet defined
        if not self.check_eav_allowed():
            return

        for schema in self.instance.get_schemata():

            defaults = {
                'label':     schema.title.capitalize(),
                'required':  schema.required,
                'help_text': schema.help_text,
            }

            datatype = schema.datatype
            if datatype == schema.TYPE_MANY:
                choices = getattr(self.instance, schema.name)
                defaults.update({'queryset': schema.get_choices(),
                                 'initial': [x.pk for x in choices]})

            extra = self.FIELD_EXTRA.get(datatype, {})
            if hasattr(extra, '__call__'):
                extra = extra(schema)
            defaults.update(extra)

            MappedField = self.FIELD_CLASSES[datatype]
            self.fields[schema.name] = MappedField(**defaults)

            # fill initial data (if attribute was already defined)
            value = getattr(self.instance, schema.name)
            if value and not datatype == schema.TYPE_MANY:    # m2m is already done above
                self.initial[schema.name] = value

    def save(self, commit=True):
        """
        Saves this ``form``'s cleaned_data into model instance ``self.instance``
        and related EAV attributes.

        Returns ``instance``.
        """

        if self.errors:
            raise ValueError("The %s could not be saved because the data didn't"
                             " validate." % self.instance._meta.object_name)

        # create entity instance, don't save yet
        instance = super(BaseDynamicEntityForm, self).save(commit=False)

        # assign attributes
        for name in instance.get_schema_names():
            value = self.cleaned_data.get(name)
            setattr(instance, name, value)

        # save entity and its attributes
        if commit:
            instance.save()

        return instance
    save.alters_data = True

    def save_m2m(self, *a, **kw):
        # stub for admin    TODO: check if we don't need to super() if entity indeed has m2m
        pass
