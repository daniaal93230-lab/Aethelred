try:
    from core.ledger import *  # re-export
except ImportError:
    from .paper import PaperLedger
