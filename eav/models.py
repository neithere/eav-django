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

# this app
from managers import EntityManager


__all__ = ['Attr', 'BaseEntity', 'BaseSchema', 'MANAGED_MANY_TO_ONE_PREFIX']


MANAGED_MANY_TO_ONE_PREFIX = 'm2o'


def get_m2o_schema_name(name, value):
    """
    Returns managed many-to-one schema name for given "naive" name and value
    with respect to `MANAGED_MANY_TO_ONE_PREFIX`::

        get_m2o_schema_name('color', 'green')    # --> 'm2o_color_green'
    """
    return '%s_%s_%s' % (MANAGED_MANY_TO_ONE_PREFIX, name, value)

def slugify_attr_name(name):
    return slugify(name.replace('_', '-')).replace('-', '_')


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

    # TODO: these flags are mutually exclusive; make one? or three choices? or move smth to "through" model?
    #
    # if True, this schema is managed automatically and not present in forms
    # but is used in lookups
    managed = BooleanField(editable=False)
    # if True, this schema is not used in lookups and only present in forms;
    # it displays ...............................?
    m2o = BooleanField(verbose_name=_('multiple choices'))

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

    def get_choices(self, entity):
        """
        Returns a list of name/title tuples::

            schema.get_choices()    # --> [("green", "Green color"), ("red", "Red color")]

        Names are used for lookups, titles are displayed to user.

        This method must be overloaded by subclasses of BaseSchema to enable
        many-to-one schemata machinery. The reasoning for this is that choices
        storage of choices is the duty of application as it depends heavily on
        application models' structure. For example, you may want to store
        choices in a text field of an intermediate ("through") many-to-many model
        between schemata and rubrics (so that choices could be defined on rubric
        level); or you may want to create a Choice model linked to your schema.
        """
        raise NotImplementedError('%s must overload get_choices() to enable '
                                  'many-to-one schemata.' % type(self))


    def get_managed_schemata(self, entity):
        """
        Returns schemata managed by this one. Only applicable to m2o schema.
        """
        if not self.m2o:
            raise ValueError('Cannot get managed schemata: not a many-to-one schema')
        choices = self.get_choices(entity)
        names = [get_m2o_schema_name(self.name, choice) for choice,_ in choices]
        return type(self).objects.filter(name__in=names)

    def get_attrs(self, entity):
        """
        Returns available attributes for given entity instance.
        Handles many-to-one relations transparently.
        """
        managed_schemata = self.get_managed_schemata(entity)
        return Attr.objects.filter(
            #schema__in = managed_schemata,                      # FIXME do we really need ONLY managed schemata?! probably just not m2o
            entity_content_type = entity.attrs.content_type,
            entity_object_id = entity.pk,
        )

    def get_active_choices(self, entity):
        choices = self.get_choices(entity)
        attrs_dict = dict((a.schema.name, a) for a in self.get_attrs(entity))
        for choice, title in choices:
            attr = attrs_dict.get(get_m2o_schema_name(self.name, choice))
            if attr and attr.value:
                yield choice, title

    def save_m2o(self, choices):
        """
        Creates/updates related many-to-one managed schemata.
        (By the way, these "managed" schemata are managed by this very method.)

        Please not that this method is *not* called on save, you must do that
        manually (e.g. catch post_save signal or overload BaseSchema.save and
        call it from there). See get_choices for the reasoning.

        This method does not remove managed schemata that are not more in use
        because there may be attributes attached.

        TODO: There should be a command to explicitly wipe all unused instances.
        """
        if not self.m2o:
            return
        # create managed schemata
        for choice, title in choices:
            name = get_m2o_schema_name(self.name, choice)
            try:
                ms = type(self).objects.get(name=name)
            except type(self).DoesNotExist:
                ms = type(self).objects.create(
                    name = name,
                    title = title,
                    datatype = 'bool',
                    managed = True,
                )
            else:
                if ms.title != title:
                    ms.title = title
                    ms.save()

    def save_attr(self, entity, name, value):
        """
        Saves given EAV attribute with given value for given entity.

        If schema is not many-to-one, the value is saved to the corresponding
        Attr instance (which is created or updated).

        If schema is many-to-one, the value is processed thusly:

        * if value is iterable, all Attr instances for corresponding managed m2o
          schemata are updated (those with names from the value list are set to
          True, others to False). If a list item is not in available choices,
          ValueError is raised;
        * if the value is None, all corresponding Attr instances are reset to False;
        * if the value is neither a list nor None, it is wrapped into a list and
          processed as above (i.e. "foo" --> ["foo"]).
        """

        if self.m2o:
            self._save_m2o_attr(entity, name, value)
        else:
            self._save_single_attr(entity, name, value)

    def _save_single_attr(self, entity, name, value, schema=None,
                          create_nulls=False, extra={}):
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
        lookups = {
            # entity
            'entity_content_type': entity.attrs.content_type,
            'entity_object_id': entity.pk,
            # schema
            'schema_content_type': schema.attrs.content_type,
            'schema_object_id': schema.pk,
        }
        try:
            attr = Attr.objects.get(**lookups)
        except Attr.DoesNotExist:
            attr = Attr(**lookups)
        if create_nulls or value != attr.value:
            attr.value = value
            for k,v in extra.items():
                setattr(attr, k, v)
            attr.save()

    def _save_m2o_attr(self, entity, name, value):
        # schema is many-to-one

        valid_choices = [get_m2o_schema_name(name, c) for c,t in self.get_choices(entity)]

        if value is None:
            # reset related Attr instances to False
            Attr.objects.filter(schema__name__in=valid_choices).update(value_bool=False)
            return

        if not hasattr(value, '__iter__'):
            value = [value]

        enabled_choices = [get_m2o_schema_name(name, v) for v in value]

        # If a list item is not in available choices, ValueError is raised
        if not set(enabled_choices).issubset(valid_choices):
            raise ValueError(u'Cannot save %s.%s.%s: expected subset of %s, '
                                'got "%s"'.encode('utf8') % (type(entity).__module__,
                                type(entity).__name__, name,
                                [x[0] for x in self.get_choices(entity)], value))

        # Attr instances for corresponding managed m2o schemata are updated
        for choice, title in self.get_choices(entity):
            schema_name = get_m2o_schema_name(name, choice)
            self._save_single_attr(entity, schema_name,
                value = True if schema_name in enabled_choices else False,
                schema = type(self).objects.get(name=schema_name),
                create_nulls = True,
                extra = {'title': title}
            )


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

    def save(self, eav=True, **kwargs):
        """
        Saves entity instance and creates/updates related attribute instances.

        :param eav: if True (default), EAV attributes are saved along with entity.
        """
        # save entity
        super(BaseEntity, self).save(**kwargs)

        if not self.check_eav_allowed():
            return

        # create/update EAV attributes
        for name in self.schema_names:
            value = getattr(self, name, None)
            schema = self.get_schema(name)
            if not schema.managed:
                schema.save_attr(self, name, value)

    def __getattr__(self, name):
        if not name.startswith('_'):
            if name in self._schemata_dict:
                schema = self._schemata_dict[name]
                if schema.m2o:
                    return [x[0] for x in schema.get_active_choices(self)]
                attr = self._eav_attrs_dict.get(name)
                return attr.value if attr else None
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
        defaults = {
            'schema_content_type': Attr.schema.get_content_type(schema_model),
            'schema_object_id__in': [s.pk for s in self._schemata],
            #'schema__managed': False,
        }
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

    @cached_property
    #@property
    def _schemata(self):
        all_schemata = self.get_schemata_for_model().select_related()
        return self.get_schemata_for_instance(all_schemata)

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
