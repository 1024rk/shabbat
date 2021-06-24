from setuptools import setup, find_packages


setup(
    name="shabbat",
    description="Pack of C-System company shared batteries for Python modules",
    version="0.0.1",
    author="1024",
    author_email="rk.hh@live.com",
    packages=find_packages(),
    install_requires=[
        'aiogram',
        'aiopg',
        'psycopg2-binary',
        'pydantic'])
