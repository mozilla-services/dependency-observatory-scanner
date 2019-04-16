#!/usr/bin/env python

from setuptools import setup, find_packages

with open('requirements.txt', 'r') as fin:
    install_requires = fin.read().split('\n')

setup(
    name='github_metadata_fetcher',
    packages=find_packages(),
    package_data={'': ['README.md']},
    zip_safe=True,
    python_requires='>=3.6',
    install_requires=install_requires,
    entry_points={
        'console_scripts': [
            'fetch_github_metadata = github_metadata_fetcher.fetch_github_metadata_for_repo:main'
        ]
    },
    classifiers=[
        'Development Status :: 0 - Alpha',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ]
)
