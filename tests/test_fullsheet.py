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

    def test_fullsheet_of_a_page_without_a_label_size_explains_why(self):
        svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 40"><text>{{LABEL}}</text></svg>\n'
        csv_text = "LABEL\nSample\n"
        with tempfile.TemporaryDirectory() as tmp:
            svg_path = os.path.join(tmp, "bare.svg")
            csv_path = os.path.join(tmp, "rows.csv")
            Path(svg_path).write_text(svg, encoding="utf-8")
            Path(csv_path).write_text(csv_text, encoding="utf-8")
            with self.assertRaises(ValueError) as raised:
                mailmerge.generate(svg_path, csv_path, mode="fullsheet", out_dir=tmp)
            self.assertIn("physical width and height", str(raised.exception))
            with self.assertRaises(ValueError):
                mailmerge.generate(
                    str(AVERY_SVG), str(AVERY_CSV), mode="fullsheet", out_dir=tmp,
                    name_field="not-a-column", **AVERY,
                )
            with self.assertRaises(ValueError):
                mailmerge.generate(
                    str(ROOT / "samples" / "certificate.svg"),
                    str(ROOT / "samples" / "certificate.csv"),
                    mode="grid",
                    output_path=os.path.join(tmp, "out.svg"),
                )

    def test_oversized_template_warns_instead_of_clipping(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = mailmerge.generate(
                str(ROOT / "samples" / "certificate.svg"),
                str(ROOT / "samples" / "certificate.csv"),
                mode="fullsheet",
                out_dir=tmp,
            )
            self.assertEqual(result["mode"], "fullsheet")
            self.assertTrue(result["warnings"])
            self.assertTrue(any("extends past the page" in note for note in result["warnings"]))
            self.assertTrue(Path(result["files"][0][0]).is_file())

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


def _single_label_svg(width_in, height_in):
    """A generic one-label template at a physical size. Not a tiled sheet."""
    vb_w = round(width_in * 100, 5)
    vb_h = round(height_in * 100, 5)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{width_in}in" height="{height_in}in" viewBox="0 0 {vb_w} {vb_h}">\n'
        '  <defs><linearGradient id="fade"><stop offset="0" stop-color="#eeeeee"/></linearGradient></defs>\n'
        f'  <rect width="{vb_w}" height="{vb_h}" fill="url(#fade)"/>\n'
        '  <use xlink:href="#fade"/>\n'
        '  <text x="4" y="12">{{LABEL}}</text>\n'
        '</svg>\n'
    )


def _nested_positions(svg):
    return re.findall(
        r'<g id="label-\d+" transform="translate\(([^,]+),([^)]+)\) scale\(([^,]+),([^)]+)\)"',
        svg,
    )


def _cell_xy(sheet, col, row):
    x = (sheet["marginLeftIn"] + col * (sheet["labelWidthIn"] + sheet["gapXIn"])) * 25.4
    y = (sheet["marginTopIn"] + row * (sheet["labelHeightIn"] + sheet["gapYIn"])) * 25.4
    return mailmerge.fmt(x), mailmerge.fmt(y)


