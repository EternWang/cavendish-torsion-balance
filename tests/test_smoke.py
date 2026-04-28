from __future__ import annotations

import csv
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CavendishSmokeTest(unittest.TestCase):
    def test_rebuilds_report_artifacts(self) -> None:
        subprocess.run(
            [sys.executable, "scripts/reproduce_report_artifacts.py"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        method_path = ROOT / "results" / "method2_summary.csv"
        systematics_path = ROOT / "results" / "systematics_table3.csv"
        tracking_path = ROOT / "figures" / "tracking_diagnostics.png"

        self.assertTrue(method_path.exists())
        self.assertTrue(systematics_path.exists())
        self.assertGreater(tracking_path.stat().st_size, 0)

        with method_path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        self.assertEqual(len(rows), 3)
        g_values = [float(row["G0_SI"]) for row in rows]
        self.assertGreater(max(g_values), 1e-10)
        self.assertGreater(min(float(row["rel_uG0_stat_pct"]) for row in rows), 0)


if __name__ == "__main__":
    unittest.main()
