"""DeepSeek web search and page fetching.

This package is intentionally independent of the video download spiders in
``core/``. It is exposed through the separate ``/research`` web page.
"""

from .client import DeepSeekClient
from .config import DeepSeekConfig, load_config
from .errors import ResearchConfigError, ResearchError, ResearchValidationError

__all__ = [
    "DeepSeekClient",
    "DeepSeekConfig",
    "load_config",
    "ResearchConfigError",
    "ResearchError",
    "ResearchValidationError",
]
