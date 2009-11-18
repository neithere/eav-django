# -*- coding: utf-8 -*-

# django
from django.db import models

# this app
from models import Attr, BaseEntity, BaseSchema

__doc__ = """
>>> MySchema.objects.create(name='colour', datatype='text', title='Colour')
<MySchema: Colour (text) >
>>> MySchema.objects.create(name='taste', datatype='text', title='Taste')
<MySchema: Taste (text) >
>>> e = MyEntity.objects.create(title='apple', colour='green')
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
>>> MyEntity.objects.filter(title='apple')
[<MyEntity: apple>]
>>> MyEntity.objects.filter(colour='yellow')
[<MyEntity: apple>]
>>> MyEntity.objects.filter(colour='yellow', title='apple')
[<MyEntity: apple>]

### many-to-one

>>> size = MySchema.objects.create(name='size', title='Size', datatype='text', m2o=True)
>>> e = MyEntity(title='T-shirt')
>>> e.size = 's'
>>> e.save()
>>> e2 = MyEntity.objects.get(pk=e.pk)
>>> e2.size
['s']
>>> e2.size = ['wrong choice']
>>> e2.save()
Traceback (most recent call last):
    ...
ValueError: Cannot save T-shirt.size: expected subset of ['s', 'm', 'l'], got "['wrong choice']"
>>> e2.size = ['s', 'l']
>>> e2.save()
>>> e3 = MyEntity.objects.get(pk=e.pk)
>>> e3.size
['s', 'l']
>>> MySchema.objects.filter(managed=False)
[<MySchema: Colour (text) >, <MySchema: Size (text) >, <MySchema: Taste (text) >]
>>> MySchema.objects.filter(managed=True)
[<MySchema: Large (boolean) >, <MySchema: Medium (boolean) >, <MySchema: Small (boolean) >]
>>> Attr.objects.all()
[<Attr: apple: Colour "yellow">, <Attr: apple: Taste "sweet">, <Attr: T-shirt: Small "True">, \
<Attr: T-shirt: Medium "False">, <Attr: T-shirt: Large "True">]
"""


class MySchema(BaseSchema):
    def get_choices(self):
        # testingly hardcoded choices for a "size" schema
        return [
            ('s', 'Small'),
            ('m', 'Medium'),
            ('l', 'Large'),
        ]


class MyEntity(BaseEntity):
    schema_model = MySchema
    title = models.CharField(max_length=100)

    @classmethod
    def get_schemata_for_model(cls):
        return MySchema.objects.all()

    def __unicode__(self):
        return self.title



'''     >>> class Rubric(Model):
        ...     name = CharField(max_length=100)
        ...     schemata = ManyToManyField(MySchema)
        ...
        >>> class Item(BaseMyEntity):
        ...     name = CharField(max_length=100)
        ...     rubric = ForeignKey(Rubric)
        ...     def filter_schemata(self, qs):
        ...         return qs.filter(rubric_set=self.rubric)
        ...
        >>> fruits = Rubric(name='Fruits')
        >>> fruits.schemata.create(name='colour', datatype='text')
        <MySchema 'colour'>
        >>> fruits.schemata.create(name='taste', datatype='text')
        <MySchema 'taste'>
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
        <MySchema 'colour'>
'''
