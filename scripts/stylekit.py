"""Shared symbol helpers for fully custom style modules (NZMS1, OS 1:50k, ...).

make_helpers(ns) takes build.py's globals() and returns small factories that clone
symbol-layer templates and fix the known template gotchas:
  * SVG template carries a data-defined rotation on "orientation"  -> removed
  * outline_width 0 suppresses stroke-only SVGs                     -> 0.2
  * MarkerLine / LinePatternFill sub-symbols have alpha="0"         -> 1
"""
import copy
import xml.etree.ElementTree as ET

PT = 0.3528  # mm per point (OS legend widths are in points)


def pt(v):
    return f"{v * PT:.3f}"


def make_helpers(ns):
    opt, sline, sfill, smarker = ns["opt"], ns["sline"], ns["sfill"], ns["smarker"]
    first_layer, nz_first_layer = ns["first_layer"], ns["nz_first_layer"]
    TPL_ML = first_layer("T50", "MarkerLine")
    TPL_LPF = first_layer("T60", "LinePatternFill")
    TPL_SVG = nz_first_layer("SvgMarker")

    def ln(rgb, w, dash=None, offset="0", pas="0", cap="round"):
        l = sline(rgb, w, dash)
        opt(l, "offset", offset)
        opt(l, "capstyle", cap)
        l.set("pass", pas)
        return l

    def svg(path, size, outline="35,31,32", fill="35,31,32", angle_expr=None):
        l = copy.deepcopy(TPL_SVG)
        ddp = l.find("data_defined_properties")
        if ddp is not None:
            l.remove(ddp)
            l.insert(1, ET.fromstring(ns["EMPTY_DDP"]))
        opt(l, "name", path)
        opt(l, "size", size)
        opt(l, "color", fill + ",255")
        opt(l, "outline_color", outline + ",255")
        opt(l, "outline_width", "0.2")
        opt(l, "offset", "0,0")
        if angle_expr:
            ns["set_angle"](l, angle_expr)
        return l

    def mline(markers, interval, place="Interval", rotate="1", offset="0", along="0"):
        l = copy.deepcopy(TPL_ML)
        opt(l, "interval", interval)
        opt(l, "placements", place)
        opt(l, "placement", place.lower())
        opt(l, "rotate", rotate)
        opt(l, "offset", offset)
        opt(l, "offset_along_line", along)
        sub = l.find("symbol")
        sub.set("alpha", "1")
        for old in sub.findall("layer"):
            sub.remove(old)
        for m in markers:
            sub.append(m)
        return l

    def lpf(rgb, w, dist, angle):
        l = copy.deepcopy(TPL_LPF)
        opt(l, "color", rgb + ",255")
        opt(l, "line_width", w)
        opt(l, "distance", dist)
        opt(l, "angle", angle)
        sub = l.find("symbol")
        sub.set("alpha", "1")
        for old in sub.findall("layer"):
            sub.remove(old)
        sub.append(ln(rgb, w, cap="flat"))
        return l

    def box(size, fill="255,255,255", out="35,31,32", w="0.12", shape="square"):
        m = smarker(fill, size, shape)
        opt(m, "outline_style", "solid")
        opt(m, "outline_color", out + ",255")
        opt(m, "outline_width", w)
        return m

    def fillo(rgb, out, w):
        """solid fill with outline"""
        return sfill(rgb, out, w)

    return dict(ln=ln, svg=svg, mline=mline, lpf=lpf, box=box, fillo=fillo,
                sfill=sfill, smarker=smarker, pattern=ns["pattern"], hashline=ns["hashline"], opt=opt)


def registry():
    S = {}

    def add(key, label, kind, layers):
        S[key] = (label, kind, (lambda rot, _l=layers: [copy.deepcopy(x) for x in _l]))
    return S, add
