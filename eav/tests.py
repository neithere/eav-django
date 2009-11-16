# -*- coding: utf-8 -*-

# django
from django.db import models

# this app
from models import Attr, BaseEntity, BaseSchema

__doc__ = """
>>> Schema.objects.create(name='colour', datatype='text', title='Colour')
<Schema: Colour (text) >
>>> Schema.objects.create(name='taste', datatype='text', title='Taste')
<Schema: Taste (text) >
>>> e = Entity.objects.create(title='apple', colour='green')
>>> e.title
'apple'
>>> e.colour
'green'
>>> e.attrs.all()
[<Attr: apple: Colour "green">]
>>> e.taste = 'sweet'
>>> e.attrs.all()
[<Attr: apple: Colour "green">]
>>> e.colour = 'yellow'
>>> e.save()
>>> e.attrs.all()
[<Attr: apple: Colour "yellow">, <Attr: apple: Taste "sweet">]
>>> Entity.objects.by_attributes(title='apple')
[<Entity: apple>]
>>> Entity.objects.by_attributes(colour='yellow')
[<Entity: apple>]
>>> Entity.objects.by_attributes(colour='yellow', title='apple')
[<Entity: apple>]
"""


class Schema(BaseSchema):
    pass


class Entity(BaseEntity):
    schema_model = Schema
    title = models.CharField(max_length=100)

    def __unicode__(self):
        return self.title



'''     >>> class Rubric(Model):
        ...     name = CharField(max_length=100)
        ...     schemata = ManyToManyField(Schema)
        ...
        >>> class Item(BaseEntity):
        ...     name = CharField(max_length=100)
        ...     rubric = ForeignKey(Rubric)
        ...     def filter_schemata(self, qs):
        ...         return qs.filter(rubric_set=self.rubric)
        ...
        >>> fruits = Rubric(name='Fruits')
        >>> fruits.schemata.create(name='colour', datatype='text')
        <Schema 'colour'>
        >>> fruits.schemata.create(name='taste', datatype='text')
        <Schema 'taste'>
        >>> apple = Item(name='Green Apple', rubric=fruits, colour='green')
        >>> [x for x in apple]
        ['name', rubric', 'colour', 'taste']
        >>> 'colour' in apple
        True
        >>> apple.schema_names
        ['colour', 'taste']
        >>> apple.field_names
        ['name', 'rubric']
        >>> apple.name
        'Green Apple'
        >>> apple['name']
        'Green Apple'
        >>> apple.colour
        >>> apple['colour']
        'Green Apple'
        >>> apple.get_schema('colour')
        <Schema 'colour'>
'''
