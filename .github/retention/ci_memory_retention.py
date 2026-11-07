"""Apply the CI Doctor's bounded retention phase to a frozen memory tree."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator

RECORD_LIMIT = 300
INDEX_LIMIT = 2000
FILE_LIMIT = 1000
BYTE_LIMIT = 1048576
INDEX_HEADROOM = 0.9
# Historical native records include an alphabetic discriminator after the run ID.
# Retention orders by the timestamp prefix; safe suffixes do not change that rule.
RECORD_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}-\d{3}-[A-Za-z0-9_-]+\.json$")


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def choose_deletions(names, protected, limit=RECORD_LIMIT):
    if protected not in names:
        raise ValueError("Protected investigation absent")
    if any(not RECORD_NAME.fullmatch(name) for name in names):
        raise ValueError("Unexpected investigation filename")
    candidates = sorted(name for name in names if name != protected)
    return candidates[:max(0, len(names) - limit)]


def compact_index(index, protected_id, limit=INDEX_LIMIT, byte_limit=BYTE_LIMIT):
    if index["total"] != len(index["entries"]):
        raise ValueError("Index total disagrees with entries")
    if not any(e["investigation_id"] == protected_id for e in index["entries"]):
        raise ValueError("Protected investigation missing from index")
    if index.get("investigations"):
        raise ValueError("Legacy alias needs explicit migration; do not silently prune it")
    result = dict(index)
    entries = list(index["entries"])
    if len(entries) > limit:
        entries = sorted(entries, key=lambda entry: entry["timestamp"], reverse=True)[:limit]
    result.update(entries=entries, total=len(entries))
    while len(json.dumps(result, indent=2).encode()) >= int(byte_limit * INDEX_HEADROOM):
        if len(entries) <= 1:
            raise ValueError("Index cannot fit with required headroom")
        entries = sorted(entries, key=lambda entry: entry["timestamp"], reverse=True)[:-1]
        result.update(entries=entries, total=len(entries))
    if not any(e["investigation_id"] == protected_id for e in result["entries"]):
        raise ValueError("Retention would remove protected index entry")
    return result


def inventory(root):
    result = {}
    for file in root.rglob("*"):
        if file.is_symlink():
            raise ValueError("Symlink in persisted memory")
        if file.is_file():
            result[file.relative_to(root).as_posix()] = git_blob(file.read_bytes())
    return result


def apply_retention(root, plan, schema):
    root = Path(root)
    before = inventory(root)
    if before != plan["memory_blobs"]:
        raise ValueError("Frozen input differs from captured memory tree")
    validator = Draft202012Validator(schema)
    Draft202012Validator.check_schema(schema)
    index_path = root / "investigations" / "index.json"
    index_bytes = index_path.read_bytes()
    index = json.loads(index_bytes)
    validator.validate(index)
    protected = plan["protected_record"]
    records = sorted(Path(p).name for p in before if p.startswith("investigations/") and p.endswith(".json") and p != "investigations/index.json")
    remove = choose_deletions(records, protected)
    if remove != plan["expected_deleted_records"]:
        raise ValueError("Deletion set differs from frozen independent expectation")
    compacted = compact_index(index, protected.removesuffix(".json"))
    validator.validate(compacted)
    next_index = index_bytes if compacted == index else (json.dumps(compacted, indent=2) + "\n").encode()
    after_paths = set(before) - {"investigations/" + name for name in remove}
    if len(after_paths) >= FILE_LIMIT or len(next_index) >= BYTE_LIMIT:
        raise ValueError("Persisted memory exceeds source limits")
    # All validation and expected-set checks precede the first workspace mutation.
    for name in remove:
        file = root / "investigations" / name
        if file.parent.resolve() != (root / "investigations").resolve():
            raise ValueError("Deletion outside investigation directory")
        file.unlink()
    if next_index != index_bytes:
        index_path.write_bytes(next_index)
    after = inventory(root)
    expected = {p: sha for p, sha in before.items() if p in after_paths}
    expected["investigations/index.json"] = git_blob(next_index)
    if after != expected:
        raise ValueError("Unexpected persisted-memory change")
    return {
        "schema": 1, "source_memory_commit": plan["source_memory_commit"],
        "before_files": len(before), "after_files": len(after),
        "before_records": len(records), "after_records": len(records) - len(remove),
        "deleted_records": remove, "index_before_entries": len(index["entries"]),
        "index_after_entries": len(compacted["entries"]),
        "index_unchanged": next_index == index_bytes,
        "patterns_unchanged": all(after[p] == sha for p, sha in before.items() if p.startswith("patterns/")),
        "protected_record": protected, "before_blobs": before, "after_blobs": after,
        "scope": "Retention phase only, on captured real memory; no new investigation or model inference",
        "model_calls": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="mq")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--schema", required=True)
    args = parser.parse_args()
    result = apply_retention(args.root, json.loads(Path(args.plan).read_text()), json.loads(Path(args.schema).read_text()))
    Path("retention-result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ["before_records", "after_records", "patterns_unchanged", "index_unchanged"]}))
