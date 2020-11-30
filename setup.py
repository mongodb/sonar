#!/usr/bin/env python3

from setuptools import setup, find_packages

setup(
    name="sonar",
    version="0.0.1",
    description="Sonar Docker Building Tools",
    author="Rodrigo Valin",
    author_email="rodrigo.valin@mongodb.com",
    url="https://github.com/10gen/sonar",
    packages=find_packages(),
    scripts=["sonar.py"],
)
