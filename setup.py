#!/usr/bin/env python3

import os

from fpr import NAME, SOURCE_URL, VERSION
from setuptools import setup, find_packages


__dirname = os.path.abspath(os.path.dirname(__file__))

with open(os.path.join(__dirname, "README.md")) as readme:
    README = readme.read()

with open(os.path.join(__dirname, "requirements.txt.lock")) as requirements:
    INSTALL_REQUIRES = [
        line.split(" ")[0]
        for i, line in enumerate(requirements.read().replace("\\\n", "").split("\n"))
        if line
    ]


setup(
    name=NAME,
    version=VERSION,
    description="Dependency Observatory Scanner: a scanner for software packages and dependencies",
    url=SOURCE_URL,
    long_description=README,
    long_description_content_type="text/markdown",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)",
        "Natural Language :: English",
        "Programming Language :: Python :: 3 :: Only",
        "Topic :: Security",
        "Topic :: Software Development :: Quality Assurance",
    ],
    author="Greg Guthe",
    author_email="foxsec+dependencyscan@mozilla.com",
    install_requires=INSTALL_REQUIRES,
    packages=find_packages(),
    include_package_data=True,
    zip_safe=True,
    python_requires=">=3.8",
)
