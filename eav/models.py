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
        #print '%s.by_attributes(%s)' % (self.model._meta.object_name, kwargs)
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
        #print '%s.create(%s)' % (self.model._meta.object_name, kwargs)

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
    See tests for examples.

    Note: you *must* define schema_model attribute to make things work.
    """

    attrs = generic.GenericRelation('Attr', content_type_field='entity_content_type',
                                    object_id_field='entity_object_id')

    objects = EntityManager()

    class Meta:
        abstract = True

    def save(self, **kwargs):
        #print '%s.save(%s)' % (self._meta.object_name, kwargs)
        # save entity
        super(BaseEntity, self).save(**kwargs)

        # create/update EAV attributes
        defaults = {'entity_content_type': self.attrs.content_type,
                    'entity_object_id': self.pk,}

        for name in self.schema_names:
            value = getattr(self, name, None)
            schema = self.get_schema(name)
            #attr, _ = Attr.objects.get_or_create(schema=schema)#, content_object=obj)
            schema_defaults = {'schema_content_type': schema.attrs.content_type,
                               'schema_object_id': schema.pk,}
            lookups = dict(defaults, **schema_defaults)
            # TODO: do not retrieve attrs from db, they should be already fetched
            #       and sit in self._eav_attrs (but it seems to be updated only after save)
            try:
                attr = Attr.objects.get(**lookups)
            except Attr.DoesNotExist:
                if value:
                    attr = Attr(**lookups)
                    attr.value = value
                    attr.save()
            else:
                if value != attr.value:
                    attr.value = value
                    attr.save()
            #attr, _ = Attr.objects.get_or_create(**lookups)
            ##f = attr._meta.get_field('value_%s' % schema.datatype)
            ##f.save_form_data(attr, self.get_attr_value(name))
            #attr.value = value
            #attr.save()

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

    schema_model = NotImplemented

    def filter_schemata(self, qs):
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

    #def save(self,**kw):
    #    print '%s.save(%s) -- %s' % (self._meta.object_name, kw, self)
    #    super(Attr, self).save(**kw)


# xxx catch signal Attr.post_save() --> update attr.item.attribute_cache (JSONField or such)
