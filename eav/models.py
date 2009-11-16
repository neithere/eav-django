# -*- coding: utf-8 -*-

# django
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
from django.core.urlresolvers import reverse
from django.db.models import (BooleanField, CharField, DateField, DateTimeField,
                              FloatField, ForeignKey, ImageField, IntegerField,
                              Manager, ManyToManyField, Model, NullBooleanField,
                              PositiveIntegerField, TextField)
from django.utils.translation import ugettext_lazy as _

# 3rd-party
from autoslug.fields import AutoSlugField
from autoslug.settings import slugify
from view_shortcuts.decorators import cached_property


__all__ = ['Attr', 'BaseEntity', 'BaseSchema', 'EntityManager']


def slugify_attr_name(name):
    return slugify(name).replace('-', '_')


class BaseSchema(Model):
    """Metadata for an attribute."""
    DATATYPE_CHOICES = (
        ('text', _('text')),
        ('int',  _('number')),
        ('date', _('date')),
        ('bool', _('boolean')),
    )
    title    = CharField(_('title'), max_length=100, help_text=_('user-friendly attribute name'))
    name     = AutoSlugField(_('name'), unique=True, editable=True, blank=True,
                             populate_from='title', slugify=slugify_attr_name)
    help_text = CharField(_('help text'), max_length=250, blank=True,
                          help_text=_('short description for administrator'))
    datatype = CharField(_('data type'), max_length=4, choices=DATATYPE_CHOICES)
    required = BooleanField(_('required'))
    searched = BooleanField(_('include in search'))  # i.e. full-text search? mb for text only
    filtered = BooleanField(_('include in filters'))
    sortable = BooleanField(_('allow sorting'))

    attrs = generic.GenericRelation('Attr', content_type_field='schema_content_type',
                                    object_id_field='schema_object_id')    # XXX do we need this?

    class Meta:
        abstract = True
        verbose_name, verbose_name_plural = _('attribute schema'), _('attribute schemata')
        ordering = ['title']

    def __unicode__(self):
        return u'%s (%s) %s' % (self.title, self.get_datatype_display(),
                                _('required') if self.required else '')


class EntityManager(Manager):

    def by_attributes(self, **kw):
        """
        A wrapper around standard filter() method. Allows to construct queries
        involving both normal fields and EAV attributes without thinking about
        implementation details. Usage::

            ConcreteEntity.objects.by_attributes(rubric=1, price=2, colour='green')

        ...where `rubric` is a ForeignKey field, and `colour` is the name of an
        EAV attribute represented by Schema and Attr models.
        """
        q = self.all()
        fields   = self.model._meta.get_all_field_names()
        schemata = dict((s.name, s) for s in self.model.schema_model.objects.all())

        for lookup, value in kw.items():
            if '__' in lookup:
                name, sublookup = lookup.split('__')
            else:
                name, sublookup = lookup, None

            if name in fields:
                lookups = {lookup: value}
            elif name in schemata:
                schema = schemata.get(name)
                value_lookup = 'attrs__value_%s' % schema.datatype
                if sublookup:
                    value_lookup = '%s__%s' % (value_lookup, sublookup)
                lookups = {'attrs__schema_content_type': schema.attrs.content_type,
                           'attrs__schema_object_id': schema.pk,
                           str(value_lookup): value}
            else:
                raise NameError('Cannot filter items by attributes: unknown '
                                'attribute "%s". Available fields: %s. '
                                'Available schemata: %s.' % (name,
                                ', '.join(fields), ', '.join(schemata)))
            q = q.filter(**lookups)
        return q

    def create(self, **kwargs):
        """
        Creates entity instance and related Attr instances.

        Note that while entity instances may filter schemata by fields, that
        filtering does not take place here. Attribute of any schema will be saved
        successfully as long as such schema exists.

        Note that we cannot create attribute with no pre-defined schema because
        we must know attribute type in order to properly put value into the DB.
        """
        fields = self.model._meta.get_all_field_names()
        schemata = dict((s.name, s) for s in self.model.schema_model.objects.all())

        # check if all attributes are known
        possible_names = set(fields) | set(schemata.keys())
        wrong_names = set(kwargs.keys()) - possible_names
        if wrong_names:
            raise NameError('Cannot create %s: unknown attribute(s) "%s". '
                            'Available fields: (%s). Available schemata: (%s).'
                            % (self.model._meta.object_name, '", "'.join(wrong_names),
                               ', '.join(fields), ', '.join(schemata)))

        # init entity with fields
        instance = self.model(**dict((k,v) for k,v in kwargs.items() if k in fields))

        # set attributes; instance will check schemata on save
        for name, value in kwargs.items():
            setattr(instance, name, value)

        # save instance and EAV attributes
        instance.save(force_insert=True)

        return instance

