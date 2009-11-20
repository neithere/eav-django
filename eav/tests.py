# -*- coding: utf-8 -*-

"""

##
## basic EAV
##

>>> colour = Schema.objects.create(title='Colour', datatype=Schema.TYPE_TEXT)
>>> colour
<Schema: Colour (text) >
>>> colour.name              #  <-- automatically generated from title
'colour'
>>> taste = Schema.objects.create(title='Taste', datatype=Schema.TYPE_TEXT)
>>> age = Schema.objects.create(title='Age', datatype=Schema.TYPE_INTEGER)
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
>>> for choice in 'S', 'M', 'L':
...     size.choices.create(title=choice)
<Choice: Size "S">
<Choice: Size "M">
<Choice: Size "L">
>>> e = Entity(title='T-shirt')
>>> e.size = u's'
>>> e.save()
>>> e2 = Entity.objects.get(pk=e.pk)
>>> e2.size
[u's']
>>> e2.size = [u'm', u'l']
>>> e2.save()
>>> e3 = Entity.objects.get(pk=e.pk)
>>> e3.size
[u'm', u'l']
>>> Attr.objects.all()
[<Attr: Apple: Colour "yellow">, <Attr: Apple: Taste "sweet">, \
<Attr: T-shirt: Size "Size "M"">, <Attr: T-shirt: Size "Size "L"">]
>>> e2.size = ['wrong choice']
>>> e2.save()
Traceback (most recent call last):
    ...
ValueError: Cannot save eav.tests.Entity.size: expected subset of [u's', u'm', u'l'], got "['wrong choice']"
>>> e2.size = [u's', u'l']
>>> e2.save()
>>> e3 = Entity.objects.get(pk=e.pk)
>>> e3.size
[u's', u'l']
>>> Attr.objects.all()
[<Attr: Apple: Colour "yellow">, <Attr: Apple: Taste "sweet">, \
<Attr: T-shirt: Size "Size "S"">, <Attr: T-shirt: Size "Size "L"">]

##
## combined
##

>>> Entity.objects.create(title='Orange', colour='orange', taste='sweet', size='m')
<Entity: Orange>
>>> Entity.objects.create(title='Tangerine', colour='orange', taste='sweet', size='s')
<Entity: Tangerine>
>>> Entity.objects.create(title='Old Dog', colour='orange', taste='bitter', size='l')
<Entity: Old Dog>

>>> Entity.objects.filter(taste='sweet')
[<Entity: Apple>, <Entity: Orange>, <Entity: Tangerine>]
>>> Entity.objects.filter(colour='orange', size__in=['s','l'])
[<Entity: Tangerine>, <Entity: Old Dog>]

#
# exclude() fetches objects that either have given attribute(s) with other values
# or don't have any attributes for this schema at all:
#
>>> Entity.objects.exclude(size='s')
[<Entity: Apple>, <Entity: Orange>, <Entity: Old Dog>]
>>> Entity.objects.exclude(taste='sweet')
[<Entity: T-shirt>, <Entity: Old Dog>]
>>> Entity.objects.filter(size='l') & Entity.objects.exclude(colour='orange')
[<Entity: T-shirt>]
>>> Entity.objects.filter(size='l') & Entity.objects.filter(colour='orange')
[<Entity: Old Dog>]
"""
# TODO: if schema changes type, drop all attribs?

# django
from django.contrib.contenttypes import generic
from django.db import models

# this app
from models import BaseAttribute, BaseChoice, BaseEntity, BaseSchema

""" TODO:
>>> color = Schema.objects.create(name='color', datatype='many')
>>> dir(color.choices)
>>> color.choices.create()
>>> color.save()
>>> Entity.objects.create(title='apple', color=['green', 'red'])
<Entity ...>
>>> [s.name for s in Schema.objects.all()]
['color', 'm2o_color_green', 'm2o_color_red']
>>> qs = Entity.objects.filter(color='green')
[<Entity ...>]
>>> qs = Entity.objects.filter(color='red')
[<Entity ...>]
>>> e = qs[0]
>>> e.color
['green', 'red']
>>> e.color = ['green']
>>> e.save()
>>> qs = Entity.objects.filter(color='green')
[<Entity ...>]
>>> qs = Entity.objects.filter(color='red')
[]
>>> x
### this is NOT a test; tests are on top of the file!!! ###
"""

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
    attrs = generic.GenericRelation(Attr, object_id_field='entity_id',
                                    content_type_field='entity_type')

    @classmethod
    def get_schemata_for_model(cls):
        return Schema.objects.all()

    def __unicode__(self):
        return self.title

