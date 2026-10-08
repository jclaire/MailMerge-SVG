/*
 * Keep mail-merge markers intact across an SVG-Edit round trip.
 *
 * The merger finds tiles and backdrop layers by the literal attribute
 * inkscape:label="..." and finds fields by {{TOKEN}} text. SVG-Edit's
 * sanitizer removes Inkscape attributes and can rewrite the root width,
 * height, and viewBox. It keeps data-* attributes and text such as
 * {{NAME}}. This module copies labels onto data-mm-* before editing and
 * writes them back afterwards, and restores the original page size when
 * the editor did not change it.
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.MailmergeFields = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var INKSCAPE_XMLNS = "http://www.inkscape.org/namespaces/inkscape";

  function escapeRegExp(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function decodeXmlEntities(s) {
    return String(s)
      .replace(/&#x([0-9a-fA-F]+);/g, function (_, h) { return String.fromCodePoint(parseInt(h, 16)); })
      .replace(/&#([0-9]+);/g, function (_, n) { return String.fromCodePoint(parseInt(n, 10)); })
      .replace(/&quot;/g, "\"")
      .replace(/&apos;/g, "'")
      .replace(/&#x27;/g, "'")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&amp;/g, "&");
  }

  function escapeAttr(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function decodeAttr(raw) {
    var xml = decodeXmlEntities(raw);
    try { return decodeURIComponent(xml); }
    catch (e) { return xml; }
  }

  function rootOpenTag(svg) {
    var m = String(svg).match(/<svg\b[^>]*>/i);
    return m ? m[0] : "";
  }

  function attr(tag, name) {
    var re = new RegExp("(?:^|\\s)" + escapeRegExp(name) + "\\s*=\\s*([\"'])([\\s\\S]*?)\\1", "i");
    var m = tag.match(re);
    return m ? decodeXmlEntities(m[2]) : null;
  }

  function setAttr(tag, name, value) {
    var re = new RegExp("\\s" + escapeRegExp(name) + "\\s*=\\s*([\"'])[\\s\\S]*?\\1", "ig");
    var stripped = tag.replace(re, "");
    return stripped.replace(/<svg\b/i, "<svg " + name + "=\"" + escapeAttr(value) + "\"");
  }

  function stripAttr(svg, name) {
    var re = new RegExp("\\s" + escapeRegExp(name) + "\\s*=\\s*([\"'])[\\s\\S]*?\\1", "gi");
    return svg.replace(re, "");
  }

  function mirrorAttr(svg, from, to) {
    var re = new RegExp("(\\s" + escapeRegExp(from) + "\\s*=\\s*([\"'])([\\s\\S]*?)\\2)", "gi");
    return svg.replace(re, function (_full, attrText, _q, val) {
      return " " + to + "=\"" + encodeURIComponent(decodeXmlEntities(val)) + "\"" + attrText;
    });
  }

  function mapDataAttr(svg, from, to) {
    var re = new RegExp("\\s" + escapeRegExp(from) + "\\s*=\\s*([\"'])([\\s\\S]*?)\\1", "gi");
    return svg.replace(re, function (_full, _q, raw) {
      return " " + to + "=\"" + escapeAttr(decodeAttr(raw)) + "\"";
    });
  }

  function parseViewBox(vb) {
    if (!vb) return null;
    var p = String(vb).trim().split(/[\s,]+/).map(Number);
    if (p.length !== 4 || p.some(function (n) { return !Number.isFinite(n); })) return null;
    return p;
  }

  function num(v) {
    var n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  function close(a, b) { return Math.abs(a - b) <= 0.05; }

  function capturePage(svg) {
    var tag = rootOpenTag(svg);
    return {
      width: attr(tag, "width"),
      height: attr(tag, "height"),
      viewBox: attr(tag, "viewBox"),
    };
  }

  function prepareTemplateForEditor(svg) {
    if (!/<svg\b/i.test(svg)) throw new Error("Template has no <svg> element.");
    var out = svg;
    out = stripAttr(out, "data-mm-label");
    out = stripAttr(out, "data-mm-groupmode");
    out = mirrorAttr(out, "inkscape:label", "data-mm-label");
    out = mirrorAttr(out, "inkscape:groupmode", "data-mm-groupmode");
    return out;
  }

  function pageUnchanged(page, resolution, tag) {
    var original = parseViewBox(page && page.viewBox);
    if (!original) return false;
    var current = parseViewBox(attr(tag, "viewBox"));
    if (current) return original.every(function (n, i) { return close(n, current[i]); });
    var rw = num(resolution && resolution.w);
    var rh = num(resolution && resolution.h);
    if (rw != null && rh != null) return close(rw, original[2]) && close(rh, original[3]);
    return true;
  }

  function restorePage(svg, page, resolution) {
    if (!page) return svg;
    var m = svg.match(/<svg\b[^>]*>/i);
    if (!m) return svg;
    var tag = m[0];
    if (pageUnchanged(page, resolution, tag)) {
      if (page.viewBox) tag = setAttr(tag, "viewBox", page.viewBox);
      if (page.width) tag = setAttr(tag, "width", page.width);
      if (page.height) tag = setAttr(tag, "height", page.height);
    } else if (!parseViewBox(attr(tag, "viewBox"))) {
      var rw = num(resolution && resolution.w);
      var rh = num(resolution && resolution.h);
      if (rw != null && rh != null) tag = setAttr(tag, "viewBox", "0 0 " + rw + " " + rh);
    }
    return svg.replace(m[0], tag);
  }

  function restoreTemplateFromEditor(svg, page, resolution) {
    if (!/<svg\b/i.test(svg)) throw new Error("The editor did not return an SVG document.");
    var out = svg;
    out = stripAttr(out, "inkscape:label");
    out = stripAttr(out, "inkscape:groupmode");
    out = mapDataAttr(out, "data-mm-label", "inkscape:label");
    out = mapDataAttr(out, "data-mm-groupmode", "inkscape:groupmode");
    if (!/xmlns:inkscape\s*=/i.test(out) && /inkscape:/i.test(out)) {
      out = out.replace(/<svg\b/i, "<svg xmlns:inkscape=\"" + INKSCAPE_XMLNS + "\"");
    }
    out = restorePage(out, page, resolution);
    return out;
  }

  function placeholderFields(svg) {
    var re = /\{\{\s*([^{}]+?)\s*\}\}/g;
    var seen = new Set();
    var fields = [];
    var m;
    while ((m = re.exec(svg))) {
      var key = m[1].trim().toLowerCase();
      if (!seen.has(key)) {
        seen.add(key);
        fields.push(key);
      }
    }
    return fields;
  }

  return {
    capturePage: capturePage,
    prepareTemplateForEditor: prepareTemplateForEditor,
    restoreTemplateFromEditor: restoreTemplateFromEditor,
    placeholderFields: placeholderFields,
  };
});
