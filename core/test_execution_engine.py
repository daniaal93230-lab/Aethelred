from core.execution_engine import ExecutionEngine

engine = ExecutionEngine()
engine.run_once(is_mock=True)
engine.close()
