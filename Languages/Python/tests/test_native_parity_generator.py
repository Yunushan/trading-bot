import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_ROOT = REPO_ROOT / "Languages" / "Python"
for path in (REPO_ROOT, PYTHON_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from tools import generate_native_parity_contracts as generator  # noqa: E402


class NativeParityGeneratorTests(unittest.TestCase):
    def test_indicator_reference_series_uses_stable_decimal_precision(self):
        self.assertEqual(
            [None, 1.234567890123, -2.0, 0.0],
            generator._json_series([float("nan"), 1.23456789012349, -2.0, -1e-16]),
        )

    def test_checked_in_indicator_reference_matches_the_generator(self):
        fixture = generator.RUST_INDICATOR_REFERENCE_OUTPUT.read_text(encoding="utf-8")
        self.assertEqual(generator.render_rust_indicator_reference_module(), fixture)

        payload_line = next(
            line
            for line in fixture.splitlines()
            if line.startswith("pub const PYTHON_INDICATOR_REFERENCE_JSON")
        )
        payload = payload_line.split(" = ", 1)[1].removesuffix(";")
        self.assertIn("expected", json.loads(json.loads(payload)))

        cpp_fixture = generator.CPP_INDICATOR_REFERENCE_OUTPUT.read_text(encoding="utf-8")
        self.assertEqual(generator.render_cpp_indicator_reference_header(), cpp_fixture)
        self.assertIn("kPythonSourceContractHash", cpp_fixture)
        self.assertIn("kReferenceJson", cpp_fixture)


if __name__ == "__main__":
    unittest.main()
