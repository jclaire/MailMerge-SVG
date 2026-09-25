"""SVG mail merge with two output layouts.

Performs a "mail merge" of rows from a CSV onto an SVG template whose artwork
contains ``{{TOKEN}}`` placeholders. Every distinct token is auto-detected and
matched to a CSV column of the same name (case-insensitive, any order), so a
template declares the fields it needs and any matching CSV merges in.

Two output modes:

- ``grid`` -- the template carries a single repeating tile (a ``<g>`` labelled
  ``Nametag``/``Tile``/``Cell`` containing a ``... Border`` cut shape). The tile
  is copied once per row and tiled into a grid sized to fit a laser bed
  (e.g. a Glowforge Pro, 19.5in x 11in) with a small gap between cuts. The gap
  can differ horizontally and vertically, and the page margin can differ on
  each side, so a sheet can register to an asymmetric die-cut layout. Ideal for
  nametags, labels and other many-up cut sheets.
- ``individual`` -- the whole template page is one document (a certificate,
  diploma, badge, ...). One output SVG is written per CSV row.

``auto`` (the default) picks ``grid`` when the template has a recognised tile
group, otherwise ``individual``.

Design goals:
- Keep the template SVG as intact as possible. Artwork is copied verbatim from
  the template (the raw XML is sliced out as text rather than re-serialized), so
  fonts, logos, embedded images and cut borders are preserved byte-for-byte.
  The only changes are the substituted values and, in grid mode, made-unique
  element ids plus a wrapping ``translate()`` group per copy.
- No third-party dependencies -- standard library only.
"""

import argparse
import csv
import os
import re
import sys


# --- placeholder / label configuration -------------------------------------

# Placeholders look like ``{{NAME}}`` / ``{{First Name}}``. Every distinct token
# found in the template is matched to a CSV column of the same name, so a
# template defines which fields it needs and any matching CSV merges into it.
PLACEHOLDER_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")

# Grid mode looks for a single repeating tile group carrying one of these
# Inkscape labels; its cut outline is labelled "Border" (or the tile label
# followed by " Border", e.g. "Nametag Border").
TILE_LABELS = ("Nametag", "Tile", "Cell")

MM_PER_INCH = 25.4

# Conversion of CSS/SVG absolute length units to millimetres. ``None`` marks
# units that have no fixed physical size (``%`` or unitless user units).
UNIT_TO_MM = {
    "": None,
    "mm": 1.0,
    "cm": 10.0,
    "q": 0.25,
    "in": 25.4,
    "pt": 25.4 / 72.0,
    "pc": 25.4 / 6.0,
    "px": 25.4 / 96.0,
    "%": None,
}

_LENGTH = re.compile(r"^\s*([+-]?[0-9]*\.?[0-9]+)\s*([a-z%]*)\s*$", re.IGNORECASE)


def parse_length(value):
    """Split an SVG length like ``19.5in`` into (number, unit). Returns
    (None, None) when the value is missing or unparseable."""
    m = _LENGTH.match(value or "")
    if not m:
        return None, None
    return float(m.group(1)), m.group(2).lower()


def fmt(value):
    """Format a float compactly (trim trailing zeros) for SVG attributes."""
    return f"{value:.5f}".rstrip("0").rstrip(".")


