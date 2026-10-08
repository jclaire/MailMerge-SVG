/* Avery sheet library for MailMerge-SVG.
   Units are inches. mailmerge.py reads the JSON array in this file.
   The browser loads it with a script tag, so opening index.html from a
   folder still works. If this file is missing, the sheet list is empty and
   margins stay manual.

   Geometry was measured from Avery's blank-template PDFs
   (https://www.avery.com/templates/<product>) on 2026-10-08. US Letter is
   8.5 by 11 inches unless pageWidthIn and pageHeightIn say otherwise.
   Each object's source field names that template. A layout is kept when
   the margins, label size, columns or rows, and gaps add up to the page
   on both axes within 0.5 mm.

   To add a format, append an object to the array. Give it a unique id,
   every product number that should select it, and the fields the other
   entries use. Then run: python -m unittest tests.test_fullsheet
*/
var AVERY_SHEETS = [
  {
    "id": "5160",
    "products": [
      "5160",
      "5260",
      "5520",
      "8160",
      "8460"
    ],
    "name": "Address labels",
    "sizeLabel": "2-5/8\" × 1\"",
    "description": "Address labels, 30 per sheet. Same layout for 5160, 5260, 5520, 8160 and 8460.",
    "pageWidthIn": 8.5,
    "pageHeightIn": 11,
    "labelWidthIn": 2.63,
    "labelHeightIn": 1,
    "columns": 3,
    "rows": 10,
    "marginTopIn": 0.5,
    "marginRightIn": 0.1825,
    "marginBottomIn": 0.5,
    "marginLeftIn": 0.1875,
    "gapXIn": 0.12,
    "gapYIn": 0,
    "shape": "rounded",
    "source": "Avery blank-template PDF for 5160 and 5520 (identical files from avery.com/templates/5160 and /5520), measured 2026-10-08. Outline is 189.36 pt (2.63 in) wide by 72 pt tall; left 13.5 pt, horizontal pitch 198 pt, top and bottom 36 pt. Marketed size is 2-5/8 in × 1 in."
  },
  {
    "id": "5161",
    "products": [
      "5161"
    ],
    "name": "Address labels",
    "sizeLabel": "4\" × 1\"",
    "description": "Wide address labels, 20 per sheet.",
    "pageWidthIn": 8.5,
    "pageHeightIn": 11,
    "labelWidthIn": 4,
    "labelHeightIn": 1,
    "columns": 2,
    "rows": 10,
    "marginTopIn": 0.5,
    "marginRightIn": 0.145139,
    "marginBottomIn": 0.5,
    "marginLeftIn": 0.166667,
    "gapXIn": 0.188194,
    "gapYIn": 0,
    "shape": "rounded",
    "source": "Avery blank-template PDF from avery.com/templates/5161, measured 2026-10-08. Labels 288×72 pt; left 12 pt, right 10.45 pt, horizontal pitch 301.55 pt; top and bottom 36 pt."
  },
  {
    "id": "5162",
    "products": [
      "5162"
    ],
    "name": "Address labels",
    "sizeLabel": "4\" × 1-1/3\"",
    "description": "Wide address labels, 14 per sheet.",
    "pageWidthIn": 8.5,
    "pageHeightIn": 11,
    "labelWidthIn": 4,
    "labelHeightIn": 1.333333,
    "columns": 2,
    "rows": 7,
    "marginTopIn": 0.833333,
    "marginRightIn": 0.156944,
    "marginBottomIn": 0.833333,
    "marginLeftIn": 0.155556,
    "gapXIn": 0.1875,
    "gapYIn": 0,
    "shape": "rounded",
    "source": "Avery blank-template PDF from avery.com/templates/5162, measured 2026-10-08. Labels 288×96 pt; left 11.2 pt, right 11.3 pt, horizontal pitch 301.5 pt; vertical pitch 96 pt with the leftover split evenly (60 pt top and bottom)."
  },
  {
    "id": "5163",
    "products": [
      "5163",
      "5523"
    ],
    "name": "Shipping labels",
    "sizeLabel": "4\" × 2\"",
    "description": "Shipping labels, 10 per sheet. 5163 and 5523 are the same layout.",
    "pageWidthIn": 8.5,
    "pageHeightIn": 11,
    "labelWidthIn": 4,
    "labelHeightIn": 2,
    "columns": 2,
    "rows": 5,
    "marginTopIn": 0.5,
    "marginRightIn": 0.15625,
    "marginBottomIn": 0.5,
    "marginLeftIn": 0.155556,
    "gapXIn": 0.188194,
    "gapYIn": 0,
    "shape": "rounded",
    "source": "Avery blank-template PDFs for 5163 and 5523 (identical files from avery.com/templates/5163 and /5523), measured 2026-10-08. Labels 288×144 pt; left 11.2 pt, right 11.25 pt, horizontal pitch 301.55 pt; top and bottom 36 pt."
  },
  {
    "id": "5164",
    "products": [
      "5164"
    ],
    "name": "Shipping labels",
    "sizeLabel": "4\" × 3-1/3\"",
    "description": "Large shipping labels, 6 per sheet.",
    "pageWidthIn": 8.5,
    "pageHeightIn": 11,
    "labelWidthIn": 4,
    "labelHeightIn": 3.333333,
    "columns": 2,
    "rows": 3,
    "marginTopIn": 0.5,
    "marginRightIn": 0.15625,
    "marginBottomIn": 0.5,
    "marginLeftIn": 0.155556,
    "gapXIn": 0.188194,
    "gapYIn": 0,
    "shape": "rounded",
    "source": "Avery blank-template PDF from avery.com/templates/5164, measured 2026-10-08. Labels 288×240 pt; same horizontal pitch as 5163 (left 11.2 pt, right 11.25 pt, pitch 301.55 pt); top and bottom 36 pt. The PDF's first vertical step is 0.05 pt short of 240 pt."
  },
  {
    "id": "5167",
    "products": [
      "5167"
    ],
    "name": "Return address labels",
    "sizeLabel": "1-3/4\" × 1/2\"",
    "description": "Return address labels, 80 per sheet.",
    "pageWidthIn": 8.5,
    "pageHeightIn": 11,
    "labelWidthIn": 1.75,
    "labelHeightIn": 0.5,
    "columns": 4,
    "rows": 20,
    "marginTopIn": 0.5,
    "marginRightIn": 0.3,
    "marginBottomIn": 0.5,
    "marginLeftIn": 0.3,
    "gapXIn": 0.3,
    "gapYIn": 0,
    "shape": "rounded",
    "source": "Avery blank-template PDF from avery.com/templates/5167, measured 2026-10-08. Labels 126×36 pt; side margins and horizontal gap 21.6 pt (0.3 in); horizontal pitch 147.6 pt; top and bottom 36 pt."
  },
  {
    "id": "5195",
    "products": [
      "5195"
    ],
    "name": "Return address labels",
    "sizeLabel": "1-3/4\" × 0.66\"",
    "description": "Return address labels, 60 per sheet.",
    "pageWidthIn": 8.5,
    "pageHeightIn": 11,
    "labelWidthIn": 1.75,
    "labelHeightIn": 0.66,
    "columns": 4,
    "rows": 15,
    "marginTopIn": 0.55,
    "marginRightIn": 0.3,
    "marginBottomIn": 0.55,
    "marginLeftIn": 0.3,
    "gapXIn": 0.3,
    "gapYIn": 0,
    "shape": "rounded",
    "source": "Avery blank-template PDF from avery.com/templates/5195, measured 2026-10-08. Labels 126×47.52 pt (1.75 in × 0.66 in); side margins and horizontal gap 21.6 pt (0.3 in); horizontal pitch 147.6 pt; top and bottom 0.55 in. Rows are flush."
  },
  {
    "id": "5266",
    "products": [
      "5266",
      "8366"
    ],
    "name": "File folder labels",
    "sizeLabel": "3-7/16\" × 2/3\"",
    "description": "File folder labels, 30 per sheet. 5266 and 8366 share this die.",
    "pageWidthIn": 8.5,
    "pageHeightIn": 11,
    "labelWidthIn": 3.4375,
    "labelHeightIn": 0.666667,
    "columns": 2,
    "rows": 15,
    "marginTopIn": 0.5,
    "marginRightIn": 0.53125,
    "marginBottomIn": 0.5,
    "marginLeftIn": 0.53125,
    "gapXIn": 0.5625,
    "gapYIn": 0,
    "shape": "rounded",
    "source": "Avery blank-template PDFs from avery.com/templates/5266 and /8366, measured 2026-10-08. Both are 2 × 15 with horizontal pitch 288 pt. The drawn outline is 247.535×47.952 pt, within 0.02 mm of 3-7/16 in × 2/3 in; side margins stored as 0.53125 in so the pitch lands on the page."
  },
  {
    "id": "5294",
    "products": [
      "5294"
    ],
    "name": "Round labels",
    "sizeLabel": "2-1/2\" round",
    "description": "Round labels, 2-1/2 in diameter, 12 per sheet.",
    "pageWidthIn": 8.5,
    "pageHeightIn": 11,
    "labelWidthIn": 2.5,
    "labelHeightIn": 2.5,
    "columns": 3,
    "rows": 4,
    "marginTopIn": 0.4375,
    "marginRightIn": 0.25,
    "marginBottomIn": 0.46875,
    "marginLeftIn": 0.25,
    "gapXIn": 0.25,
    "gapYIn": 0.03125,
    "shape": "round",
    "source": "Avery blank-template PDF from avery.com/templates/5294, measured 2026-10-08. Circles are 180 pt across; horizontal pitch 198 pt with 18 pt side margins; vertical pitch 182.25 pt, top 31.5 pt, bottom 33.75 pt."
  },
  {
    "id": "6450",
    "products": [
      "6450",
      "94066"
    ],
    "name": "Round labels",
    "sizeLabel": "1\" round",
    "description": "Round labels, 1 in diameter, 63 per sheet. Avery lists Presta 94066 on the same template.",
    "pageWidthIn": 8.5,
    "pageHeightIn": 11,
    "labelWidthIn": 1,
    "labelHeightIn": 1,
    "columns": 7,
    "rows": 9,
    "marginTopIn": 0.5,
    "marginRightIn": 0.5,
    "marginBottomIn": 0.5,
    "marginLeftIn": 0.5,
    "gapXIn": 0.083333,
    "gapYIn": 0.125,
    "shape": "round",
    "source": "Avery blank-template PDF U-0514-01 from avery.com/templates/6450, measured 2026-10-08. 7 × 9 circles of 72 pt. Vertical pitch 81 pt. Horizontal pitch is 78 pt (the PDF's first step is 77.95 pt, 0.05 pt short). Half-inch margins. 5408 is a different product (3/4 in rounds on a 4×6 in sheet) and is listed separately."
  },
  {
    "id": "5408",
    "products": [
      "5408"
    ],
    "name": "Round labels",
    "sizeLabel": "3/4\" round",
    "description": "Round labels, 3/4 in diameter, 24 per 4 × 6 in sheet (not US Letter).",
    "pageWidthIn": 4,
    "pageHeightIn": 6,
    "labelWidthIn": 0.75,
    "labelHeightIn": 0.75,
    "columns": 4,
    "rows": 6,
    "marginTopIn": 0.59375,
    "marginRightIn": 0.3125,
    "marginBottomIn": 0.59375,
    "marginLeftIn": 0.3125,
    "gapXIn": 0.125,
    "gapYIn": 0.0625,
    "shape": "round",
    "source": "Avery blank-template PDF from avery.com/templates/5408, measured 2026-10-08. Page MediaBox is 288×432 pt (4 × 6 in). Stroked circles are 54 pt (3/4 in); centers step 63 pt across and 58.5 pt down. The clipping path is a larger 1 in circle and is not the die."
  },
  {
    "id": "22805",
    "products": [
      "22805"
    ],
    "name": "Square labels",
    "sizeLabel": "1-1/2\" × 1-1/2\"",
    "description": "Square labels, 24 per sheet.",
    "pageWidthIn": 8.5,
    "pageHeightIn": 11,
    "labelWidthIn": 1.5,
    "labelHeightIn": 1.5,
    "columns": 4,
    "rows": 6,
    "marginTopIn": 0.5,
    "marginRightIn": 0.780556,
    "marginBottomIn": 0.5,
    "marginLeftIn": 0.779861,
    "gapXIn": 0.313194,
    "gapYIn": 0.2,
    "shape": "rect",
    "source": "Avery blank-template PDF from avery.com/templates/22805, measured 2026-10-08. Rectangles are 108 pt square; left 56.15 pt, right 56.2 pt, horizontal pitch 130.55 pt; vertical pitch 122.4 pt; top and bottom 36 pt. Corners are square."
  },
  {
    "id": "5126",
    "products": [
      "5126"
    ],
    "name": "Half-sheet labels",
    "sizeLabel": "8-1/2\" × 5-1/2\"",
    "description": "Half-sheet shipping labels, 2 per sheet.",
    "pageWidthIn": 8.5,
    "pageHeightIn": 11,
    "labelWidthIn": 8.5,
    "labelHeightIn": 5.5,
    "columns": 1,
    "rows": 2,
    "marginTopIn": 0,
    "marginRightIn": 0,
    "marginBottomIn": 0,
    "marginLeftIn": 0,
    "gapXIn": 0,
    "gapYIn": 0,
    "shape": "rect",
    "source": "Avery template 5126 is the 5-1/2 × 8-1/2 in, 2-per-sheet layout (avery.com/templates/5126). The blank PDF is a US Letter page with no drawn die; the two labels are 8.5 in wide by 5.5 in tall, stacked, with no margin or gap."
  },
  {
    "id": "5165",
    "products": [
      "5165"
    ],
    "name": "Full-sheet label",
    "sizeLabel": "8-1/2\" × 11\"",
    "description": "One label covering the whole sheet.",
    "pageWidthIn": 8.5,
    "pageHeightIn": 11,
    "labelWidthIn": 8.5,
    "labelHeightIn": 11,
    "columns": 1,
    "rows": 1,
    "marginTopIn": 0,
    "marginRightIn": 0,
    "marginBottomIn": 0,
    "marginLeftIn": 0,
    "gapXIn": 0,
    "gapYIn": 0,
    "shape": "rect",
    "source": "Avery blank-template PDF from avery.com/templates/5165, measured 2026-10-08. One rectangle, MediaBox 612×792 pt, no margin."
  }
];
