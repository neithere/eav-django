# -*- coding: utf-8 -*-

# django
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
from django.core.urlresolvers import reverse
from django.db.models import (BooleanField, CharField, DateField, DateTimeField,
                              FloatField, ForeignKey, ImageField, IntegerField,
                              Manager, ManyToManyField, Model, TextField)
from django.utils.translation import ugettext_lazy as _

# 3rd-party
from autoslug.fields import AutoSlugField
from autoslug.settings import slugify
from view_shortcuts.decorators import cached_property


__all__ = ['Attr', 'BaseEntity', 'EntityManager', 'Schema']


def slugify_attr_name(name):
    return slugify(name).replace('-', '_')


class Schema(Model):
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

    class Meta:
        verbose_name, verbose_name_plural = _('attribute schema'), _('attribute schemata')
        ordering = ['title']

    def __unicode__(self):
        return u'%s (%s) %s' % (self.title, self.get_datatype_display(),
                                _('required') if self.required else '')


def get_schemata_dict(rubric=None):
    """
    Returns a dictionary of existing schemata where keys are names of attributes
    and values are schemata describing these names.

    :param rubric: if defined, only related schemata are returned.
    """
    defaults = {}
    if rubric:
        defaults.update({'rubrics': rubric})
    schemata = Schema.objects.filter(**defaults)
    return dict((s.name,s) for s in schemata)


class EntityManager(Manager):

    def _get_available_fields(self):
        "Returns names of available model fields."
        return self.model._meta.get_all_field_names()

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
        fields   = self._get_available_fields()
        schemata = get_schemata_dict()
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
                lookups = {'attrs__schema': schema, str(value_lookup): value}
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

        If rubric is not specified all existing schemata are available. If rubric
        is specified, only related schemata can be used.

        Note that we cannot create attribute with no pre-defined schema because
        we must know attribute type in order to properly put value into the DB.
        """
        fields = self._get_available_fields()
        schemata = get_schemata_dict(rubric=kwargs.get('rubric'))

        defined_static, defined_dynamic = {}, {}
        for k, v in kwargs.items():
            if k in fields:
                defined_static[k] = v
            elif k in schemata:
                defined_dynamic[k] = v
            else:
                raise NameError('Cannot create entity: unknown attribute "%s". '
                                'Available fields: (%s). Available schemata: (%s).'
                                 % (k, ', '.join(fields), ', '.join(schemata)))
        # Create the entity instance
        entity = super(ItemManager, self).create(**defined_static)

        # Create related Attr instances
        for name, value in defined_dynamic.items():
            schema = schemata[name]
            attr = Attr(item=entity, schema=schema, value=value)    # FIXME use contenttypes
            attr.save()

        return entity


class BaseEntity(Model):
    """Entity, the "E" in EAV"""

    attrs = generic.GenericRelation('Attr')    # XXX do we need this?

    objects = EntityManager()

    class Meta:
        abstract = True

    def get_lookups(self):
        return {'rubric': self.rubric}

    @cached_property
    def fields_and_eav(self):
        "Returns all fields and EAV attributes."
        # TODO: replace this method with .keys() or __iter__
        fields = self._meta.get_all_field_names()
        schemata = get_schemata_dict(self.rubric)
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
    content_type = ForeignKey(ContentType, related_name='attrs')
    object_id = IntegerField()

    content_object = generic.GenericForeignKey()

    schema = ForeignKey(Schema, related_name='attrs')
    value_text = TextField(blank=True, null=True)
    value_int = IntegerField(blank=True, null=True)
    value_date = DateField(blank=True, null=True)
    value_bool = BooleanField(blank=True)
    #added = DateTimeField(auto_now_add=True, blank=True, null=True, editable=False)
    #modified = DateTimeField(auto_now=True, blank=True, null=True, editable=False)
    #added_by = ForeignKey(User, blank=True, null=True, editable=False)
    #modified_by = ForeignKey(User, blank=True, null=True, editable=False)
    #removed = BooleanField(default=False, blank=True, null=True, editable=False)

    class Meta:
        verbose_name, verbose_name_plural = _('attribute'), _('attributes')
        #ordering = ['item', 'schema']
        unique_together = ('content_type', 'object_id', 'schema')

    def __unicode__(self):
        return u'%s: %s "%s"' % (self.content_object, self.schema.title, self.value)

    def _get_value(self):
        return getattr(self, 'value_%s' % self.schema.datatype)

    def _set_value(self, new_value):
        setattr(self, 'value_%s' % self.schema.datatype, new_value)

    value = property(_get_value, _set_value)


# xxx catch signal Attr.post_save() --> update attr.item.attribute_cache (JSONField or such)
