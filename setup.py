from setuptools import setup, find_packages
import sys

# Read requirements from requirements.txt file
with open('requirements.txt') as f:
    requirements = f.read().splitlines()

# Get the current Python version you're using
current_python_version = f"{sys.version_info.major}.{sys.version_info.minor}"

setup(
    name="nami",
    version="0.1",
    description="Nami project with TTS and vision utilities",
    author="Thomas Balaban",
    packages=find_packages(),
    # Use requirements from requirements.txt
    install_requires=requirements,
    # Set Python version requirement based on your current version
    python_requires=f">={current_python_version}",
)