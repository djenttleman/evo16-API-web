"""Complete profiles, v1 gain migration, path safety and validation before hardware writes."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import presets


def channels():
    return [{"channel": ch, "gain": 20, "mute": False, "phantom": False,
             "instrument": False if ch in presets.DI_CHANNELS else None, "linked": False}
            for ch in range(1, 25)]


class PresetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = patch.object(presets, "PRESETS_DIR", Path(self.tmp.name))
        self.patch.start()

    def tearDown(self):
        self.patch.stop(); self.tmp.cleanup()

    def test_roundtrip(self):
        saved = presets.save("Sala chica", channels())
        self.assertEqual(saved, presets.load("Sala chica"))
        self.assertEqual(saved["formatVersion"], 2)
        self.assertEqual(presets.list_presets()[0]["name"], "Sala chica")
        self.assertTrue(presets.delete("Sala chica"))

    def test_names_and_symlinks(self):
        for name in ("../escape", "a/b", "..", "", "x" * 65, "import", "export", " bad; "):
            with self.subTest(name=name), self.assertRaises(presets.PresetError):
                presets.save(name, channels())
        (Path(self.tmp.name) / "enlace.json").symlink_to("outside.json")
        with self.assertRaises(presets.PresetError):
            presets.save("enlace", channels())

    def test_legacy_migration_preserves_wire_bytes_and_original_file(self):
        old = channels()
        old[0]["gain"] = 0
        old[-1]["gain"] = 58
        data = {"name": "Legado", "channels": old}
        path = Path(self.tmp.name) / "Legado.json"
        original = json.dumps(data)
        path.write_text(original)
        migrated = presets.load("Legado")
        self.assertEqual(migrated["channels"][0]["gain"], -8)
        self.assertEqual(migrated["channels"][-1]["gain"], 50)
        self.assertEqual([c["gain"] + 8 for c in migrated["channels"]], [c["gain"] for c in old])
        self.assertEqual(path.read_text(), original)
        self.assertEqual(presets.import_data(migrated)["channels"], migrated["channels"])

    def test_reject_incomplete_duplicate_bad_types_and_ranges(self):
        cases = [channels()[:2], channels() + channels()[:1]]
        for key, value in [("channel", 0), ("channel", True), ("gain", 51), ("gain", -9),
                           ("gain", float("nan")), ("phantom", "false"), ("mute", 1)]:
            bad = channels(); bad[0][key] = value; cases.append(bad)
        duplicate = channels(); duplicate[-1] = copy.deepcopy(duplicate[0]); cases.append(duplicate)
        for case in cases:
            with self.subTest(case=case[0]), self.assertRaises(presets.PresetError):
                presets.save("Malo", case)
        self.assertFalse((Path(self.tmp.name) / "Malo.json").exists())

    def test_link_conflicts_rejected_before_application(self):
        bad = channels(); bad[0]["linked"] = True
        with self.assertRaises(presets.PresetError): presets.validate_channels(bad)
        bad[1]["linked"] = True; bad[1]["gain"] = 21
        with self.assertRaises(presets.PresetError): presets.validate_channels(bad)

    def test_import_versions_and_bad_json(self):
        for value in [[], {"formatVersion": 99}, {"formatVersion": 2, "channels": channels()}, {"hello": 1}]:
            with self.assertRaises(presets.PresetError): presets.import_data(value)
        (Path(self.tmp.name) / "Roto.json").write_text("{oops")
        self.assertIn("error", presets.list_presets()[0])


if __name__ == "__main__": unittest.main()