def xml_escape_text(text):
    """Escape a string for use as XML text content."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# --- template parsing -------------------------------------------------------

_G_TOKEN = re.compile(r"<g(?=[\s>])|</g>")
_ID_ATTR = re.compile(r'(?<=\s)id="([^"]*)"')


def find_labeled_group(svg_text, label):
    """Return (start, end) char offsets of the <g> whose opening tag carries
    ``inkscape:label="<label>"``, spanning the full element including nested
    groups. Raises ValueError if not found."""
    needle = f'inkscape:label="{label}"'
    label_pos = svg_text.find(needle)
    if label_pos == -1:
        raise ValueError(f'Could not find a <g> with inkscape:label="{label}" in the template.')

    # The label is an attribute of an opening tag; walk back to that tag's '<'.
    start = svg_text.rfind("<", 0, label_pos)
    if start == -1 or svg_text[start:start + 2] != "<g":
        raise ValueError(f'Malformed template: label "{label}" is not on a <g> element.')

    # Walk forward, tracking <g> nesting depth, to find the matching </g>.
    depth = 0
    pos = start
    while True:
        m = _G_TOKEN.search(svg_text, pos)
        if m is None:
            raise ValueError(f'Unbalanced <g> tags while extracting "{label}".')
        token = m.group()
        if token == "</g>":
            depth -= 1
            pos = m.end()
            if depth == 0:
                return start, pos
        else:  # an opening "<g"
            gt = svg_text.find(">", m.end())
            if gt == -1:
                raise ValueError("Malformed template: unterminated <g> tag.")
            self_closing = svg_text[gt - 1] == "/"
            if not self_closing:
                depth += 1
            pos = gt + 1


def find_tile_group(svg_text):
    """Find the first recognised repeating-tile group.

    Returns ``(start, end, label)`` for the ``<g>`` whose ``inkscape:label`` is
    one of ``TILE_LABELS``, or ``None`` when the template has no tile group (in
    which case the template is treated as a single per-record document)."""
    for label in TILE_LABELS:
        if f'inkscape:label="{label}"' in svg_text:
            try:
                start, end = find_labeled_group(svg_text, label)
            except ValueError:
                continue
            return start, end, label
    return None


def get_attr(tag_text, name):
    """Read a single attribute value out of an element's opening-tag text."""
    m = re.search(rf'{re.escape(name)}="([^"]*)"', tag_text)
    return m.group(1) if m else None


def parse_page(svg_text):
    """Inspect the root <svg> element.

    Returns ``(width_uu, height_uu, uu_per_mm)`` where the page size is given in
    the template's own user units (its viewBox), and ``uu_per_mm`` is how many of
    those user units make up one millimetre -- derived from the declared
    ``width``/``height`` so that physical spacing is honoured no matter what
    units or dimensions the template uses. ``uu_per_mm`` is ``None`` when the
    template gives no absolute physical size (then spacing falls back to being
    interpreted directly in user units)."""
    svg_start = svg_text.find("<svg")
    svg_open_end = svg_text.find(">", svg_start)
    svg_tag = svg_text[svg_start:svg_open_end]

    view_box = get_attr(svg_tag, "viewBox")
    if not view_box:
        raise ValueError("Template <svg> has no viewBox; cannot determine page size.")
    parts = view_box.replace(",", " ").split()
    if len(parts) != 4:
        raise ValueError(f"Unexpected viewBox value: {view_box!r}")
    vb_w, vb_h = float(parts[2]), float(parts[3])

    uu_per_mm = _scale_from_dimension(get_attr(svg_tag, "width"), vb_w)
    if uu_per_mm is None:
        uu_per_mm = _scale_from_dimension(get_attr(svg_tag, "height"), vb_h)

    return vb_w, vb_h, uu_per_mm


def _scale_from_dimension(dim_value, viewbox_extent):
    """User units per millimetre implied by a physical width/height attribute
    paired with the matching viewBox extent. Returns ``None`` if it can't be
    determined (missing, percentage, or unitless)."""
    value, unit = parse_length(dim_value)
    if value is None or not viewbox_extent:
        return None
    mm_per_unit = UNIT_TO_MM.get(unit)
    if mm_per_unit is None:
        return None
    physical_mm = value * mm_per_unit
    if physical_mm <= 0:
        return None
    return viewbox_extent / physical_mm


