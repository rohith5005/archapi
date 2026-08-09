from importlib.metadata import PackageNotFoundError, version

from archapi.core import ArchAPI

try:
    __version__ = version("archapi")
except PackageNotFoundError:
    # Running from a source checkout without an installed distribution
    # (e.g. no `pip install -e .` yet) -- not an error condition.
    __version__ = "0.0.0+unknown"

__all__ = ["ArchAPI", "__version__"]
