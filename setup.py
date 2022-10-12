from setuptools import setup, find_packages
import re
import ast

#
# Search for the __version__=1.2.3 string in __init__.py
#
_version_re = re.compile(r'__version__\s+=\s+(.*)')

with open('merge_pacs_metrics_prometheus_exporter/__init__.py', 'rb') as f:
    version = str(ast.literal_eval(_version_re.search(f.read().decode('utf-8')).group(1)))


setup(
        name='merge_pacs_metrics_prometheus_exporter',
    version=version,
    description="An application to scrape metrics data from Merge PACS servers",
    install_requires=[
        "prometheus_client",
        "pandas",
        "requests",
        "pywin32"
    ],
    packages=find_packages()
)