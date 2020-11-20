#!/usr/bin/env python3

from distutils.core import setup

setup(
    name="sonar",
    version="0.0.1",
    description="Sonar Docker Building Tools",
    author="Rodrigo Valin",
    author_email="licorna@gmail.com",
    url="https://gitlab.com/licorna/sonar",
    packages=["sonar", "sonar.builders"],
)
