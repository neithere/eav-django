# -*- coding: utf-8 -*-

# python
import warnings

# django
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
from django.core.urlresolvers import reverse
from django.db.models import (BooleanField, CharField, DateField, DateTimeField,
                              FloatField, ForeignKey, ImageField, IntegerField,
                              Manager, ManyToManyField, Model, NullBooleanField,
                              Q, PositiveIntegerField, TextField)
from django.utils.translation import ugettext_lazy as _

# 3rd-party
from autoslug.fields import AutoSlugField
from autoslug.settings import slugify
from view_shortcuts.decorators import cached_property

# this app
from managers import BaseEntityManager


__all__ = ['BaseAttribute', 'BaseChoice', 'BaseEntity', 'BaseSchema']


def slugify_attr_name(name):
    return slugify(name.replace('_', '-')).replace('-', '_')


def get_entity_lookups(entity):
    ctype = ContentType.objects.get_for_model(entity)
    return {'entity_type': ctype, 'entity_id': entity.pk}


class BaseSchema(Model):
    """
    Metadata for an attribute.
    """
    TYPE_TEXT    = 'text'
    TYPE_INTEGER = 'int'
    TYPE_DATE    = 'date'
    TYPE_BOOLEAN = 'bool'
    TYPE_MANY    = 'many'

    DATATYPE_CHOICES = (
        (TYPE_TEXT,    _('text')),
        (TYPE_INTEGER, _('number')),
        (TYPE_DATE,    _('date')),
        (TYPE_BOOLEAN, _('boolean')),
        (TYPE_MANY,    _('multiple choices')),
    )

    title    = CharField(_('title'), max_length=100, help_text=_('user-friendly attribute name'))
    name     = AutoSlugField(_('name'), populate_from='title',
                             editable=True, blank=True, slugify=slugify_attr_name)
    help_text = CharField(_('help text'), max_length=250, blank=True,
                          help_text=_('short description for administrator'))
    datatype = CharField(_('data type'), max_length=4, choices=DATATYPE_CHOICES)

    required = BooleanField(_('required'))
    searched = BooleanField(_('include in search'))  # i.e. full-text search? mb for text only
    filtered = BooleanField(_('include in filters'))
    sortable = BooleanField(_('allow sorting'))

    class Meta:
        abstract = True
        verbose_name, verbose_name_plural = _('attribute schema'), _('attribute schemata')
        ordering = ['title']

    def __unicode__(self):
        return u'%s (%s) %s' % (self.title, self.get_datatype_display(),
                                _('required') if self.required else '')

    def save(self, **kw):
        super(BaseSchema, self).save(**kw)
        self.save_m2m(self.get_choices())

    def get_choices(self, entity=None):
        """
        Returns a list of name/title tuples::

            schema.get_choices()    # --> [("green", "Green color"), ("red", "Red color")]

        Names are used for lookups, titles are displayed to user.

        This method must be overloaded by subclasses of BaseSchema to enable
        many-to-one schemata machinery.
        """
