"""Run setuptools."""
from setuptools import find_packages, setup

setup(
    name="apimodels",
    version="0.0.1",
    author="thesadru",
    author_email="thesadru@gmail.com",
    description="Models for modern JSON APIs.",
    url="https://github.com/thesadru/apimodel",
    packages=find_packages(exclude=["tests.*"]),
    python_requires=">=3.8",
    include_package_data=True,
    package_data={"apimodel": ["py.typed"]},
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    license="MIT",
    classifiers=[
        "Development Status :: 4 - Beta",
        "License :: OSI Approved :: MIT License",
        "Intended Audience :: Developers",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Topic :: Software Development :: Libraries",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Utilities",
        "Typing :: Typed",
    ],
)
