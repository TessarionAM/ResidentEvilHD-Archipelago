"""The example YAML (yamls/ in the repository) must match the implemented options exactly."""
import re
import unittest
from pathlib import Path

from Options import Visibility

from ..options import RE1HDOptions

YAML = Path(__file__).resolve().parents[3] / "yamls" / "Resident Evil HD Remaster.yaml"
COMMON = {"progression_balancing", "accessibility"}


@unittest.skipUnless(YAML.exists(), "example YAML not found (not in a repository checkout)")
class ExampleYamlTest(unittest.TestCase):
    def setUp(self):
        import yaml
        self.text = YAML.read_text(encoding="utf-8")
        data = yaml.safe_load(self.text)
        self.game = data["game"]
        self.opts = data[self.game]
        self.fields = RE1HDOptions.type_hints

    def test_game_and_name(self):
        self.assertEqual(self.game, "Resident Evil HD Remaster")

    def test_every_key_is_an_implemented_option(self):
        for key in self.opts:
            self.assertIn(key, self.fields, key)
            if key not in COMMON:
                self.assertNotEqual(self.fields[key].visibility, Visibility.none, f"{key} is hidden")

    def test_every_visible_option_is_listed(self):
        for name, cls in self.fields.items():
            if cls.visibility != Visibility.none and name not in COMMON and name in RE1HDOptions.__annotations__:
                self.assertIn(name, self.opts, name)

    def test_values_are_valid(self):
        for key, value in self.opts.items():
            self.fields[key].from_any(value)

    def test_documented_defaults_match(self):
        # "# Default: x" directly above "key: value"
        for m in re.finditer(r"# Default: (\S+)\n  (\w+):", self.text):
            default, key = m.groups()
            cls = self.fields[key]
            self.assertEqual(cls.from_any(default).value, cls.from_any(cls.default).value, key)