#        choices = self.choices.all()
#        if entity:
#            entity.filter_
#            choices = self.filter_choices_by_entity(choices, entity)
        return [(choice.name, choice.title) for choice in self.choices.all()]

    def get_attrs(self, entity):
        """
        Returns available attributes for given entity instance.
        Handles many-to-one relations transparently.
        """
        return self.attrs.filter(**get_entity_lookups(entity))

    def save_m2m(self, choices):
        """
        Creates/updates related many-to-one managed schemata.
        (By the way, these "managed" schemata are managed by this very method.)

        Normally called automatically each time the schema is saved.

        This method does not remove managed schemata that are not more in use
        because there may be attributes attached.

        TODO: There should be a command to explicitly wipe all unused instances.
        """

        if not self.datatype == self.TYPE_MANY:
            return
        warnings.warn('Schema.save_m2m() does not do anything!')
        """
        assert 1==0, choices
        # create managed schemata
        for choice, title in choices:
            name = get_m2m_schema_name(self.name, choice)
            try:
                ms = type(self).objects.get(name=name)
            except type(self).DoesNotExist:
                ms = type(self).objects.create(
                    name = name,
                    title = title,
                    datatype = self.TYPE_BOOLEAN,
                    namespace = self,
                )
            else:
                if ms.title != title:
                    ms.title = title
                    ms.save()
        """

    def save_attr(self, entity, value):
        """
        Saves given EAV attribute with given value for given entity.

        If schema is not many-to-one, the value is saved to the corresponding
        Attr instance (which is created or updated).

        If schema is many-to-one, the value is processed thusly:

        * if value is iterable, all Attr instances for corresponding managed m2m
          schemata are updated (those with names from the value list are set to
          True, others to False). If a list item is not in available choices,
          ValueError is raised;
        * if the value is None, all corresponding Attr instances are reset to False;
        * if the value is neither a list nor None, it is wrapped into a list and
          processed as above (i.e. "foo" --> ["foo"]).
        """

        if self.datatype == self.TYPE_MANY:
            self._save_m2m_attr(entity, value)
        else:
            self._save_single_attr(entity, value)

    def _save_single_attr(self, entity, value, schema=None, create_nulls=False, extra={}):
        """
        Creates or updates an EAV attribute for given entity with given value.

        :param schema: schema for attribute. Default it current schema instance.
        :param create_nulls: boolean: if True, even attributes with value=None
            are created (be default they are skipped).
        :param extra: dict: additional data for Attr instance (e.g. title).
        """
        # If schema is not many-to-one, the value is saved to the corresponding
        # Attr instance (which is created or updated).

        schema = schema or self
        lookups = dict(get_entity_lookups(entity), schema=schema, **extra)
        try:
            attr = self.attrs.get(**lookups)
        except self.attrs.model.DoesNotExist:
            attr = self.attrs.model(**lookups)
        if create_nulls or value != attr.value:
            attr.value = value
            for k,v in extra.items():
                setattr(attr, k, v)
            attr.save()

    def _save_m2m_attr(self, entity, value):
        # FIXME: code became dirty, needs refactoring and optimization

        valid_choices = self.get_choices()

        # drop all attributes for this entity/schema pair
        self.get_attrs(entity).delete()

        if not hasattr(value, '__iter__'):
            value = [value]

        enabled_choices = value

        # If a list item is not in available choices, ValueError is raised
        if not set(enabled_choices).issubset([x[0] for x in valid_choices]):
            raise ValueError(u'Cannot save %s.%s.%s: expected subset of %s, '
                              'got "%s"'.encode('utf8') % (type(entity).__module__,
                                    type(entity).__name__, self.name,
                                    [x[0] for x in self.get_choices()], value))

        # Attr instances for corresponding managed m2m schemata are updated
        for choice in self.choices.all():
            #schema_name = get_m2m_schema_name(name, choice)
            if choice.name in enabled_choices:
                self._save_single_attr(
                    entity,
                    value = None,   #True if schema_name in enabled_choices else False,
                    schema = self,  #type(self).objects.get(name=schema_name),
                    create_nulls = True,    # <-- because it's not value_X=Y but choice=Y
                    extra = {'choice': choice}
                )


