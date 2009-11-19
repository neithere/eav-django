# -*- coding: utf-8 -*-

from django.db.models import Manager


class EntityManager(Manager):

    def filter(self, **kw):
        """
        A wrapper around standard filter() method. Allows to construct queries
        involving both normal fields and EAV attributes without thinking about
        implementation details. Usage::

            ConcreteEntity.objects.filter(rubric=1, price=2, colour='green')

        ...where `rubric` is a ForeignKey field, and `colour` is the name of an
        EAV attribute represented by Schema and Attr models.
        """

        qs = self.all()
        for lookup, value in kw.items():

            # FIXME FIXME managed sche,a doesn't get "m2o" flag!!!

            qs = self._filter_by_lookup(qs, lookup, value)
        return qs

    def _filter_by_lookup(self, qs, lookup, value):
        fields   = self.model._meta.get_all_field_names()
        schemata = dict((s.name, s) for s in self.model.get_schemata_for_model())

        if '__' in lookup:
            name, sublookup = lookup.split('__')
        else:
            name, sublookup = lookup, None

        if name in fields:
            # ordinary model field
            return qs.filter(**{lookup: value})
        elif name in schemata:
            # EAV attribute (Attr instance linked to entity)
            schema = schemata.get(name)
            if schema.m2o:
                if sublookup:
                    raise NameError('%s is not a valid lookup: sublookups cannot '
                                    'be used with m2o attributes.' % lookup)
                return self._filter_by_m2o_schema(qs, lookup, value, schema)
            else:
                return self._filter_by_simple_schema(qs, lookup, sublookup, value, schema)
        else:
            raise NameError('Cannot filter items by attributes: unknown '
                            'attribute "%s". Available fields: %s. '
                            'Available schemata: %s.' % (name,
                            ', '.join(fields), ', '.join(schemata)))

    def _filter_by_simple_schema(self, qs, lookup, sublookup, value, schema):
        """
        Filters given entity queryset by an attribute which is linked to given
        schema and has given value in the field for schema's datatype.
        """
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
        return qs.filter(**lookups)

    def _filter_by_m2o_schema(self, qs, lookup, value, schema):
        """
        Filters given entity queryset by an attribute which is linked to given
        many-to-one schema.

        Actually it is:

        1. "management schema" (one) which can contain a list
            of choices (defined by get_choices), its value doesn't matter;
        2. "managed schema" (many) which names are like "m2o_color_blue"
            where "color" is management schema's name, and "blue"
            is one of choices. Datatype in bool.
        """

        #choices = schema.get_choice_names()    # ['green', 'red', 'blue']
        schema_model = self.model.get_schemata_for_model().model
        managed_name = get_m2o_schema_name(schema.name, value)
        try:
            managed_schema = schema_model.objects.get(name=managed_name)
        except schema_model.DoesNotExist:
            # TODO: smarter error message, i.e. how could this happen and what to do
            raise ValueError(u'Could not find managed m2o schema %s for name "%s" '
                              'and value "%s"'.encode('utf8') % (managed_name, schema.name, value))
        lookups = {
            # schema
            'attrs__schema_content_type': managed_schema.attrs.content_type,
            'attrs__schema_object_id': managed_schema.pk,
            # value
            'attrs__value_bool': True,
        }
        return qs.filter(**lookups)

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
