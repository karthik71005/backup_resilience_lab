from lab.faults import FAULTS

def test_fault_catalog_complete():
    for expected in ["disk_full", "dns_failure", "port_blocked", "permission_denied", "bad_credentials", "wrong_repo_password", "service_down"]:
        assert expected in FAULTS

def test_triage_rules_cover_faults():
    from lab.triage import load_rules
    rules = load_rules("config/triage_rules.yaml")
    ids = {r["id"] for r in rules}
    for need in ["STORAGE_DISK_FULL", "DNS_FAILURE", "NETWORK_PORT_BLOCKED", "PERMISSIONS", "AUTH_S3", "AUTH_REPO_PASSWORD", "SERVICE_DOWN", "UNKNOWN"]:
        assert need in ids, f"missing rule {need}"
