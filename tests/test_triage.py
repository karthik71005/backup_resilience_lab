from lab.triage import classify_record, load_rules

def test_all_fault_categories():
    rules = load_rules("config/triage_rules.yaml")
    cases = [
        ("fallocate: /cache/fill: No space left on device", "storage"),
        ("lookup minio on 192.0.2.1:53: no such host", "dns"),
        ("dial tcp 172.18.0.3:9000: connect: i/o timeout", "network"),
        ("open /data/victim/finance/ledger.csv: permission denied", "permissions"),
        ("AccessDenied: Access Denied", "auth"),
        ("wrong password or no key found", "auth"),
        ("dial tcp 172.18.0.2:9000: connect: connection refused", "service"),
    ]
    for msg, cat in cases:
        r = classify_record({"message": msg, "raw": msg}, rules)
        assert r is not None, msg
        assert r["category"] == cat, f"{msg} -> {r}"

def test_unknown_fallback():
    rules = load_rules("config/triage_rules.yaml")
    r = classify_record({"message": "weird xyzzy frobnicate 12345 !!!", "raw": ""}, rules)
    # UNKNOWN matches .* so it still returns something; must be P3/unknown or a real rule
    assert r is not None