def parse_tag_geometry(nametag_xml, border_labels):
    """Return (width, height, stroke) of the border element, in the template's
    user units (the same space as the viewBox and transforms).

    ``border_labels`` is a label or list of candidate labels tried in order, so
    the cut outline can be labelled either ``<Tile> Border`` (e.g.
    ``Nametag Border``) or simply ``Border``.

    The border may be any of ``rect``, ``circle``, ``ellipse``, ``polygon`` or
    ``polyline``, so tiles can be any shape; the width/height returned are the
    shape's bounding box, which is what the grid tiles on."""
    if isinstance(border_labels, str):
        border_labels = [border_labels]
    border_pos = -1
    border_label = border_labels[0]
    for cand in border_labels:
        pos = nametag_xml.find(f'inkscape:label="{cand}"')
        if pos != -1:
            border_pos, border_label = pos, cand
            break
    if border_pos == -1:
        shown = " or ".join(f'"{lbl}"' for lbl in border_labels)
        raise ValueError(
            f"Could not find a border element with inkscape:label {shown} "
            "in the tile group."
        )
    el_start = nametag_xml.rfind("<", 0, border_pos)
    el_end = nametag_xml.find(">", border_pos)
    if el_start == -1 or el_end == -1:
        raise ValueError(f'Malformed "{border_label}" element in the template.')
    el = nametag_xml[el_start:el_end + 1]

    name_match = re.match(r"<\s*([A-Za-z0-9:]+)", el)
    tag_name = name_match.group(1).split(":")[-1].lower() if name_match else ""

    width, height = _shape_bbox(tag_name, el)
    if width is None or height is None:
        raise ValueError(
            f'Could not determine the size of the "{border_label}" '
            f"<{tag_name or '?'}> element."
        )

    stroke = 0.0
    style = get_attr(el, "style") or ""
    m = re.search(r"stroke-width:\s*([0-9.]+)", style)
    if m:
        stroke = float(m.group(1))
    elif get_attr(el, "stroke-width"):
        try:
            stroke = float(get_attr(el, "stroke-width"))
        except ValueError:
            stroke = 0.0
    return float(width), float(height), stroke


def _shape_bbox(tag_name, el):
    """Bounding-box (width, height) for a supported border shape, or (None, None)."""
    def num(attr):
        try:
            return float(get_attr(el, attr))
        except (TypeError, ValueError):
            return None

    if tag_name == "rect":
        return num("width"), num("height")
    if tag_name == "circle":
        r = num("r")
        return (2 * r, 2 * r) if r is not None else (None, None)
    if tag_name == "ellipse":
        rx, ry = num("rx"), num("ry")
        return (2 * rx, 2 * ry) if rx is not None and ry is not None else (None, None)
    if tag_name in ("polygon", "polyline"):
        points = get_attr(el, "points") or ""
        coords = [float(v) for v in re.findall(r"[-+]?[0-9]*\.?[0-9]+", points)]
        xs, ys = coords[0::2], coords[1::2]
        if xs and ys:
            return max(xs) - min(xs), max(ys) - min(ys)
    return None, None


# --- grid layout ------------------------------------------------------------

# User units. Keeps an exact die-cut fit (pitch * n + margins == page) from
# rounding down to one fewer row or column. Far smaller than a print dot.
_FIT_EPS = 1e-4


def _pick_spacing(specific, fallback):
    """Use ``specific`` when it was provided, otherwise the shared fallback.

    ``0`` is a real value (a flush gutter or a flush edge). Only ``None`` means
    "not set"."""
    return fallback if specific is None else specific


def resolve_grid_spacing(gap, margin, gap_x=None, gap_y=None,
                         margin_top=None, margin_right=None,
                         margin_bottom=None, margin_left=None):
    """Resolve per-axis gaps and per-side margins.

    ``gap`` applies to both axes unless ``gap_x`` or ``gap_y`` is set.
    ``margin`` applies to every side unless that side is set. All six numbers
    are in the same unit (millimetres at the CLI; user units in the layout).
    """
    return {
        "gap_x": _pick_spacing(gap_x, gap),
        "gap_y": _pick_spacing(gap_y, gap),
        "margin_top": _pick_spacing(margin_top, margin),
        "margin_right": _pick_spacing(margin_right, margin),
        "margin_bottom": _pick_spacing(margin_bottom, margin),
        "margin_left": _pick_spacing(margin_left, margin),
    }


def _slots(avail, size, pitch):
    """How many tiles of ``size`` fit in ``avail`` stepped by ``pitch``."""
    if pitch <= 0:
        return 1 if avail + _FIT_EPS >= size else 0
    if avail + _FIT_EPS < size:
        return 0
    return int((avail - size + _FIT_EPS) / pitch) + 1


def compute_grid(page_w, page_h, tag_w, tag_h, stroke, gap, margin,
                 gap_x=None, gap_y=None,
                 margin_top=None, margin_right=None,
                 margin_bottom=None, margin_left=None):
    """Compute how many columns/rows of tags fit on the page.

    ``gap`` is the space between tiles on both axes and ``margin`` is the
    inset on every side, matching the original single-value behaviour. Pass
    ``gap_x`` / ``gap_y`` or a side margin to override one axis or edge.
    """
    spacing = resolve_grid_spacing(
        gap, margin,
        gap_x=gap_x, gap_y=gap_y,
        margin_top=margin_top, margin_right=margin_right,
        margin_bottom=margin_bottom, margin_left=margin_left,
    )
    pitch_x = tag_w + spacing["gap_x"]
    pitch_y = tag_h + spacing["gap_y"]
    avail_w = page_w - stroke - spacing["margin_left"] - spacing["margin_right"]
    avail_h = page_h - stroke - spacing["margin_top"] - spacing["margin_bottom"]

    cols = max(_slots(avail_w, tag_w, pitch_x), 1)
    rows = max(_slots(avail_h, tag_h, pitch_y), 1)
    return cols, rows, pitch_x, pitch_y


