try:
    from core.risk import *  # re-export
except ImportError:
    from .strategy import kelly_size_from_metrics
