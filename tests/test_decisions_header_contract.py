from api.contracts.decisions_header import DECISIONS_HEADER

def test_decisions_header_is_canonical():
    expected = [
        "ts","symbol","regime","strategy_name",
        "signal_side","signal_strength","signal_stop_hint","signal_ttl",
        "final_action","final_size","veto_ml","veto_risk","veto_reason","price","note",
    ]
    assert DECISIONS_HEADER == expected
