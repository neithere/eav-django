# -*- coding: utf-8 -*-
#
#    EAV-Django is a reusable Django application which implements EAV data model
#    Copyright © 2009—2010  Andrey Mikhaylenko
#
#    This file is part of EAV-Django.
#
#    EAV-Django is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as published
#    by the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    EAV-Django is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public License
#    along with EAV-Django.  If not, see <http://gnu.org/licenses/>.

__all__ = ['BaseEntityAdmin', 'BaseSchemaAdmin', 'BaseEntityStackedInline']


# django
from django.contrib.admin import helpers
from django.contrib.admin.options import (
    ModelAdmin, InlineModelAdmin, StackedInline
)
from django.forms.models import BaseInlineFormSet
from django.utils.safestring import mark_safe


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
        adminform = helpers.AdminForm(form, fieldsets,
                                      self.prepopulated_fields)
        media = mark_safe(self.media + adminform.media)

        context.update(adminform=adminform, media=media)

        super_meth = super(BaseEntityAdmin, self).render_change_form
        return super_meth(request, context, **kwargs)


class BaseSchemaAdmin(ModelAdmin):

    list_display = ('title', 'name', 'datatype', 'help_text', 'required')
    prepopulated_fields = {'name': ('title',)}


class BaseEntityInlineFormSet(BaseInlineFormSet):
    """
    An inline formset that correctly initializes EAV forms.
    """
    def add_fields(self, form, index):
        if self.instance:
            setattr(form.instance, self.fk.name, self.instance)
            form._build_dynamic_fields()
        super(BaseEntityInlineFormSet, self).add_fields(form, index)


class BaseEntityInline(InlineModelAdmin):
    """
    Inline model admin that works correctly with EAV attributes. You should mix
    in the standard StackedInline or TabularInline classes in order to define
    formset representation, e.g.::

        class ItemInline(BaseEntityInline, StackedInline):
            model = Item
            form = forms.ItemForm

    .. warning: TabularInline does *not* work out of the box. There is,
        however, a patched template `admin/edit_inline/tabular.html` bundled
        with EAV-Django. You can copy or symlink the `admin` directory to your
        templates search path (see Django documentation).

    """
    formset = BaseEntityInlineFormSet

    def get_fieldsets(self, request, obj=None):
        if self.declared_fieldsets:
            return self.declared_fieldsets

        formset = self.get_formset(request)
        fk_name = self.fk_name or formset.fk.name
        kw = {fk_name: obj} if obj else {}
        instance = self.model(**kw)
        form = formset.form(request.POST, instance=instance)

        return [(None, {'fields': form.fields.keys()})]
