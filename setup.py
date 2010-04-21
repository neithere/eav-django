#!/usr/bin/env python
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


import os
from setuptools import setup


readme = open(os.path.join(os.path.dirname(__file__), 'README')).read()

setup(
    # overview
    name     = 'eav-django',
    description  = ('a reusable Django application which implements the '
                    'Entity-Attribute-Value data model.'),
    long_description = readme,

    # technical info
    version  = '1.1.0',
    packages = ['eav'],
    requires = ['python (>= 2.5)', 'django (>= 1.1)',
                'django_autoslug (>= 1.3.9)'],
    provides = ['eav'],

    # copyright
    author       = 'Andrey Mikhaylenko',
    author_email = 'andy@neithere.net',
    license      = 'GNU Lesser General Public License (LGPL), Version 3',

    # more info
    url          = 'http://bitbucket.org/neithere/eav-django/',
    download_url = 'http://bitbucket.org/neithere/eav-django/get/tip.zip',

    # categorization
    keywords     = 'django eav flexible data model object entity attribute value',
    classifiers  = [
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)',
        'Programming Language :: Python',
        'Topic :: Database',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Text Processing :: General',
    ],
)
