from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="fasta2a",
    version="0.1.0",
    author="Siddharth Ambegaonkar",
    author_email="sid.ambegaonkar@gmail.com",
    description="A Python package for implementing an A2A server",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/sambegaonkar/py-a2a",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
    install_requires=[
        # Add your dependencies here
    ],
) 