# --- placeholder detection & name copy generation ---------------------------

def detect_placeholders(nametag_xml):
    """Return an ordered mapping of every distinct ``{{token}}`` found in the
    nametag markup to its normalised (lower-cased, stripped) field name. The
    raw token text -- braces and inner spacing included -- is the dict key, so
    substitution replaces exactly what appears in the template."""
    tokens = {}
    for m in PLACEHOLDER_RE.finditer(nametag_xml):
        raw = m.group(0)
        if raw not in tokens:
            tokens[raw] = m.group(1).strip().lower()
    return tokens


def make_tag_copy(nametag_xml, row, tokens, index, tx, ty, missing):
    """Return a positioned copy of the nametag group with every ``{{token}}``
    replaced by the matching value from ``row`` (a dict keyed by lower-cased
    column name). Tokens with no matching column are blanked and recorded in
    ``missing``."""
    body = nametag_xml
    for raw, field in tokens.items():
        if field in row:
            value = row[field]
        else:
            missing.add(field)
            value = ""
        body = body.replace(raw, xml_escape_text(value))
    # Make every id unique to this copy so the merged SVG stays valid.
    body = _ID_ATTR.sub(lambda m: f'id="{m.group(1)}__{index}"', body)
    return (
        f'<g id="nametag-{index}" '
        f'inkscape:label="Nametag {index + 1}" '
        f'transform="translate({fmt(tx)},{fmt(ty)})">'
        f"{body}</g>"
    )


# --- csv input --------------------------------------------------------------

def read_rows(csv_path):
    """Read a CSV with a header row into (fieldnames, rows). Each row is a dict
    keyed by lower-cased, stripped column name so it matches placeholder fields
    case-insensitively."""
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        fieldnames = [f.strip() for f in (reader.fieldnames or [])]
        rows = []
        for raw in reader:
            row = {}
            for key, value in raw.items():
                if key is None:
                    continue
                row[key.strip().lower()] = (value or "").strip()
            # Skip fully blank rows.
            if any(row.values()):
                rows.append(row)
    return fieldnames, rows


# --- output assembly --------------------------------------------------------

def page_filename(output_path, page_number):
    if page_number == 1:
        return output_path
    stem, ext = os.path.splitext(output_path)
    return f"{stem}_{page_number}{ext}"


_UNSAFE_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename(value):
    """Turn an arbitrary field value into a safe file name (no extension)."""
    cleaned = _UNSAFE_FILENAME.sub("_", value or "").strip().rstrip(". ")
    return cleaned


def unique_name(base, used):
    """Return ``base`` (or ``base-2``, ``base-3`` ...) not already in ``used``,
    and record the result in ``used``."""
    name = base
    n = 2
    while name.lower() in used:
        name = f"{base}-{n}"
        n += 1
    used.add(name.lower())
    return name


def match_fields(tokens, fieldnames):
    """Given detected placeholder tokens and CSV field names, return
    ``(template_fields, matched, unmatched, header_set)``."""
    template_fields = list(dict.fromkeys(tokens.values()))
    header_set = {f.strip().lower() for f in fieldnames}
    matched = [f for f in template_fields if f in header_set]
    unmatched = [f for f in template_fields if f not in header_set]
    return template_fields, matched, unmatched, header_set


