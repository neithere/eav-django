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
from itertools import chain

# django
from django.db import models
from django import forms
from django.utils.datastructures import SortedDict
from django.utils.translation import ugettext as _

# 3rd-party
from view_shortcuts.decorators import cached_property

# this app
from fields import RangeField


class Facet(object):
    def __init__(self, facet_set, schema=None, field=None, lookup_prefix=''):
        self.facet_set = facet_set
        assert schema or field, 'Facet must be created with schema or field'
        assert not (schema and field), 'Facet cannot be created with both schema and field'
        self.schema = schema
        self.field = field
        self.lookup_prefix = lookup_prefix

    def __repr__(self):
        return u'<%s: %s>' % (self.__class__.__name__, unicode(self))

    def __unicode__(self):
        return unicode(self.schema.title if self.schema else self.field.verbose_name)

    extra = {}

    @property
    def field_class(self):
        raise NotImplementedError('Facet subclasses must specify form field class')

    @property
    def widget(self):
        return self.field_class.widget

    @property
    def form_field(self):
        "Returns appropriate form field."
        defaults = dict(required=False, label=unicode(self), widget=self.widget)
        defaults.update(self.extra)
        return self.field_class(**defaults)

    @property
    def attr_name(self):
        "Returns attribute name for this facet"
        return self.schema.name if self.schema else self.field.name

    @property
    def lookup_name(self):
        return '%s%s' % (self.lookup_prefix, self.attr_name)

    def get_lookups(self, value):
        "Returns dictionary of lookups for facet-specific query."
        return {self.lookup_name: value} if value else {}


class TextFacet(Facet):
    field_class = forms.ChoiceField

    @property
    def _choices(self):
        if self.schema:
            # FIXME implementation details exposed ###########
            attrs = self.schema.attrs.all()    # FIXME in shop don't need *all* attrs, just those in rubric
            field_name = 'value_%s' % self.schema.datatype
        else:
            attrs = self.facet_set.get_queryset()
            field_name = self.attr_name
        choices = set(attrs.values_list(field_name, flat=True).distinct())
        return [('', _('any'))] + [(x,x) for x in choices]

    @property
    def extra(self):
        d = {'choices': self._choices}
        if len(self._choices) < 5:
            d['widget'] = forms.RadioSelect
        return d


class ManyToManyFacet(Facet):
    field_class = forms.models.ModelMultipleChoiceField

    def _get_queryset(self):
        assert self.schema.datatype == self.schema.TYPE_MANY
        # TODO: intersection with entity and, maybe, FacetSet?
        return self.schema.get_choices()

    @property
    def extra(self):
        return {
            'queryset': self._get_queryset(),
            'widget': forms.CheckboxSelectMultiple,
        }

    def get_lookups(self, value):
        "Returns dictionary of lookups for facet-specific query."
        return {'%s__in' % self.lookup_name: value} if value else {}


class IntegerFacet(Facet):
    field_class = forms.IntegerField


class RangeFacet(Facet):
    field_class = RangeField

    def get_lookups(self, value):
        if not value:
            return {}
        # XXX what about __lt ?
        if not value.stop:
            return {'%s__gt' % self.lookup_name: value.start}
        return {'%s__range' % self.lookup_name: (value.start or 0, value.stop)}


class DateFacet(Facet):
    field_class = forms.DateField


class BooleanFacet(Facet):
    field_class = forms.NullBooleanField

    # XXX this is funny but using RadioSelect for booleans is non-trivial
    #widget = RadioSelect

    def get_lookups(self, value):
        return {self.lookup_name: value} if value is not None else {}


FACET_FOR_DATATYPE_DEFAULTS = {
    'text':  TextFacet,
    'float': RangeFacet, #IntegerFacet,
    'date':  DateFacet,
    'bool':  BooleanFacet,
    'many':  ManyToManyFacet,
}

FACET_FOR_FIELD_DEFAULTS = {
    models.FloatField: RangeFacet,
}


class BaseFacetSet(object):
    filterable_fields = []
    sortable_fields = []

    def __getitem__(self, k):
        return self.object_list[k]

    def __init__(self, data):
        self.data = data

    def __iter__(self):
        return iter(self.object_list)

    def __len__(self):
        if self.object_list:
            return self.object_list.count()
        return 0

    def get_queryset(self, **kwargs):
        raise NotImplementedError('BaseFacetSet subclasses must define get_queryset()')

    def get_schemata(self):
        return self.get_queryset().model.get_schemata_for_model()

    @cached_property
    def filterable_schemata(self):
        return self.get_schemata().filter(filtered=True)

    @cached_property
    def sortable_schemata(self):
        return self.get_schemata().filter(sortable=True)

    @cached_property
    def _schemata_by_name(self):
        return dict((s.name, s) for s in chain(self.filterable_schemata, self.sortable_schemata))

    def get_schema(self, name):
        return self._schemata_by_name[name]

    @cached_property
    def filterable_names(self):
        return self.filterable_fields + [str(s.name) for s in self.filterable_schemata]

    @cached_property
    def sortable_names(self):
        return self.sortable_fields + [str(s.name) for s in self.sortable_schemata]

    def _get_facets(self):
        # TODO: refactor this

        for name in self.filterable_names:
            try:
                schema, lookup_prefix = self.get_schema_and_lookup(name)
            except KeyError:    # XXX  are we sure it will raise KeyError? depends on implementation!
                field, lookup_prefix = self.get_field_and_lookup(name)
                FacetClass = FACET_FOR_FIELD_DEFAULTS.get(type(field), TextFacet)
                yield FacetClass(self, field=field, lookup_prefix=lookup_prefix)
            else:
                FacetClass = FACET_FOR_DATATYPE_DEFAULTS[schema.datatype]
                yield FacetClass(self, schema=schema, lookup_prefix=lookup_prefix)

    @cached_property
    def facets(self):
        return list(self._get_facets())

    @cached_property
    def form(self):
        if not hasattr(self, '_form'):
            fields = SortedDict([(facet.attr_name, facet.form_field) for facet in self.facets])
            FormClass = type('%sForm' % self.__class__.__name__, (forms.Form,), fields)        # XXX maybe add rubric slug?
            self._form = FormClass(self.data)
        return self._form

    def get_field_and_lookup(self, name):
        """
        Returns field instance and lookup prefix for given attribute name.
        Can be overloaded in subclasses to provide filtering across multiple models.
        """
        name = self.get_queryset().model._meta.get_field(name)
        lookup_prefix = ''
        return name, lookup_prefix

    def get_schema_and_lookup(self, name):
        schema = self.get_schema(name)
        lookup_prefix = ''
        return schema, lookup_prefix

    def get_lookups(self):
        lookups = {}
        for facet in self.facets:
            data  = self.form[facet.attr_name].data
            field = self.form.fields[facet.attr_name]
            value = field.clean(data)
            lookups.update(facet.get_lookups(value))
        return lookups

    @cached_property
    def object_list(self):
        try:
            lookups = self.get_lookups()
        except forms.ValidationError:
            return []
        lookups = dict((str(k),v) for k,v in lookups.items())

        # assume to use the EntityManager's smart filter()
        qs = self.get_queryset(**lookups).distinct()

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
        fields   = self.get_queryset().model._meta.get_all_field_names()
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
