# -*- coding: utf-8 -*-

# django
from django.contrib.admin import helpers, site, ModelAdmin, TabularInline
from django.utils.translation import ugettext_lazy as _
from django.utils.safestring import mark_safe

# 3rd-party
from view_shortcuts.decorators import render_to

# this app
from models import Attr, Schema
from forms import SchemaForm, BaseDynamicEntityForm


class BaseEntityAdmin(ModelAdmin):

    def render_change_form(self, request, context, **kwargs):
        """
        Wrapper for ModelAdmin.render_change_form. Replaces standard static
        AdminForm with an EAV-friendly one. The point is that our form generates
        fields dynamically and fieldsets must be inferred from a prepared and
        validated form instance, not just the form class. Django does not seem
        to provide hooks for this purpose, so we simply wrap the view and
        substitute some data.
        """
        form = context['adminform'].form

        # infer correct data from the form
        fieldsets = [(None, {'fields': form.fields.keys()})]
        adminform = helpers.AdminForm(form, fieldsets, self.prepopulated_fields)
        media = mark_safe(self.media + adminform.media)

        context.update(adminform=adminform, media=media)

        return super(BaseEntityAdmin, self).render_change_form(request, context, **kwargs)


class SchemaAdmin(ModelAdmin):
    form = SchemaForm
    list_display = ('title', 'name', 'datatype', 'help_text',
                    'required', 'filtered', 'sortable', 'rubrics')
    prepopulated_fields = {'name': ('title',)}

    def rubrics(self, instance):
        return ', '.join([u'<a href="%s">%s</a>' % (x.get_absolute_url(), x.title)
                          for x in instance.rubrics.all()])
    rubrics.allow_tags = True


site.register(Schema, SchemaAdmin)
