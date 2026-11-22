"""데이터 검증 회귀 테스트: python3 -m unittest discover -s etl."""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import validate


class ValidationTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.data = Path(directory.name)

    def run_validation(self, baseline, **modules):
        for name, value in modules.items():
            (self.data / f"{name}.json").write_text(json.dumps(value))
        with (
            patch.object(validate, "RULES", {name: [] for name in baseline}),
            patch.object(validate, "baseline", side_effect=lambda ref, name: baseline.get(name)),
            patch.object(sys, "argv", ["validate.py", "--data", str(self.data)]),
            redirect_stdout(io.StringIO()) as output,
        ):
            return validate.main(), output.getvalue()

    def test_missing_required_module(self):
        status, output = self.run_validation({"korea": {}})
        self.assertEqual(status, 1)
        self.assertIn("필수 파일 없음", output)

    def test_non_object_module(self):
        for value in (None, [], 5):
            with self.subTest(value=value):
                status, output = self.run_validation({"korea": {}}, korea=value)
                self.assertEqual(status, 1)
                self.assertIn("최상위 값은 JSON 객체", output)

    def test_birth_forecast_requires_replacement_by_observation(self):
        old = {
            "meta": {"year": 2026, "month": 11},
            "monthly": {"births": {"2026": [20000] * 11 + [None]}, "forecast": {"12": 20000}},
            "backtest": {"detail": {}, "pseudo": []},
            "sidos": [],
        }
        new = deepcopy(old)
        new["monthly"]["forecast"].clear()
        self.assertEqual(self.run_validation({"births": old}, births=new)[0], 1)
        new["meta"]["month"] = 12
        self.assertEqual(self.run_validation({"births": old}, births=new)[0], 1)
        new["monthly"]["births"]["2026"][-1] = 20200
        self.assertEqual(self.run_validation({"births": old}, births=new)[0], 0)

    def test_housing_outlook_requires_replacement_by_observation(self):
        point = {"burden": 25, "pir": 8}
        old = {
            "meta": {"currentYear": 2026},
            "regions": [{
                "id": "00", "hist": {"2026": point},
                "outlook": {"trend": {"hold": {"2027": point, "2028": point}}},
            }],
        }
        new = deepcopy(old)
        new["meta"]["currentYear"] = 2027
        region = new["regions"][0]
        del region["outlook"]["trend"]["hold"]["2027"]
        self.assertEqual(self.run_validation({"housing": old}, housing=new)[0], 1)
        region["hist"]["2027"] = point
        self.assertEqual(self.run_validation({"housing": old}, housing=new)[0], 0)
        del region["outlook"]["trend"]["hold"]["2028"]
        self.assertEqual(self.run_validation({"housing": old}, housing=new)[0], 1)

    def test_prediction_ledger_uses_a_shared_unique_key(self):
        old = {"ledger": [
            {"id": "births:2026", "key": "births:2026@08", "pred": 200000, "lo": 190000},
            {"id": "pop:2026", "key": "pop:2026@2025", "pred": 50000000},
        ]}
        new = deepcopy(old)
        new["ledger"].insert(1, {"id": "births:2026", "key": "births:2026@09", "pred": 201000})
        self.assertEqual(self.run_validation({"track": old}, track=new)[0], 0)
        new["ledger"].pop(0)
        self.assertEqual(self.run_validation({"track": old}, track=new)[0], 1)


if __name__ == "__main__":
    unittest.main()
