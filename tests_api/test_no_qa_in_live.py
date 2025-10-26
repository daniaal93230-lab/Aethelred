from importlib import reload


def test_no_qa_engine_when_live(monkeypatch):
    monkeypatch.setenv("LIVE", "1")
    monkeypatch.delenv("QA_DEV_ENGINE", raising=False)
    monkeypatch.delenv("QA_MODE", raising=False)
    # reload module to run startup attach logic during import-time for tests
    import api.main as main

    reload(main)
    # should not auto attach engine
    assert getattr(main.app.state, "engine", None) is None
