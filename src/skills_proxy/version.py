"""Package version (from installed distribution metadata)."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("llama-skills")
except PackageNotFoundError:
    __version__ = "0.0.0+dev"