class BaseEntity(Model):
    """
    Entity, the "E" in EAV. This model is abstract and must be subclassed.
    See tests for examples.
    """

    objects = BaseEntityManager()

    class Meta:
        abstract = True

    def save(self, force_eav=False, **kwargs):
        """
        Saves entity instance and creates/updates related attribute instances.

        :param eav: if True (default), EAV attributes are saved along with entity.
        """
        # save entity
        super(BaseEntity, self).save(**kwargs)

        # TODO: think about use cases; are we doing it right?
        #if not self.check_eav_allowed():
        #    warnings.warn('EAV attributes are going to be saved along with entity'
        #                  ' despite %s.check_eav_allowed() returned False.'
        #                  % type(self), RuntimeWarning)


        # create/update EAV attributes
        for name in self.schema_names:
            schema = self.get_schema(name)
            value = getattr(self, name, None)
            schema.save_attr(self, value)

    def __getattr__(self, name):
        if not name.startswith('_'):
            if name in self._schemata_dict:
                schema = self.get_schema(name)
                attrs = schema.get_attrs(self)
                if schema.datatype == schema.TYPE_MANY:
                    return [a.value.name for a in attrs if a.value]
                else:
                    return attrs[0].value if attrs else None
        raise AttributeError('%s does not have attribute named "%s".' % (self._meta.object_name, name))

    def __iter__(self):
        "Iterates over non-empty EAV attributes. Normal fields are not included."
        return iter([a for a in self._eav_attrs if getattr(self, a.schema.name, None)])

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
        schema_model = self.get_schemata_for_model().model
        defaults = {'schema__in': [s.pk for s in self._schemata]}
        return self.attrs.filter(**defaults).select_related()

    #@cached_property
    @property
    def _eav_attrs_dict(self):
        return dict((a.schema.name, a) for a in self._eav_attrs)

    @classmethod
    def get_schemata_for_model(cls):
        return NotImplementedError('BaseEntity subclasses must define method '
                                   '"get_schemata_for_model" which returns a '
                                   'QuerySet for a BaseSchema subclass.')

    def get_schemata_for_instance(self, qs):
        return qs

    def get_schemata(self):
        if hasattr(self, '_schemata_cache') and self._schemata_cache is not None:
            return self._schemata_cache
        all_schemata = self.get_schemata_for_model().select_related()
        self._schemata_cache = self.get_schemata_for_instance(all_schemata)
        return self._schemata_cache

    #@cached_property
    @property
    def _schemata(self):
        return self.get_schemata()

    #@cached_property
    @property
    def _schemata_dict(self):
        return dict((s.name, s) for s in self._schemata)

    def get_schema(self, name):
        return self._schemata_dict[name]

    def check_eav_allowed(self):
        """
        Returns True if entity instance allows EAV attributes to be attached.

        Can be useful if some external data is required to determine available
        schemata and that data may be missing. In such cases this method should
        be overloaded to check whether the data is available.
        """
        return True

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


class BaseChoice(Model):
    title = CharField(max_length=100)
    name = AutoSlugField(_('name'), populate_from='title',
                             editable=True, blank=True, slugify=slugify_attr_name)
    schema = NotImplemented

    class Meta:
        abstract = True
        unique_together = ('schema', 'name')

    def __unicode__(self):
        return u'%s "%s"' % (self.schema.title, self.title)


class BaseAttribute(Model):
    entity_type = ForeignKey(ContentType)
    entity_id = IntegerField()
    entity = generic.GenericForeignKey(ct_field="entity_type", fk_field='entity_id')

    value_text = TextField(blank=True, null=True)
    value_int = IntegerField(blank=True, null=True)
    value_date = DateField(blank=True, null=True)
    value_bool = NullBooleanField(blank=True)    # TODO: ensure that form invalidates null booleans (??)

    #entity = NotImplemented    # must be FK
    schema = NotImplemented    # must be FK
    choice = NotImplemented    # must be nullable FK

    class Meta:
        abstract = True
        verbose_name, verbose_name_plural = _('attribute'), _('attributes')
        #ordering = ['item', 'schema']
        unique_together = ('entity_type', 'entity_id', 'schema', 'choice')

    def __unicode__(self):
        return u'%s: %s "%s"' % (self.entity, self.schema.title, self.value)

    def _get_value(self):
        if self.schema.datatype == self.schema.TYPE_MANY:
            return self.choice
        return getattr(self, 'value_%s' % self.schema.datatype)

    def _set_value(self, new_value):
        setattr(self, 'value_%s' % self.schema.datatype, new_value)

    value = property(_get_value, _set_value)


# xxx catch signal Attr.post_save() --> update attr.item.attribute_cache (JSONField or such)
