import argparse
import sys
from utils.logger import get_logger
from utils.config import Settings
from core.engine import ExecutionEngine
from exchange.paper import PaperBroker

try:
    from exchange.mexc import MexcBroker  # will be added in a later patch
except Exception:
    MexcBroker = None  # placeholder keeps imports working during cleanup

log = get_logger("runner")


def build_broker(mode: str):
    if mode == "paper":
        return PaperBroker()
    if mode == "live":
        if MexcBroker is None:
            raise RuntimeError("MexcBroker not available yet. Implement exchange/mexc.py")
        return MexcBroker()
    raise ValueError(f"Unknown mode: {mode}")


def main(mode: str | None = None):
    parser = argparse.ArgumentParser(description="Aethelred unified runner")
    parser.add_argument("--mode", choices=["paper", "live"], default=mode or "paper")
    parser.add_argument(
        "--safe-start", action="store_true", help="Flatten on start if breaker active or when requested"
    )
    args = parser.parse_args([] if mode else None)

    settings = Settings.load()
    broker = build_broker(args.mode)
    engine = ExecutionEngine(broker=broker, settings=settings)

    if args.safe_start or settings.SAFE_START:
        log.warning("Safe-start requested. Engine will flatten before trading.")
        engine.flatten_all()

    try:
        engine.run_forever()
    except KeyboardInterrupt:
        log.info("Interrupted by user, attempting graceful shutdown...")
        engine.shutdown()
    except Exception as e:
        log.exception("Fatal error in engine: %s", e)
        # optional: engine.flatten_all() here or rely on an external watchdog to call /flatten
        sys.exit(1)


if __name__ == "__main__":
    main()
