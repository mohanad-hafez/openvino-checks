import unittest
from ci_memory_retention import choose_deletions, compact_index


class RetentionTests(unittest.TestCase):
    def test_oldest_pruned_and_current_protected(self):
        names = [f"2026-11-07-00-00-00-{n:03d}-1.json" for n in range(301)]
        self.assertEqual(choose_deletions(names, names[-1]), [names[0]])
        self.assertEqual(choose_deletions(names, names[0]), [names[1]])

    def test_under_limit_unchanged(self):
        names = ["2026-11-07-00-00-00-000-1.json"]
        self.assertEqual(choose_deletions(names, names[0]), [])

    def test_unsafe_or_unprotected_input_rejected(self):
        with self.assertRaises(ValueError):
            choose_deletions(["../a.json"], "../a.json")
        with self.assertRaises(ValueError):
            choose_deletions([], "absent.json")

    def test_index_window_is_separate_and_protected(self):
        entries = [{"investigation_id": str(n), "timestamp": f"2026-{n:06d}"} for n in range(2001)]
        result = compact_index({"total": len(entries), "entries": entries}, "2000")
        self.assertEqual(result["total"], 2000)
        self.assertEqual(result["entries"][0]["investigation_id"], "2000")
        with self.assertRaises(ValueError):
            compact_index({"total": len(entries), "entries": entries}, "0")

    def test_wrong_totals_and_legacy_alias_rejected(self):
        with self.assertRaises(ValueError):
            compact_index({"total": 0, "entries": [{"investigation_id": "a"}]}, "a")
        with self.assertRaises(ValueError):
            compact_index({"total": 1, "entries": [{"investigation_id": "a"}], "investigations": [1]}, "a")


if __name__ == "__main__":
    unittest.main()
