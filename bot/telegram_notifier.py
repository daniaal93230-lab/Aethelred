try:
    from core.telegram_notifier import *  # re-export
except ImportError:
    def notify(msg: str):
        print(f"[TELEGRAM] {msg}")