def generate(template_path, names_csv_path, output_path="output.svg", mode="auto",
             gap=2.0, margin=0.0, out_dir="output", name_field=None,
             gap_x=None, gap_y=None,
             margin_top=None, margin_bottom=None,
             margin_left=None, margin_right=None):
    """Dispatch to the grid or individual generator.

    ``mode`` is ``"auto"`` (choose based on whether the template has a tile
    group), ``"grid"`` or ``"individual"``.

    In grid mode ``gap`` (mm) is the space between tiles on both axes and
    ``margin`` (mm) is the inset on every side. ``gap_x`` / ``gap_y`` and
    ``margin_top`` / ``margin_bottom`` / ``margin_left`` / ``margin_right``
    override one axis or side; leave them unset to keep the shared value.
    """
    with open(template_path, encoding="utf-8") as fh:
        svg_text = fh.read()

    tile = find_tile_group(svg_text)
    resolved = mode
    if mode == "auto":
        resolved = "grid" if tile else "individual"

    if resolved == "grid":
        if tile is None:
            raise ValueError(
                "grid mode needs a repeating tile group labelled one of "
                f"{', '.join(TILE_LABELS)} (e.g. inkscape:label=\"Nametag\"). "
                "Use individual mode for whole-page templates."
            )
        return generate_grid(
            svg_text, tile, names_csv_path, output_path, gap, margin,
            gap_x=gap_x, gap_y=gap_y,
            margin_top=margin_top, margin_bottom=margin_bottom,
            margin_left=margin_left, margin_right=margin_right,
        )
    return generate_individual(svg_text, names_csv_path, out_dir, name_field)


def generate_grid(svg_text, tile, names_csv_path, output_path, gap=2.0, margin=0.0,
                  gap_x=None, gap_y=None,
                  margin_top=None, margin_bottom=None,
                  margin_left=None, margin_right=None):
    start, end, tile_label = tile
    prefix = svg_text[:start]
    suffix = svg_text[end:]
    nametag_xml = svg_text[start:end]
    border_labels = [f"{tile_label} Border", "Border"]

    tokens = detect_placeholders(nametag_xml)
    if not tokens:
        raise ValueError(
            f"No {{{{placeholder}}}} tokens found inside the {tile_label} group. "
            "Add at least one, e.g. {{NAME}}."
        )

    page_w, page_h, uu_per_mm = parse_page(svg_text)
    tag_w, tag_h, stroke = parse_tag_geometry(nametag_xml, border_labels)

    # Spacing arrives in millimetres. Convert into the template's user units so
    # a millimetre is a real millimetre on any template. If the template
    # declares no absolute size, treat the values as user units.
    # A single gap or margin still fills both axes or every side; an explicit
    # per-axis gap or per-side margin replaces only that one.
    scale = uu_per_mm if uu_per_mm else 1.0
    spacing_mm = resolve_grid_spacing(
        gap, margin,
        gap_x=gap_x, gap_y=gap_y,
        margin_top=margin_top, margin_right=margin_right,
        margin_bottom=margin_bottom, margin_left=margin_left,
    )
    spacing = {key: value * scale for key, value in spacing_mm.items()}

    cols, rows, pitch_x, pitch_y = compute_grid(
        page_w, page_h, tag_w, tag_h, stroke,
        spacing["gap_x"], spacing["margin_top"],
        gap_x=spacing["gap_x"], gap_y=spacing["gap_y"],
        margin_top=spacing["margin_top"],
        margin_right=spacing["margin_right"],
        margin_bottom=spacing["margin_bottom"],
        margin_left=spacing["margin_left"],
    )
    per_page = cols * rows

    fieldnames, data_rows = read_rows(names_csv_path)
    if not data_rows:
        raise ValueError(f"No data rows found in {names_csv_path}.")

    template_fields, matched, unmatched, _ = match_fields(tokens, fieldnames)
    if not matched:
        raise ValueError(
            f"CSV {names_csv_path} has no columns matching the template "
            f"placeholders {template_fields}. CSV columns: {fieldnames}."
        )

    missing = set()
    total_pages = (len(data_rows) + per_page - 1) // per_page
    written = []
    for page in range(total_pages):
        chunk = data_rows[page * per_page:(page + 1) * per_page]
        copies = []
        for i, data_row in enumerate(chunk):
            col = i % cols
            grid_row = i // cols
            tx = spacing["margin_left"] + col * pitch_x
            ty = spacing["margin_top"] + grid_row * pitch_y
            copies.append(make_tag_copy(nametag_xml, data_row, tokens, i, tx, ty, missing))

        out_svg = prefix + "".join(copies) + suffix
        out_name = page_filename(output_path, page + 1)
        with open(out_name, "w", encoding="utf-8") as fh:
            fh.write(out_svg)
        written.append((out_name, len(chunk)))

    # For human-readable reporting only. When the template has no absolute size
    # we report raw user units rather than inches.
    mm_per_uu = (1.0 / uu_per_mm) if uu_per_mm else None
    if mm_per_uu is not None:
        page_size_in = (page_w * mm_per_uu / MM_PER_INCH, page_h * mm_per_uu / MM_PER_INCH)
        tag_size_in = (tag_w * mm_per_uu / MM_PER_INCH, tag_h * mm_per_uu / MM_PER_INCH)
    else:
        page_size_in = None
        tag_size_in = None

    return {
        "mode": "grid",
        "tile_label": tile_label,
        "fields": template_fields,
        "matched": matched,
        "unmatched": sorted(unmatched),
        "csv_columns": fieldnames,
        "page_size_uu": (page_w, page_h),
        "tag_size_uu": (tag_w, tag_h),
        "page_size_in": page_size_in,
        "tag_size_in": tag_size_in,
        "grid": (cols, rows),
        "spacing_mm": spacing_mm,
        "per_page": per_page,
        "names": len(data_rows),
        "files": written,
    }