class AverySheetTests(unittest.TestCase):
    def test_every_sheet_fits_its_page(self):
        sheets = mailmerge.load_avery_sheets()
        self.assertGreaterEqual(len(sheets), 14)
        seen = set()
        for sheet in sheets:
            for number in sheet["products"]:
                self.assertNotIn(number, seen)
                seen.add(number)
                self.assertEqual(mailmerge.find_sheet(number)["id"], sheet["id"])
            width = (
                sheet["marginLeftIn"] + sheet["marginRightIn"]
                + sheet["columns"] * sheet["labelWidthIn"]
                + (sheet["columns"] - 1) * sheet["gapXIn"]
            )
            height = (
                sheet["marginTopIn"] + sheet["marginBottomIn"]
                + sheet["rows"] * sheet["labelHeightIn"]
                + (sheet["rows"] - 1) * sheet["gapYIn"]
            )
            self.assertLessEqual(
                abs(width - sheet["pageWidthIn"]) * 25.4, 0.5, sheet["id"],
            )
            self.assertLessEqual(
                abs(height - sheet["pageHeightIn"]) * 25.4, 0.5, sheet["id"],
            )
            self.assertIn(sheet["shape"], ("rect", "rounded", "round"))

    def test_single_label_positions_for_5195_5520_and_5523(self):
        csv_text = "LABEL\nSample\n"
        expected = {"5195": 60, "5520": 30, "5523": 10}
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "rows.csv")
            Path(csv_path).write_text(csv_text, encoding="utf-8")
            for number, count in expected.items():
                sheet = mailmerge.find_sheet(number)
                self.assertEqual(sheet["columns"] * sheet["rows"], count)
                svg_path = os.path.join(tmp, number + ".svg")
                Path(svg_path).write_text(
                    _single_label_svg(sheet["labelWidthIn"], sheet["labelHeightIn"]),
                    encoding="utf-8",
                )
                result = mailmerge.generate(
                    svg_path, csv_path, mode="fullsheet",
                    out_dir=os.path.join(tmp, number),
                    sheet_label_mm=mailmerge.sheet_label_mm(sheet),
                    sheet_name="Avery " + number,
                    columns=sheet["columns"], rows=sheet["rows"],
                    page_width_mm=mailmerge.sheet_page_mm(sheet)[0],
                    page_height_mm=mailmerge.sheet_page_mm(sheet)[1],
                    **mailmerge.sheet_spacing_mm(sheet),
                )
                # sheet_spacing uses gap_x as a keyword generate() accepts.
                self.assertEqual(result["grid"], (sheet["columns"], sheet["rows"]))
                self.assertEqual(result["per_page"], count)
                self.assertEqual(result["warnings"], [])
                text = Path(result["files"][0][0]).read_text(encoding="utf-8")
                placed = _nested_positions(text)
                self.assertEqual(len(placed), count, number)
                self.assertEqual((placed[0][0], placed[0][1]), _cell_xy(sheet, 0, 0), number)
                last = sheet["columns"] - 1, sheet["rows"] - 1
                self.assertEqual(
                    (placed[-1][0], placed[-1][1]),
                    _cell_xy(sheet, last[0], last[1]),
                    number,
                )
                self.assertEqual(text.count("Sample"), count)
                self.assertNotIn("{{", text)
                self.assertIn('id="fade__0"', text)
                self.assertIn('id="fade__1"', text)
                self.assertIn("url(#fade__0)", text)
                self.assertIn('xlink:href="#fade__0"', text)
                self.assertNotIn("url(#fade)", text.replace("url(#fade__", ""))

    def test_size_mismatch_does_not_scale(self):
        sheet = mailmerge.find_sheet("5520")
        csv_text = "LABEL\nSample\n"
        with tempfile.TemporaryDirectory() as tmp:
            svg_path = os.path.join(tmp, "label.svg")
            csv_path = os.path.join(tmp, "rows.csv")
            Path(svg_path).write_text(_single_label_svg(2, 1), encoding="utf-8")
            Path(csv_path).write_text(csv_text, encoding="utf-8")
            result = mailmerge.generate(
                svg_path, csv_path, mode="fullsheet", out_dir=tmp,
                sheet_label_mm=mailmerge.sheet_label_mm(sheet),
                sheet_name="Avery 5520",
                columns=sheet["columns"], rows=sheet["rows"],
                page_width_mm=mailmerge.sheet_page_mm(sheet)[0],
                page_height_mm=mailmerge.sheet_page_mm(sheet)[1],
                **mailmerge.sheet_spacing_mm(sheet),
            )
            self.assertTrue(any("was not scaled" in note for note in result["warnings"]))
            self.assertTrue(any("2.000 in" in note and "2.630 in" in note for note in result["warnings"]))
            text = Path(result["files"][0][0]).read_text(encoding="utf-8")
            placed = _nested_positions(text)
            # scale maps the template viewBox (width_in * 100) onto the
            # template's own physical size. The sheet's catalog size is the
            # pitch, not a stretch target.
            sx = float(placed[0][2])
            drawn_mm = sx * (2 * 100)
            self.assertEqual(mailmerge.fmt(drawn_mm), mailmerge.fmt(2 * 25.4))
            self.assertNotEqual(
                mailmerge.fmt(drawn_mm),
                mailmerge.fmt(sheet["labelWidthIn"] * 25.4),
            )
            self.assertEqual((placed[0][0], placed[0][1]), _cell_xy(sheet, 0, 0))
            self.assertEqual((placed[1][0], placed[1][1]), _cell_xy(sheet, 1, 0))

    def test_cli_sheet_and_list_sheets(self):
        listed = subprocess.run(
            [sys.executable, str(ROOT / "mailmerge.py"), "--list-sheets"],
            cwd=str(ROOT), capture_output=True, text=True, check=False,
        )
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn("5520", listed.stdout)
        self.assertIn("5195", listed.stdout)
        self.assertIn("5408", listed.stdout)
        self.assertIn("4×6", listed.stdout)

        unknown = subprocess.run(
            [sys.executable, str(ROOT / "mailmerge.py"), "--sheet", "9999",
             "--template", str(ROOT / "samples" / "single-label.svg"),
             "--names", str(ROOT / "samples" / "single-label.csv"),
             "--mode", "fullsheet"],
            cwd=str(ROOT), capture_output=True, text=True, check=False,
        )
        self.assertEqual(unknown.returncode, 1)
        self.assertIn("--list-sheets", unknown.stderr)

        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, str(ROOT / "mailmerge.py"),
                 "--template", str(ROOT / "samples" / "single-label.svg"),
                 "--names", str(ROOT / "samples" / "single-label.csv"),
                 "--mode", "fullsheet", "--out-dir", tmp,
                 "--preset", "5195", "--name-field", "label"],
                cwd=str(ROOT), capture_output=True, text=True, check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("4 cols x 15 rows = 60 copies per sheet", proc.stdout)
            self.assertIn("Sheet:", proc.stdout)
            self.assertEqual(proc.stderr, "")
            text = Path(next(Path(tmp).glob("*.svg"))).read_text(encoding="utf-8")
            self.assertEqual(len(_nested_positions(text)), 60)


if __name__ == "__main__":
    unittest.main()
