"""
Amused - Open Source Muse S BLE Protocol Implementation
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="amused",
    version="1.0.0",
    author="nexon33 & Claude",
    description="First open-source BLE protocol for Muse S EEG. Stream brain waves, heart rate & blood oxygen without proprietary SDKs",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/nexon33/amused",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Medical Science Apps.",
        "Topic :: Scientific/Engineering :: Human Machine Interfaces",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=[
        "bleak>=0.21.0",
        "numpy>=1.20.0",
        "scipy>=1.7.0",
    ],
    extras_require={
        "viz": ["matplotlib>=3.5.0"],
        "dev": ["pytest>=7.0.0", "black", "flake8"],
    },
    entry_points={
        "console_scripts": [
            "amused=amused.cli:main",
            "amused-stream=amused.muse_exact_client:main",
            "amused-sleep=amused.muse_sleep_client:main",
            "amused-parse=amused.muse_integrated_parser:main",
        ],
    },
    keywords="muse eeg ble neuroscience biometrics ppg fnirs brain-computer-interface bci",
    project_urls={
        "Bug Reports": "https://github.com/nexon33/amused/issues",
        "Source": "https://github.com/nexon33/amused",
        "Documentation": "https://github.com/nexon33/amused/wiki",
    },
)