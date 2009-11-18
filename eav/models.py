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


__all__ = ['Attr', 'BaseEntity', 'BaseSchema', 'MANAGED_MANY_TO_ONE_PREFIX',
           'EntityManager']


MANAGED_MANY_TO_ONE_PREFIX = 'm2o'


def get_m2o_schema_name(name, value):
    """
    Returns manages many-to-one schema name for given "naive" name and value
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
    required = BooleanField(_('required'))
    searched = BooleanField(_('include in search'))  # i.e. full-text search? mb for text only
    filtered = BooleanField(_('include in filters'))
    sortable = BooleanField(_('allow sorting'))

    # TODO: these flags are mutually exclusive; make one? or three choices? or move smth to "through" model?
    #
    # if True, this schema is managed automatically and not present in forms
    # but is used in lookups
    managed = BooleanField(editable=False)
    # if True, this schema is not used in lookups and only present in forms;
    # it displays ...............................?
    m2o = BooleanField(editable=False)

    attrs = generic.GenericRelation('Attr', content_type_field='schema_content_type',
                                    object_id_field='schema_object_id')    # XXX do we need this?

    class Meta:
        abstract = True
        verbose_name, verbose_name_plural = _('attribute schema'), _('attribute schemata')
        ordering = ['title']

    def __unicode__(self):
        return u'%s (%s) %s' % (self.title, self.get_datatype_display(),
                                _('required') if self.required else '')

    def get_choices(self):
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

    def save(self, **kwargs):
        instance = super(BaseSchema, self).save(**kwargs)
        if self.m2o:
            # create managed schemata
            for choice, title in self.get_choices():
                name = get_m2o_schema_name(self.name, choice)
                if __debug__: print 'choice', choice, 'title', title, '-->', name
                try:
                    ms = type(self).objects.get(name=name)
                except type(self).DoesNotExist:
                    if __debug__: print '  creating managed schema...'
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
        return instance

    def save_attr(self, entity, name, value):
        """
        Saves given EAV attribute with given value for given entity.

        If schema is not many-to-one, the value is saved to the corresponding
        Attr instance (which is created or updated).

        If schema is many-to-one, the value is processed thusly:

        * if value is list, all Attr instances for corresponding managed m2o
          schemata are updated (those with names from the value list are set to
          True, others to False). If a list item is not in available choices,
          ValueError is raised;
        * if the value is None, all corresponding Attr instances are reset to False;
        * if the value is neither a list nor None, it is wrapped into a list and
          processed as above (i.e. "foo" --> ["foo"]).
        """

        if __debug__: print u'%s.save_attr(entity=%s, name="%s", value="%s")' % (self, entity, name, value)

        if self.m2o:
            # schema is many-to-one

            if __debug__: print '  m2o'

            valid_choices = [get_m2o_schema_name(name, c) for c,t in self.get_choices()]

            if __debug__: print '  valid_choices', valid_choices

            if isinstance(value, list):     # xxx maybe hasattr('__iter__') ?
                if __debug__: print '  value is list'

                enabled_choices = [get_m2o_schema_name(name, v) for v in value]

                if __debug__: print '    enabled choices:', enabled_choices

                # If a list item is not in available choices, ValueError is raised
                if not set(enabled_choices).issubset(valid_choices):
                    raise ValueError(u'Cannot save %s.%s: expected subset of %s, '
                                     'got "%s"'.encode('utf8') % (entity, name,
                                     [x[0] for x in self.get_choices()], value))

                # Attr instances for corresponding managed m2o schemata are updated

                for choice, title in self.get_choices():
                    if __debug__: print '      choice', choice
                    schema_name = get_m2o_schema_name(name, choice)
                    managed_schema = type(self).objects.get(name=schema_name)
                    lookups = {
                        # entity
                        'entity_content_type': entity.attrs.content_type,
                        'entity_object_id': entity.pk,
                        ## schema
                        #'schema__name': choice,    # e.g. 'm2o_color_blue'
                        # schema
                        'schema_content_type': self.attrs.content_type,
                        'schema_object_id': managed_schema.pk,
                    }
                    if __debug__: print '      lookups:', lookups
                    try:
                        attr = Attr.objects.get(**lookups)
                        if __debug__: print '      attr found, updating'
                    except Attr.DoesNotExist:
                        # only create attribute if it's not None
                        if __debug__: print '      attr not found, creating'
                        attr = Attr(**lookups)
                    attr.title = title
                    attr.value = True if schema_name in enabled_choices else False
                    if __debug__: print 'schema_name is', ('in' if attr.value else 'not in'), 'enabled_choices'
                    attr.save()

            elif value is None:
                # if the value is None, all corresponding Attr instances are reset to False
                if __debug__: print '  value is None, resetting all Attr\'s'
                Attr.objects.filter(schema__name__in=valid_choices).update(value_bool=False)
            else:
                # if the value is neither a list nor None, ValueError is raised.
                if __debug__: print '  value is wrong:)'
                raise ValueError('Cannot save %s.%s: expected list or None, got "%s"'
                                % (entity, name, value))
        else:
            # If schema is not many-to-one, the value is saved to the corresponding
            # Attr instance (which is created or updated).
            if __debug__: print '  not m2o'
            lookups = {
                # entity
                'entity_content_type': entity.attrs.content_type,
                'entity_object_id': entity.pk,
                # schema
                'schema_content_type': self.attrs.content_type,
                'schema_object_id': self.pk,
            }
            if __debug__: print '    lookups:', lookups
            try:
                attr = Attr.objects.get(**lookups)
            except Attr.DoesNotExist:
                # only create attribute if it's not None
                if __debug__: print '    attr not found'
                if value:
                    if __debug__: print '      value is not None, creating'
                    attr = Attr(**lookups)
                    attr.value = value
                    attr.save()
            else:
                # update attribute; keep it even if resetting value to None
                if __debug__: print '    attr found, updating'
                if value != attr.value:
                    attr.value = value
                    attr.save()


class EntityManager(Manager):

    def _filter_by_schema_straight(self, qs, lookup, sublookup, value, schema):
        if __debug__: print '  ordinary schema'
        # using normal schema.
        # filter entities by attribute which is linked to given schema
        # and has given value in the field for schema's datatype.
        value_lookup = 'attrs__value_%s' % schema.datatype
        if sublookup:
            value_lookup = '%s__%s' % (value_lookup, sublookup)
        lookups = {
            # schema
            'attrs__schema_content_type': schema.attrs.content_type,
            'attrs__schema_object_id': schema.pk,
            # value
            str(value_lookup): value,
        }
        if __debug__: print '    lookups:', lookups
        return qs.filter(**lookups)

    def _filter_by_schema_m2o(self, qs, lookup, value, schema):
        if __debug__: print '  many-to-one management schema'
        # using many-to-one schema. Actually it is:
        # a) "management schema" (one) which can contain a list
        #     of choices (defined by get_choices), its value doesn't matter;
        # b) "managed schema" (many) which names are like "m2o_color_blue"
        #     where "color" is management schema's name, and "blue"
        #     is one of choices. Datatype in bool.
        # So, if we've got color="blue", we do the following:
        #

        #choices = schema.get_choice_names()    # ['green', 'red', 'blue']
        schema_model = self.model.get_schemata_for_model().model
        managed_name = get_m2o_schema_name(schema.name, value)
        try:
            managed_schema = schema_model.objects.get(name=managed_name)
        except schema_model.DoesNotExist:
            # TODO: smarter error message, i.e. how could this happen and what to do
            raise ValueError(u'Could not find managed m2o schema %s for name "%s" '
                              'and value "%s"'.encode('utf8') % (managed_name, schema.name, value))
        #subschemata = Schema.objects.filter(name__in=['m2o_%s_%s' % (schema.name, choice) for choice in choices])
        #for subschema in subschemata:
        lookups = {
            # schema
            'attrs__schema_content_type': managed_schema.attrs.content_type,
            'attrs__schema_object_id': managed_schema.pk,
            # value
            'attrs__value_bool': True,
        }
        if __debug__: print '    lookups:', lookups
        return qs.filter(**lookups)

    def _filter_by_lookup(self, qs, lookup, value):
        fields   = self.model._meta.get_all_field_names()
        schemata = dict((s.name, s) for s in self.model.get_schemata_for_model())

        if '__' in lookup:
            name, sublookup = lookup.split('__')
        else:
            name, sublookup = lookup, None

        if name in fields:
            # ordinary model field
            if __debug__: print name, 'is a field'
            return qs.filter(**{lookup: value})
        elif name in schemata:
            # EAV attribute (Attr instance linked to entity)
            if __debug__: print name, 'is an EAV attribute'
            schema = schemata.get(name)
            if schema.m2o:
                if sublookup:
                    raise NameError('%s is not a valid lookup: sublookups cannot '
                                    'be used with m2o attributes.' % lookup)
                return self._filter_by_schema_m2o(qs, lookup, value, schema)
            else:
                return self._filter_by_schema_straight(qs, lookup, sublookup, value, schema)
        else:
            raise NameError('Cannot filter items by attributes: unknown '
                            'attribute "%s". Available fields: %s. '
                            'Available schemata: %s.' % (name,
                            ', '.join(fields), ', '.join(schemata)))

    def filter(self, **kw):
        """
        A wrapper around standard filter() method. Allows to construct queries
        involving both normal fields and EAV attributes without thinking about
        implementation details. Usage::

            ConcreteEntity.objects.by_attributes(rubric=1, price=2, colour='green')

        ...where `rubric` is a ForeignKey field, and `colour` is the name of an
        EAV attribute represented by Schema and Attr models.
        """
        #print '%s.by_attributes(%s)' % (self.model._meta.object_name, kwargs)

        qs = self.all()
        for lookup, value in kw.items():

            # FIXME FIXME managed sche,a doesn't get "m2o" flag!!!

            qs = self._filter_by_lookup(qs, lookup, value)
        return qs


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
        schemata = dict((s.name, s) for s in self.model.get_schemata_for_model())

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

    def save(self, eav=True, **kwargs):
        """
        Saves entity instance and creates/updates related attribute instances.

        :param eav: if True (default), EAV attributes are saved along with entity.
        """
        #print '%s.save(%s)' % (self._meta.object_name, kwargs)
        # save entity
        super(BaseEntity, self).save(**kwargs)

        # create/update EAV attributes
        for name in self.schema_names:
            value = getattr(self, name, None)
            schema = self.get_schema(name)
            #attr, _ = Attr.objects.get_or_create(schema=schema)#, content_object=obj)
            if not schema.managed:
                schema.save_attr(self, name, value)

    def __getattr__(self, name):
        if not name.startswith('_'):
            if name in self._schemata_dict:
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
            'schema_object_id__in': self._schemata,
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

    #@cached_property
    @property
    def _schemata(self):
        qs = self.get_schemata_for_model().select_related()
        return self.get_schemata_for_instance(qs)

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


# xxx catch signal Attr.post_save() --> update attr.item.attribute_cache (JSONField or such)
