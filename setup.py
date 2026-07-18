"""Package setup for the assistant."""

from setuptools import setup, find_packages

setup(
    name="assistant",
    version="1.0.0",
    description="A versatile AI assistant covering system, files, network, security, "
                "programming, databases, containers, web, productivity, documents, "
                "data analysis, multimedia, finance, research, PKM, monitoring, and automation.",
    author="AI Assistant contributors",
    python_requires=">=3.10",
    py_modules=[
        "assistant",
        "api_client",
        "cli",
        "config",
        "demo",
        "main",
        "memory",
        "operational_policy",
        "tools",
    ],
    install_requires=[
        "requests>=2.31.0",
    ],
    extras_require={
        "full": [
            "psutil>=5.9",
            "pypdf>=3.0",
            "Pillow>=10.0",
        ],
        "dev": [
            "pyflakes",
            "black",
        ],
    },
    entry_points={
        "console_scripts": [
            "assistant=cli:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
