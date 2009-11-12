# -*- coding: utf-8 -*-

# python
from copy import deepcopy

# django
from django.forms import (BooleanField, CharField, DateField, IntegerField,
                          ModelForm,  ValidationError)
from django.contrib.admin.widgets import AdminDateWidget
from django.utils.translation import ugettext_lazy as _

# this app
from models import Attr, Schema, BaseEntity
#from widgets import PlainTextWidget


__all__ = ['SchemaForm', 'BaseDynamicEntityForm']


class SchemaForm(ModelForm):
    class Meta:
        model = Schema

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
    # TODO: allow many attributes of the same name per entity:
    #       - model:
    #         - add "multiple" (boolean field)
    #         - drop constraint unique_together
    #       - abstraction layer:
    #         - always group attribs with same name
    #         - if multiple=True, delete&add instead of update
    #         - tolerate violation of multiple=False by simply ignoring [1:]
    #       - widget: SelectMultiple or MultipleWidget (probably dropdown + native widget?)

    FIELD_CLASSES = {
        'text': CharField,
        'int':  IntegerField,
        'date': DateField,
        'bool': BooleanField,
    }
    FIELD_EXTRA = {
        'date': {'widget': AdminDateWidget},
    }
    def __init__(self, data=None, *args, **kwargs):
        super(BaseDynamicEntityForm, self).__init__(data, *args, **kwargs)

        self._build_dynamic_fields()

    def check_eav_allowed(self):
        """
        Returns True if dynamic attributes can be added to this form.
        If False is returned, only normal fields will be displayed.
        """
        if self.instance:
            return True

    def get_schemata(self):
        return Schema.objects.all()

    def _build_dynamic_fields(self):
        # reset form fields
        self.fields = deepcopy(self.base_fields)

        # do not display dynamic fields if some fields are yet defined
        if not self.check_eav_allowed():
            return

        schemata = self.get_schemata()

        for schema in schemata:
            defaults = {
                'label':     schema.title.capitalize(),
                'required':  schema.required,
                'help_text': schema.help_text,
            }
            defaults.update(self.FIELD_EXTRA.get(schema.datatype, {}))

            MappedField = self.FIELD_CLASSES[schema.datatype]
            self.fields[schema.name] = MappedField(**defaults)

            # fill initial data (if attribute was already defined)
            entity_attr = self.instance.all_attributes.get(schema.name)
            if entity_attr:
                self.initial[schema.name] = entity_attr.value


    def save(self, commit=True):
        """
        Saves this ``form``'s cleaned_data into model instance
        ``self.instance`` and related EAV attributes.

        Please note that the changes to ``instance`` and EAV attributes are
        *always* saved to the database, i.e. `commit` value is ignored.

        Returns ``instance``.
        """

        if self.errors:
            raise ValueError("The %s could not be saved because the data didn't"
                            " validate." % self.instance._meta.object_name)

        # save entity instance
        obj = super(BaseDynamicEntityForm, self).save(commit=True)    # Note: commit forced
        obj_ct = dict(content_type=obj.attrs.content_type, object_id=obj.pk)

        # save Attr instances
        # XXX we ignore commit=False because it may mean unchanged static attrs
        schemata = self.get_schemata()
        for schema in schemata:
            #attr, _ = Attr.objects.get_or_create(schema=schema)#, content_object=obj)
            attr, _ = Attr.objects.get_or_create(schema=schema, **obj_ct)
            f = attr._meta.get_field('value_%s' % schema.datatype)
            f.save_form_data(attr, self.cleaned_data.get(schema.name))
            attr.save()

        return obj
    save.alters_data = True

    def save_m2m(*a, **kw):
        # stub for admin    TODO: check if we don't need to super() if entity indeed has m2m
        pass
