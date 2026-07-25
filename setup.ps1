[project]
name = "tron-alpha"
version = "0.1.0"
description = "Local-first TRON smart-computer alpha"
requires-python = ">=3.10"

[project.scripts]
tron = "tron.__main__:main"

[tool.setuptools.packages.find]
where = ["."]
include = ["tron*"]
