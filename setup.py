from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

# Get version from __init__.py
from peasforex import __version__ as version

setup(
    name="peasforex",
    version=version,
    description="Alpha Vantage Forex Integration for ERPNext",
    author="ERP Champions",
    author_email="info@erpchampions.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
