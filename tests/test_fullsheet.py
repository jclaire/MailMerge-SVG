"""Full-sheet-per-label layout: one sheet of identical copies per CSV row."""

import hashlib
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import mailmerge


# Bundled template.svg + names.csv at the default 2 mm gap / 0 mm margin.
GRID_BASELINE_SHA256 = "988a40e020e9cda42e14044c890855714b8b259c2e268a76a7b462c766b626a5"

AVERY_SVG = ROOT / "samples" / "avery-5520-label.svg"
AVERY_CSV = ROOT / "samples" / "avery-5520.csv"

# Avery 5520: 2.625 in x 1 in, 3 across x 10 down, on US Letter.
AVERY = dict(
    gap=0.0,
    margin=0.0,
    gap_x=3.175,
    gap_y=0.0,
    margin_top=12.7,
    margin_bottom=12.7,
    margin_left=4.7625,
    margin_right=4.7625,
)


def _translates(svg):
    return re.findall(
        r'<g id="nametag-(\d+)"[^>]*transform="translate\(([^)]+)\)"',
        svg,
    )


def _expected_translate(col, row):
    tx = 4.7625 + col * (66.675 + 3.175)
    ty = 12.7 + row * 25.4
    return f"{mailmerge.fmt(tx)},{mailmerge.fmt(ty)}"


class FullSheetTests(unittest.TestCase):
    def test_grid_output_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "output.svg")
            result = mailmerge.generate(
                str(ROOT / "template.svg"),
                str(ROOT / "names.csv"),
                output_path=out,
                mode="grid",
            )
            self.assertEqual(result["mode"], "grid")
            self.assertEqual(result["grid"], (5, 13))
            self.assertEqual(result["per_page"], 65)
            data = Path(out).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), GRID_BASELINE_SHA256)

    def test_individual_mode_still_one_file_per_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = mailmerge.generate(
                str(ROOT / "samples" / "certificate.svg"),
                str(ROOT / "samples" / "certificate.csv"),
                mode="individual",
                out_dir=tmp,
            )
            self.assertEqual(result["mode"], "individual")
            self.assertEqual(result["names"], 5)
            self.assertEqual(len(result["files"]), 5)
            for path, count in result["files"]:
                self.assertEqual(count, 1)
                text = Path(path).read_text(encoding="utf-8")
                self.assertNotIn("{{", text)
                self.assertTrue(path.endswith(".svg"))

    def test_avery_5520_full_sheet_alignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = mailmerge.generate(
                str(AVERY_SVG), str(AVERY_CSV), mode="fullsheet", out_dir=tmp,
                name_field="medication", **AVERY,
            )
            self.assertEqual(result["mode"], "fullsheet")
            self.assertEqual(result["grid"], (3, 10))
            self.assertEqual(result["per_page"], 30)
            self.assertEqual(result["names"], 4)
            self.assertEqual(len(result["files"]), 4)
            self.assertEqual(result["name_fields"], ["medication"])

            names = [os.path.basename(path) for path, _ in result["files"]]
            self.assertEqual(names, [
                "Amoxicillin-01.svg",
                "Lisinopril-02.svg",
                "Amoxicillin-03.svg",
                "Ibuprofen _ Advil-04.svg",
            ])

            first = Path(result["files"][0][0]).read_text(encoding="utf-8")
            placed = _translates(first)
            self.assertEqual(len(placed), 30)
            self.assertEqual([idx for idx, _ in placed], [str(i) for i in range(30)])
            for index, point in placed:
                col, row = int(index) % 3, int(index) // 3
                self.assertEqual(point, _expected_translate(col, row), index)
            self.assertEqual(first.count("Amoxicillin"), 30)
            self.assertEqual(first.count("500 mg"), 30)
            self.assertNotIn("Lisinopril", first)
            self.assertNotIn("{{", first)

            third = Path(result["files"][2][0]).read_text(encoding="utf-8")
            self.assertEqual(len(_translates(third)), 30)
            self.assertEqual(third.count("Amoxicillin"), 30)
            self.assertEqual(third.count("250 mg"), 30)
            self.assertNotIn("500 mg", third)

            # The same die registration as a mixed grid sheet.
            grid = mailmerge.generate(
                str(AVERY_SVG), str(AVERY_CSV), mode="grid",
                output_path=os.path.join(tmp, "mixed.svg"), **AVERY,
            )
            self.assertEqual(grid["grid"], (3, 10))
            self.assertEqual(len(grid["files"]), 1)
            mixed = Path(grid["files"][0][0]).read_text(encoding="utf-8")
            mixed_xy = _translates(mixed)
            self.assertEqual(len(mixed_xy), 4)
            self.assertEqual(mixed_xy[0][1], _translates(first)[0][1])
            self.assertIn("Amoxicillin", mixed)
            self.assertIn("Lisinopril", mixed)

    def test_blank_rows_do_not_consume_a_number(self):
        csv_text = "Medication,Dose\nAmoxicillin,500 mg\n\nLisinopril,10 mg\n"
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "rows.csv")
            Path(csv_path).write_text(csv_text, encoding="utf-8")
            result = mailmerge.generate(
                str(AVERY_SVG), csv_path, mode="fullsheet",
                out_dir=os.path.join(tmp, "out"), name_field="medication", **AVERY,
            )
            names = [os.path.basename(path) for path, count in result["files"]]
            self.assertEqual(names, ["Amoxicillin-01.svg", "Lisinopril-02.svg"])
            self.assertTrue(all(count == 30 for _, count in result["files"]))

    def test_basename_padding_and_duplicate_suffix(self):
        self.assertEqual(
            mailmerge.fullsheet_basename({"medication": "A"}, ["medication"], 0, 100),
            "A-001",
        )
        self.assertEqual(
            mailmerge.fullsheet_basename({"medication": ""}, ["medication"], 4, 5),
            "row-05",
        )
        used = set()
        self.assertEqual(mailmerge.unique_name("A-01", used), "A-01")
        self.assertEqual(mailmerge.unique_name("A-01", used), "A-01-2")

    def test_fullsheet_requires_a_tile_and_known_name_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                mailmerge.generate(
                    str(ROOT / "samples" / "certificate.svg"),
                    str(ROOT / "samples" / "certificate.csv"),
                    mode="fullsheet",
                    out_dir=tmp,
                )
            with self.assertRaises(ValueError):
                mailmerge.generate(
                    str(AVERY_SVG), str(AVERY_CSV), mode="fullsheet", out_dir=tmp,
                    name_field="not-a-column", **AVERY,
                )

    def test_cli_fullsheet(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [
                    sys.executable, str(ROOT / "mailmerge.py"),
                    "--template", str(AVERY_SVG),
                    "--names", str(AVERY_CSV),
                    "--mode", "fullsheet",
                    "--out-dir", tmp,
                    "--name-field", "medication",
                    "--margin-top", "12.7",
                    "--margin-bottom", "12.7",
                    "--margin-left", "4.7625",
                    "--margin-right", "4.7625",
                    "--gap-x", "3.175",
                    "--gap-y", "0",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("3 cols x 10 rows = 30 copies per sheet", proc.stdout)
            self.assertIn("full sheet per label", proc.stdout)
            self.assertIn("Amoxicillin-01.svg", proc.stdout)
            self.assertEqual(len(list(Path(tmp).glob("*.svg"))), 4)


if __name__ == "__main__":
    unittest.main()
