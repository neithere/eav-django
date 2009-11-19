# -*- coding: utf-8 -*-

# python
from itertools import chain

# django
from django.conf import settings
from django.db import models
from django import forms
from django.utils.datastructures import SortedDict
from django.utils.translation import ugettext as _

# 3rd-party
from view_shortcuts.decorators import cached_property

# this app
from models import Attr, Item
from fields import RangeField


FILTERABLE_FIELDS = getattr(settings, 'CATALOGUE_FILTERABLE_FIELDS', ('price',))
SORTABLE_FIELDS   = getattr(settings, 'CATALOGUE_SORTABLE_FIELDS',   ('price',))


class FakeSchema(object):
    """
    A schema-like wrapper for real model fields. Used to maintain unified
    internal API in Facet subclasses.
    """
    def __init__(self, field):
        self.field = field
        self.title = unicode(self.field.verbose_name)
        self.name  = field.name


class Facet(object):
    def __init__(self, rubric, schema):
        self.rubric = rubric
        self.schema = schema

    extra = {}

    @property
    def field_class(self):
        raise NotImplementedError('Facet subclasses must specify form field class')

    @property
    def widget(self):
        return self.field_class.widget

    @property
    def field(self):
        "Returns appropriate form field."
        defaults = dict(required=False, label=self.schema.title, widget=self.widget)
        defaults.update(self.extra)
        return self.field_class(**defaults)

    def get_lookups(self, value):
        "Returns dictionary of lookups for facet-specific query."
        return {self.schema.name: value} if value else {}


class TextFacet(Facet):
    field_class = forms.ChoiceField

    @property
    def _choices(self):
        if isinstance(self.schema, FakeSchema):
            attrs = Item.objects.filter(rubric=self.rubric)
            field_name = self.schema.field.name
        else:
            attrs = self.schema.attrs.filter(item__rubric=self.rubric)
            field_name = 'value_%s' % self.schema.datatype    # XXX implementation details exposed
        choices = set(attrs.values_list(field_name, flat=True))
        return [(x,x) for x in choices]

    @property
    def extra(self):
        d = {'choices': self._choices}
        if len(self._choices) < 5:
            d['widget'] = forms.RadioSelect
        return d


class IntegerFacet(Facet):
    field_class = forms.IntegerField


class RangeFacet(Facet):
    field_class = RangeField

    def get_lookups(self, value):
        if not value:
            return {}
        if not value.stop:
            return {'%s__gt' % self.schema.name: value.start}
        return {'%s__range' % self.schema.name: (value.start or 0, value.stop)}


class DateFacet(Facet):
    field_class = forms.DateField


class BooleanFacet(Facet):
    field_class = forms.NullBooleanField

    # XXX this is funny but using RadioSelect for booleans is non-trivial
    #widget = RadioSelect

    def get_lookups(self, value):
        return {self.schema.name: value} if value is not None else {}


FACET_FOR_DATATYPE_DEFAULTS = {
    'text': TextFacet,
    'int':  RangeFacet, #IntegerFacet,
    'date': DateFacet,
    'bool': BooleanFacet,
}

FACET_FOR_FIELD_DEFAULTS = {
    models.FloatField: RangeFacet,
}


class RubricFacetSet(object):
    def __init__(self, rubric, data):
        self.rubric = rubric
        self.data = data

    def __iter__(self):
        return iter(self.object_list)

    @cached_property
    def filterable_schemata(self):
        return self.rubric.schemata.filter(filtered=True)

    @cached_property
    def sortable_schemata(self):
        return self.rubric.schemata.filter(sortable=True)

    @cached_property
    def _schemata_by_name(self):
        return dict((s.name, s) for s in chain(self.filterable_schemata, self.sortable_schemata))

    def get_schema(self, name):
        return self._schemata_by_name[name]

    @cached_property
    def filterable_names(self):
        return [str(s.name) for s in self.filterable_schemata]

    @cached_property
    def sortable_names(self):
        return [str(s.name) for s in self.sortable_schemata] + SORTABLE_FIELDS

    def _get_facets(self):
        for name in self.filterable_names:
            schema = self.get_schema(name)
            FacetClass = FACET_FOR_DATATYPE_DEFAULTS[schema.datatype]
            yield FacetClass(self.rubric, schema)
        for name in FILTERABLE_FIELDS:
            field = Item._meta.get_field(name)
            FacetClass = FACET_FOR_FIELD_DEFAULTS.get(type(field), TextFacet)
            schema = FakeSchema(field=field)
            yield FacetClass(self.rubric, schema)

    @cached_property
    def facets(self):
        return list(self._get_facets())

    @cached_property
    def form(self):
        if not hasattr(self, '_form'):
            fields = SortedDict([(facet.schema.name, facet.field) for facet in self.facets])
            FormClass = type('%sForm' % self.__class__.__name__, (forms.Form,), fields)        # XXX maybe add rubric slug?
            self._form = FormClass(self.data)
        return self._form

    @cached_property
    def object_list(self):
        lookups = {'rubric': self.rubric}
        for facet in self.facets:
            try:
                value = self.form.fields[facet.schema.name].clean(self.form[facet.schema.name].data)
            except forms.ValidationError:
                continue
            lookups.update(facet.get_lookups(value))
        qs = Item.objects.filter(**dict((str(k),v) for k,v in lookups.items()))
        order_by_name = self.data.get('order_by')
        if order_by_name:
            qs = self.sort_by_attribute(qs, order_by_name)
        return qs


    def sort_by_attribute(self, qs, name):
        """
        A wrapper around standard order_by() method. Allows to sort by both normal
        fields and EAV attributes without thinking about implementation details.
        Usage::

            qs = sort_by_attributes(qs, 'price', 'colour')

        ...where `price` is a FloatField, and `colour` is the name of an EAV attribute
        represented by Schema and Attr models.
        """
        fields   = Item._meta.get_all_field_names()
        schemata = self.sortable_names
        direction = '-' if self.data.get('order_desc') else ''
        if name in fields:
            return qs.order_by('%s%s' % (direction, name))
        elif name in schemata:
            schema = self.get_schema(name)
            value_lookup = 'attrs__value_%s' % schema.datatype
            order_lookup = '%s%s' % (direction, value_lookup)
            return qs.filter(attrs__schema__name=name).order_by(order_lookup)
        else:
            raise NameError('Cannot order items by attributes: unknown '
                            'attribute "%s". Available fields: %s. '
                            'Available schemata: %s.' % (name,
                            ', '.join(fields), ', '.join(schemata)))