def generate_individual(svg_text, names_csv_path, out_dir="output", name_field=None):
    """Write one output SVG per CSV row: the whole template page with its
    ``{{token}}`` placeholders merged. The template is reproduced byte-for-byte
    apart from the substituted values."""
    tokens = detect_placeholders(svg_text)
    if not tokens:
        raise ValueError(
            "No {{placeholder}} tokens found in the template. "
            "Add at least one, e.g. {{NAME}}."
        )

    fieldnames, data_rows = read_rows(names_csv_path)
    if not data_rows:
        raise ValueError(f"No data rows found in {names_csv_path}.")

    template_fields, matched, unmatched, header_set = match_fields(tokens, fieldnames)
    if not matched:
        raise ValueError(
            f"CSV {names_csv_path} has no columns matching the template "
            f"placeholders {template_fields}. CSV columns: {fieldnames}."
        )

    # Use an explicit comma-separated field list when supplied. Otherwise,
    # certificates with both NAME and DATE use both; other templates retain
    # the first-matched-field default.
    name_fields = [
        field.strip().lower()
        for field in (name_field or "").split(",")
        if field.strip()
    ]
    invalid_name_fields = [field for field in name_fields if field not in header_set]
    if invalid_name_fields:
        raise ValueError(
            f"--name-field contains unknown CSV column(s): {invalid_name_fields}. "
            f"Available columns: {fieldnames}."
        )
    if not name_fields:
        name_fields = ["name", "date"] if "name" in matched and "date" in matched else [matched[0]]

    os.makedirs(out_dir, exist_ok=True)
    missing = set()
    used = set()
    written = []
    for i, row in enumerate(data_rows):
        body = svg_text
        for raw, field in tokens.items():
            if field in row:
                value = row[field]
            else:
                missing.add(field)
                value = ""
            body = body.replace(raw, xml_escape_text(value))

        base = sanitize_filename(
            " - ".join(row.get(field, "") for field in name_fields if row.get(field, ""))
        ) or f"row-{i + 1}"
        out_name = os.path.join(out_dir, unique_name(base, used) + ".svg")
        with open(out_name, "w", encoding="utf-8") as fh:
            fh.write(body)
        written.append((out_name, 1))

    return {
        "mode": "individual",
        "fields": template_fields,
        "matched": matched,
        "unmatched": sorted(unmatched),
        "csv_columns": fieldnames,
        "name_field": ",".join(name_fields),
        "name_fields": name_fields,
        "out_dir": out_dir,
        "names": len(data_rows),
        "files": written,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Mail-merge rows from a CSV onto an SVG template. Either tile "
                    "a repeating nametag/label into a laser-ready grid, or emit "
                    "one full-page SVG per row (certificates, badges, ...)."
    )
    parser.add_argument("--template", default="template.svg", help="Template SVG (default: template.svg)")
    parser.add_argument("--names", default="names.csv", help="CSV of merge data (default: names.csv)")
    parser.add_argument("--mode", choices=("auto", "grid", "individual"), default="auto",
                        help="Output layout: grid (tiled), individual (one file per row), "
                             "or auto-detect (default: auto)")
    parser.add_argument("--output", default="output.svg",
                        help="[grid] Output SVG; extra sheets get _2, _3 suffixes (default: output.svg)")
    parser.add_argument("--out-dir", default="output",
                        help="[individual] Directory for the per-row SVGs (default: output)")
    parser.add_argument("--name-field", default=None,
                        help="[individual] CSV column(s), comma-separated, used to name each output file "
                             "(default: NAME and DATE when both exist; otherwise the first matched field)")
    parser.add_argument("--gap", type=float, default=2.0,
                        help="[grid] Gap between tiles in mm, both axes (default: 2.0). "
                             "Overridden per axis by --gap-x / --gap-y.")
    parser.add_argument("--gap-x", type=float, default=None,
                        help="[grid] Horizontal gap between columns in mm (default: --gap)")
    parser.add_argument("--gap-y", type=float, default=None,
                        help="[grid] Vertical gap between rows in mm (default: --gap)")
    parser.add_argument("--margin", type=float, default=0.0,
                        help="[grid] Margin on every side in mm (default: 0.0). "
                             "Overridden per side by --margin-top/bottom/left/right.")
    parser.add_argument("--margin-top", type=float, default=None,
                        help="[grid] Top page margin in mm (default: --margin)")
    parser.add_argument("--margin-bottom", type=float, default=None,
                        help="[grid] Bottom page margin in mm (default: --margin)")
    parser.add_argument("--margin-left", type=float, default=None,
                        help="[grid] Left page margin in mm (default: --margin)")
    parser.add_argument("--margin-right", type=float, default=None,
                        help="[grid] Right page margin in mm (default: --margin)")
    args = parser.parse_args(argv)

    try:
        result = generate(
            args.template, args.names, args.output, mode=args.mode,
            gap=args.gap, margin=args.margin,
            gap_x=args.gap_x, gap_y=args.gap_y,
            margin_top=args.margin_top, margin_bottom=args.margin_bottom,
            margin_left=args.margin_left, margin_right=args.margin_right,
            out_dir=args.out_dir, name_field=args.name_field,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Fields: {', '.join(result['fields'])}  (matched CSV columns: {', '.join(result['matched'])})")
    if result["unmatched"]:
        print(f"WARNING: template fields with no CSV column (left blank): "
              f"{', '.join(result['unmatched'])}", file=sys.stderr)

    if result["mode"] == "grid":
        cols, rows = result["grid"]
        if result["page_size_in"] and result["tag_size_in"]:
            pw, ph = result["page_size_in"]
            tw, th = result["tag_size_in"]
            print(f"Bed: {pw:.2f}in x {ph:.2f}in   Tile: {tw:.2f}in x {th:.2f}in")
        else:
            pw, ph = result["page_size_uu"]
            tw, th = result["tag_size_uu"]
            print(f"Bed: {pw:g} x {ph:g} (user units)   Tile: {tw:g} x {th:g} (user units)")
        sp = result["spacing_mm"]
        if sp["gap_x"] == sp["gap_y"]:
            gap_txt = f"gap {sp['gap_x']:g} mm"
        else:
            gap_txt = f"gap-x {sp['gap_x']:g} mm, gap-y {sp['gap_y']:g} mm"
        sides = (sp["margin_top"], sp["margin_right"], sp["margin_bottom"], sp["margin_left"])
        if len(set(sides)) == 1:
            margin_txt = f"margin {sides[0]:g} mm"
        else:
            margin_txt = (
                f"margin T {sp['margin_top']:g} / R {sp['margin_right']:g} / "
                f"B {sp['margin_bottom']:g} / L {sp['margin_left']:g} mm"
            )
        print(f"Grid: {cols} cols x {rows} rows = {result['per_page']} per sheet")
        print(f"Spacing: {gap_txt}; {margin_txt}")
        print(f"Records: {result['names']}  ->  {len(result['files'])} sheet(s)")
        for name, count in result["files"]:
            print(f"  {name}: {count} tile(s)")
    else:
        print(f"Mode: individual  (file name from {' + '.join(result['name_fields'])})")
        print(f"Records: {result['names']}  ->  {len(result['files'])} file(s) in {result['out_dir']}/")
        shown = result["files"][:10]
        for name, _ in shown:
            print(f"  {name}")
        if len(result["files"]) > len(shown):
            print(f"  ... and {len(result['files']) - len(shown)} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
