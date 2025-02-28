#!/usr/bin/env python

from setuptools import setup

setup(name='tap-urban-airship',
      version='0.9.0',
      description='Singer.io tap for extracting data from the Urban Airship API',
      author='Stitch',
      url='http://singer.io',
      classifiers=['Programming Language :: Python :: 3 :: Only'],
      py_modules=['tap_urban_airship'],
      install_requires=[
          'singer-python==5.12.2',
          'requests==2.27.1',
          'backoff>=1.8.0'
      ],
      entry_points='''
          [console_scripts]
          tap-urban-airship=tap_urban_airship:main
      ''',
      packages=['tap_urban_airship'],
      package_data = {
          'tap_urban_airship/schemas': [
            "channels.json",
            "lists.json",
            "named_users.json",
            "segments.json",
          ],
      },
      include_package_data=True,
)