'''
class AttrDescriptor(object):
    def __init__(self, name):
        self.name = name

    def __get__(self, instance):


    def __set__(self, instance, value)


    def save(self):
        self.instance.save()
'''

class BaseEntity(Model):
    """
    Entity, the "E" in EAV. This model is abstract and must be subclassed.

    Usage::

        >>> class Rubric(Model):
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
    """

    attrs = generic.GenericRelation('Attr', content_type_field='entity_content_type',
                                    object_id_field='entity_object_id')

    objects = EntityManager()

    class Meta:
        abstract = True

    def save(self, **kwargs):
        # save entity
        super(BaseEntity, self).save(**kwargs)

        # create/update EAV attributes
        defaults = {'entity_content_type': self.attrs.content_type,
                    'entity_object_id': self.pk,}

        for name in self.schema_names:
            schema = self.get_schema(name)
            #attr, _ = Attr.objects.get_or_create(schema=schema)#, content_object=obj)
            schema_defaults = {'schema_content_type': schema.attrs.content_type,
                               'schema_object_id': schema.pk,}
            lookups = dict(defaults, **schema_defaults)
            attr, _ = Attr.objects.get_or_create(**lookups)
            #f = attr._meta.get_field('value_%s' % schema.datatype)
            #f.save_form_data(attr, self.get_attr_value(name))
            attr.value = getattr(self, name, '')
            attr.save()

    def __getattr__(self, name):
        if not name.startswith('_'):
            if name in self._schemata_dict:
                attr = self._eav_attrs_dict.get(name)
                return attr.value if attr else None
        raise AttributeError('%s does not have attribute named "%s".' % (self._meta.object_name, name))

    def __iter__(self):
        "Iterates over EAV attributes. Normal fields are not included."           # xxx do we use this anywhere?
        return iter(self._eav_attrs)

    # names

    #@cached_property
    @property
    def field_names(self):
        return self._meta.get_all_field_names()

    #@cached_property
    @property
    def schema_names(self):
        return [s.name for s in self._schemata]

    #@cached_property
    @property
    def all_names(self):
        return self.field_names + self.schema_names

    # linked EAV data

    #@cached_property
    @property
    def _eav_attrs(self):
        defaults = {
            'schema_content_type': Attr.schema.get_content_type(self.schema_model),
            'schema_object_id__in': self._schemata,
        }
        return self.attrs.filter(**defaults).select_related()

    #@cached_property
    @property
    def _eav_attrs_dict(self):
        return dict((a.schema.name, a) for a in self._eav_attrs)

    @property
    def schema_model(cls):
        return Schema

    def filter_schemata(self):
        return qs

    #@cached_property
    @property
    def _schemata(self):
        qs = self.schema_model.objects.select_related()
        return self.filter_schemata(qs)

    #@cached_property
    @property
    def _schemata_dict(self):
        return dict((s.name, s) for s in self._schemata)

    def get_schema(self, name):
        return self._schemata_dict[name]

    '''
    @cached_property
    def all_eav_attributes(self):
        return self.attrs.select_related()

    @cached_property
    def all_attributes_dict(self):
        """ Returns all existing attributes for this entity, regardless to whether
        they confirm to the schemata applied by entity's rubric.
        """
        return dict((x.schema.name, x) for x in self.all_attributes)

    @cached_property
    def valid_attributes(self):
        """ Returns existing attributes for this entity, filtered by the schemata
        applied by entity's rubric.
        """
        # ignore attributes for which there's no schema
        q = self._all_attributes.filter(schema__in=self.schemata.values())

        # TODO ignore inactive attrs:
        #print 'active', [x for x in q if x.removed]
        #q = q.exclude(removed=True

        return dict((x.schema.name, x) for x in q)


    def get_lookups(self):
        return {'rubric': self.rubric}

    def get_schemata_for_instance(self):
        schemata = Schema.objects.all()
        return self.filter_schemata(schemata)

    def filter_schemata_by_fields(self, qs):
        return qs


    @classmethod
    def get_schemata(cls, **kwargs):
        """
        Returns schemata available for this entity class.
        Instance attributes and their values can be passed as keyword arguments.
        """
        # you may want to overload this method in a custom Entity model
        # and use kwargs to filter schemata by instance fields
        return Schema.objects.all()

    @classmethod
    def get_schemata_dict(cls, **kwargs):
        """
        Returns a dictionary of existing schemata where keys are names of attributes
        and values are schemata describing these names.

        Instance attributes and their values can be passed as keyword arguments.
        """
        schemata = cls.get_schemata(**kwargs)
        return dict((s.name,s) for s in schemata)

    # names

    @property
    def field_names(self):
        return self._meta.get_all_field_names()

    @property
    def schema_names(self):
        return self.get_schemata()

    @property
    def all_names(self):
        return self.field_names + self.schema_names

    # metadata instances

    def get_schemata(self):
        qs = Schema.objects.all()
        return self.filter_schemata(qs)

    def filter_schemata(self, qs):
        return qs


    @classmethod
    def get_nameslots(cls):
        "Returns all possible attribute names for this model."
        fields = cls._meta.get_all_field_names()
        schemata = cls.get_schemata_dict()
        return fields + schemata.keys()

    @cached_property
    def fields_and_eav(self):
        "Returns all fields and EAV attributes for this instance."
        # TODO: replace this method with .keys() or __iter__
        fields = self._meta.get_all_field_names()
        schemata = self.get_schemata_dict(self.rubric)
        return fields + schemata.keys()

    def value_for(self, name):
        "Returns value of field or EAV attribute with given name."
        # TODO: replace this method with __getattr__
        if not name in self.fields_and_eav:
            raise NameError('Unknown field or schema. Available: %s' %
                            ', '.join(self.fields_and_eav))
        if name in self._meta.get_all_field_names():
            return getattr(self, name)
        attr = self.attributes.get(name)
        if attr:
            return attr.value
        return None

    @cached_property
    def _all_attributes(self):
        return self.attrs.select_related()

    @cached_property
    def all_attributes(self):
        """ Returns all existing attributes for this entity, regardless to whether
        they confirm to the schemata applied by entity's rubric.
        """
        return dict((x.schema.name, x) for x in self._all_attributes)

    @cached_property
    def attributes(self):
        """ Returns existing attributes for this entity, filtered by the schemata
        applied by entity's rubric.
        """
        # ignore attributes for which there's no schema
        q = self._all_attributes.filter(schema__in=self.schemata.values())

        # TODO ignore inactive attrs:
        #print 'active', [x for x in q if x.removed]
        #q = q.exclude(removed=True

        return dict((x.schema.name, x) for x in q)

    @cached_property
    def schemata(self):
        return get_schemata_dict(self.rubric)
    '''
    def is_valid(self):
        "Returns True if attributes and their values conform with schema."

        raise NotImplementedError()

        '''
        schemata = self.rubric.schemata.all()
        return all(x.is_valid for x in self.attributes)
        # 1. check if all required attributes are present
        for schema in schemata:
            pass
        # 2. check if all attributes have appropriate values
        for schema in schemata:
            pass
        return True
        '''


