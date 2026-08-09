# GitHub Quickstart

Use this guide after cloning the repository from GitHub.

## Clone

```bash
git clone https://github.com/rohith5005/archapi.git
cd archapi
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

## Test

```bash
python -m compileall archapi evaluation
python -m unittest discover -s tests -v
```

## Use from PyPI instead

```bash
python -m pip install archapi
```

```python
from archapi import ArchAPI
```
