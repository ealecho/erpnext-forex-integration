from setuptools import setup, find_packages

setup(
    name="peasforex",
    version="0.0.1",
    description="Alpha Vantage Forex Integration for ERPNext",
    author="ERP Champions",
    author_email="info@erpchampions.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=[
        "requests>=2.25.0",
        "python-dateutil>=2.8.0",
    ],
)
