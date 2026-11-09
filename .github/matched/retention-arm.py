"""Run the two retention implementations on isolated copies of one saved tree."""
import json
import os
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
from ci_memory_retention import apply_retention, inventory

here = Path(".github/matched")
root = Path("mq")
evidence = Path("evidence")
plan = json.loads((here / "retention-input-plan.json").read_bytes())
schema = json.loads((here / "index.schema.json").read_bytes())
index_file = root / "investigations/index.json"


def inputs():
    before = inventory(root)
    assert before == plan["memory_blobs"]
    paths = sorted(name for name in before if name.startswith("investigations/") and
                   name.endswith(".json") and name != "investigations/index.json")
    data = json.loads(index_file.read_bytes())
    Draft202012Validator(schema).validate(data)
    return before, paths, data


mode = sys.argv[1]
if mode == "fixture":
    before, paths, index = inputs()
    fixture = {"inputs": {"memory": {
        "raw_record_count": len(paths), "total_persisted_files": len(before),
        "index_entries": len(index["entries"]), "index_bytes": index_file.stat().st_size,
        "protected_record": plan["protected_record"],
    }}, "output_description": "Submit JSON with integer raw_limit, boolean compact_index and boolean preserve_current."}
    (evidence / "fixture.json").write_text(json.dumps(fixture), encoding="utf-8")
elif mode == "script":
    result = apply_retention(root, plan, schema)
    (evidence / "result.json").write_text(json.dumps(result), encoding="utf-8")
elif mode == "agent":
    before, paths, index = inputs()
    calls = [json.loads(line) for line in (evidence / "tools.jsonl").read_text().splitlines()]
    assert [row["name"] for row in calls] == ["read_input", "publish_result"]
    assert all("error" not in row for row in calls)
    decision = json.loads(calls[-1]["args"]["body"])
    assert decision == {"raw_limit": 300, "compact_index": False, "preserve_current": True}
    delete = paths[:len(paths)-decision["raw_limit"]]
    assert [Path(path).name for path in delete] == plan["expected_deleted_records"]
    assert "investigations/" + plan["protected_record"] not in delete
    for path in delete:
        (root / path).unlink()
    after = inventory(root)
    assert after == {path:sha for path,sha in before.items() if path not in set(delete)}
    assert len(after) < 1000 and index_file.stat().st_size < 1048576
    (evidence / "result.json").write_text(json.dumps({"after_blobs": after}), encoding="utf-8")
else:
    raise ValueError("Unknown retention mode")