class Attr(Model):
    entity_content_type = ForeignKey(ContentType, related_name='attrs_in_entity')
    entity_object_id = PositiveIntegerField()
    entity = generic.GenericForeignKey('entity_content_type', 'entity_object_id')

    schema_content_type = ForeignKey(ContentType, related_name='attrs_in_schema')
    schema_object_id = PositiveIntegerField()
    schema = generic.GenericForeignKey('schema_content_type', 'schema_object_id')


    #schema = ForeignKey(Schema, related_name='attrs')
    value_text = TextField(blank=True, null=True)
    value_int = IntegerField(blank=True, null=True)
    value_date = DateField(blank=True, null=True)
    value_bool = NullBooleanField(blank=True)    # TODO: ensure that form invalidates null booleans (??)
    #added = DateTimeField(auto_now_add=True, blank=True, null=True, editable=False)
    #modified = DateTimeField(auto_now=True, blank=True, null=True, editable=False)
    #added_by = ForeignKey(User, blank=True, null=True, editable=False)
    #modified_by = ForeignKey(User, blank=True, null=True, editable=False)
    #removed = BooleanField(default=False, blank=True, null=True, editable=False)

    class Meta:
        verbose_name, verbose_name_plural = _('attribute'), _('attributes')
        #ordering = ['item', 'schema']
        unique_together = ('entity_content_type', 'entity_object_id',
                           'schema_content_type', 'schema_object_id')

    def __unicode__(self):
        return u'%s: %s "%s"' % (self.entity, self.schema.title, self.value)

    def _get_value(self):
        return getattr(self, 'value_%s' % self.schema.datatype)

    def _set_value(self, new_value):
        setattr(self, 'value_%s' % self.schema.datatype, new_value)

    value = property(_get_value, _set_value)


# xxx catch signal Attr.post_save() --> update attr.item.attribute_cache (JSONField or such)
