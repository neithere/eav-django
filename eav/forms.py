# -*- coding: utf-8 -*-

# python
from copy import deepcopy

# django
from django.forms import (BooleanField, CharField, DateField, IntegerField,
                          ModelForm, MultipleChoiceField, ValidationError)
from django.contrib.admin.widgets import AdminDateWidget, FilteredSelectMultiple
from django.utils.translation import ugettext_lazy as _

# this app
from models import Attr, BaseEntity
#from widgets import PlainTextWidget


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
        'int':  IntegerField,
        'date': DateField,
        'bool': BooleanField,
        'm2o': MultipleChoiceField,
    }
    FIELD_EXTRA = {
        'date': {'widget': AdminDateWidget},
        #'m2o': {'widget': FilteredSelectMultiple('xxx verbose name xxx', is_stacked=False)},
    }
    def __init__(self, data=None, *args, **kwargs):
        super(BaseDynamicEntityForm, self).__init__(data, *args, **kwargs)

        self._build_dynamic_fields()

    def check_eav_allowed(self):
        """
        Returns True if dynamic attributes can be added to this form.
        If False is returned, only normal fields will be displayed.
        """
        return bool(self.instance and self.instance.check_eav_allowed())

    def _build_dynamic_fields(self):
        # reset form fields
        self.fields = deepcopy(self.base_fields)

        # do not display dynamic fields if some fields are yet defined
        if not self.check_eav_allowed():
            return

        names = self.instance.schema_names

        for name in names:
            schema = self.instance.get_schema(name)

            if schema.managed:
                continue

            defaults = {
                'label':     schema.title.capitalize(),
                'required':  schema.required,
                'help_text': schema.help_text,
            }

            # FIXME fake datatype -- temporary!
            datatype = schema.datatype
            if schema.m2o:
                datatype = 'm2o'
                defaults.update({'choices': schema.get_choices(self.instance)})

            defaults.update(self.FIELD_EXTRA.get(datatype, {}))

            MappedField = self.FIELD_CLASSES[datatype]
            self.fields[schema.name] = MappedField(**defaults)

            # fill initial data (if attribute was already defined)
            value = getattr(self.instance, schema.name)
            if value:
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
        for name in instance.schema_names:
            value = self.cleaned_data.get(name)
            setattr(instance, name, value)

        # save entity and its attributes
        if commit:
            instance.save()

        return instance
    save.alters_data = True

    def save_m2m(*a, **kw):
        # stub for admin    TODO: check if we don't need to super() if entity indeed has m2m
        pass
