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

"""

##
## basic EAV
##

>>> colour = Schema.objects.create(title='Colour', datatype=Schema.TYPE_TEXT)
>>> colour
<Schema: Colour (text)>
>>> colour.name              #  <-- automatically generated from title
'colour'
>>> taste = Schema.objects.create(title='Taste', datatype=Schema.TYPE_TEXT)
>>> age = Schema.objects.create(title='Age', datatype=Schema.TYPE_FLOAT)
>>> can_haz = Schema.objects.create(title='I can haz it', datatype=Schema.TYPE_BOOLEAN)
>>> can_haz.name
'i_can_haz_it'
>>> e = Entity.objects.create(title='Apple', colour='green')
>>> e.title
'Apple'
>>> e.colour
'green'
>>> e.attrs.all()
[<Attr: Apple: Colour "green">]
>>> e.taste = 'sweet'
>>> e.attrs.all()
[<Attr: Apple: Colour "green">]
>>> e.colour = 'yellow'
>>> e.save()
>>> e.attrs.all()
[<Attr: Apple: Colour "yellow">, <Attr: Apple: Taste "sweet">]
>>> [x for x in e]
[<Attr: Apple: Colour "yellow">, <Attr: Apple: Taste "sweet">]
>>> Entity.objects.filter(title='Apple')
[<Entity: Apple>]
>>> Entity.objects.filter(colour='yellow')
[<Entity: Apple>]
>>> Entity.objects.filter(colour='yellow', title='Apple')
[<Entity: Apple>]

##
## many-to-one
##

>>> size = Schema.objects.create(name='size', title='Size', datatype=Schema.TYPE_MANY)
>>> small  = size.choices.create(title='S')
>>> medium = size.choices.create(title='M')
>>> large  = size.choices.create(title='L')
>>> small
<Choice: S>
>>> large.schema
<Schema: Size (multiple choices)>
>>> e = Entity(title='T-shirt')
>>> e.size = small
>>> e.save()
>>> e2 = Entity.objects.get(pk=e.pk)
>>> e2.size
[<Choice: S>]
>>> e2.size = [medium, large]
>>> e2.save()
>>> e3 = Entity.objects.get(pk=e.pk)
>>> e3.size
[<Choice: M>, <Choice: L>]
>>> Attr.objects.all()
[<Attr: Apple: Colour "yellow">, <Attr: Apple: Taste "sweet">, \
<Attr: T-shirt: Size "M">, <Attr: T-shirt: Size "L">]
>>> e2.size = ['wrong choice']
>>> e2.save()
Traceback (most recent call last):
    ...
ValueError: Cannot assign "'wrong choice'": "Attr.choice" must be a "Choice" instance.
>>> e2.size = [small, large]
>>> e2.save()
>>> e3 = Entity.objects.get(pk=e.pk)
>>> e3.size
[<Choice: S>, <Choice: L>]
>>> Attr.objects.all().order_by('schema', 'choice__id')
[<Attr: Apple: Colour "yellow">, <Attr: T-shirt: Size "S">,\
 <Attr: T-shirt: Size "L">, <Attr: Apple: Taste "sweet">]

##
## combined
##

>>> Entity.objects.create(title='Orange', colour='orange', taste='sweet', size=medium)
<Entity: Orange>
>>> Entity.objects.create(title='Tangerine', colour='orange', taste='sweet', size=small)
<Entity: Tangerine>
>>> Entity.objects.create(title='Old Dog', colour='orange', taste='bitter', size=large)
<Entity: Old Dog>

>>> Entity.objects.filter(taste='sweet')
[<Entity: Apple>, <Entity: Orange>, <Entity: Tangerine>]
>>> Entity.objects.filter(colour='orange', size__in=[small, large])
[<Entity: Tangerine>, <Entity: Old Dog>]

#
# exclude() fetches objects that either have given attribute(s) with other values
# or don't have any attributes for this schema at all:
#
>>> Entity.objects.exclude(size=small)
[<Entity: Apple>, <Entity: Orange>, <Entity: Old Dog>]
>>> Entity.objects.exclude(taste='sweet')
[<Entity: T-shirt>, <Entity: Old Dog>]
>>> Entity.objects.filter(size=large) & Entity.objects.exclude(colour='orange')
[<Entity: T-shirt>]
>>> Entity.objects.filter(size=large) & Entity.objects.filter(colour='orange')
[<Entity: Old Dog>]

##
## facets
##

# make some schemata available for filtering entities by them
>>> Schema.objects.filter(name__in=['colour', 'size', 'taste']).update(filtered=True)
3
>>> fs = FacetSet({})
>>> fs.filterable_schemata
[<Schema: Colour (text)>, <Schema: Size (multiple choices)>, <Schema: Taste (text)>]
>>> fs.filterable_names
['price', 'colour', 'size', 'taste']
>>> fs.facets
[<TextFacet: Item price>, <TextFacet: Colour>, <ManyToManyFacet: Size>, <TextFacet: Taste>]
>>> [x for x in fs]
[<Entity: Apple>, <Entity: T-shirt>, <Entity: Orange>, <Entity: Tangerine>, <Entity: Old Dog>]
>>> [x for x in FacetSet({'colour': 'yellow'})]
[<Entity: Apple>]
>>> [x for x in FacetSet({'colour': 'orange'})]
[<Entity: Orange>, <Entity: Tangerine>, <Entity: Old Dog>]
>>> [x for x in FacetSet({'colour': 'orange', 'taste': 'sweet'})]
[<Entity: Orange>, <Entity: Tangerine>]
>>> [x for x in FacetSet({'size': [large.pk]})]
[<Entity: T-shirt>, <Entity: Old Dog>]
"""

# TODO: if schema changes type, drop all attribs?

# django
from django.contrib.contenttypes import generic
from django.db import models

# this app
from facets import BaseFacetSet
from models import BaseAttribute, BaseChoice, BaseEntity, BaseSchema


class Schema(BaseSchema):
    pass


class Choice(BaseChoice):
    schema = models.ForeignKey(Schema, related_name='choices')


class Attr(BaseAttribute):
    #entity = models.ForeignKey(Entity, related_name='attrs')
    schema = models.ForeignKey(Schema, related_name='attrs')
    choice = models.ForeignKey(Choice, related_name='attrs', null=True)


class Entity(BaseEntity):
    title = models.CharField(max_length=100)
    price = models.IntegerField(blank=True, null=True, verbose_name='Item price')
    attrs = generic.GenericRelation(Attr, object_id_field='entity_id',
                                    content_type_field='entity_type')

    @classmethod
    def get_schemata_for_model(cls):
        return Schema.objects.all()

    def __unicode__(self):
        return self.title


class FacetSet(BaseFacetSet):
    filterable_fields = ['price']
    sortable_fields = ['price']

    def get_queryset(self, **kwargs):
        return Entity.objects.filter(**kwargs)     # can be pre-filtered using custom FacetSet.__init__
