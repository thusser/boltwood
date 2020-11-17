#!/usr/bin/env python3
from setuptools import setup, find_packages

setup(
    name='boltwood',
    version='0.1',
    description='Web interface for Boltwood II cloud sensor',
    author='Tim-Oliver Husser',
    author_email='thusser@uni-goettingen.de',
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'bw2web=boltwood.web:main'
        ]
    },
    package_data={'boltwood': ['*.html', 'static_html/*.css']},
    include_package_data=True,
    install_requires=['tornado', 'apscheduler', 'pyserial', 'numpy']
)
