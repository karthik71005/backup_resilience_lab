from lab.manifest import build_manifest, sha256_file
from lab.verify import verify_restore
import json

def test_manifest_roundtrip(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    (d / "a.txt").write_text("hello")
    (d / "sub").mkdir()
    (d / "sub" / "b.txt").write_text("world")
    m = build_manifest(d)
    assert m["count"] == 2
    assert m["bytes"] > 0
    for e in m["files"]:
        assert len(e["sha256"]) == 64

def test_verify_catches_corruption(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    (d / "a.txt").write_text("clean content")
    m = build_manifest(d)
    r = tmp_path / "restore"
    r.mkdir()
    (r / "a.txt").write_text("clean content")
    ok = verify_restore(r, m)
    assert ok["success_pct"] == 100.0
    (r / "a.txt").write_text("clean contentX")  # flip
    bad = verify_restore(r, m)
    assert bad["success_pct"] < 100.0
    assert len(bad["corrupted"]) == 1
