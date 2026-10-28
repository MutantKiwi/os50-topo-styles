"""Build an NZ Topo50 QGIS project (LINZ parquet) styled with the swisstopo SMV25 symbology.

usage: python build.py <swiss.qgs> <nz.qgs> <out.qgs> <mapping.csv>
"""
import copy
import csv
import re
import sys
import uuid
import xml.etree.ElementTree as ET

import importlib, os
MOD = importlib.import_module(os.environ.get('MAPPING', 'mapping'))
LAYERS = MOD.LAYERS
from translate import tr, tr_layer

REFSCALE = "50000"   # Swiss sizes are paper mm at 1:25k; reuse them at Topo50's 1:50k

ch_path, nz_path, out_path, csv_path = sys.argv[1:5]
CH = ET.parse(ch_path).getroot()
NZT = ET.parse(nz_path)
NZ = NZT.getroot()

ch_layers = {}
for m in CH.find("projectlayers").findall("maplayer"):
    n = m.findtext("layername")
    ch_layers[n.split("_")[0] if n.startswith("T") else n] = m

nz_layers = NZ.find("projectlayers").findall("maplayer")
nz_by_id = {m.findtext("id"): m for m in nz_layers}
nz_checked = {}
for tl in NZ.find("layer-tree-group").iter("layer-tree-layer"):
    nz_checked.setdefault(tl.get("name"), []).append((tl.get("id"), tl.get("checked")))


def src_file(m):
    return m.findtext("datasource").split("|")[0].replace("./", "")


nz_by_src = {}
for m in nz_layers:
    nz_by_src.setdefault(src_file(m), m)


def fields_of(m):
    return [f.get("name") for f in m.findall("./fieldConfiguration/field")]


def new_id(name):
    return re.sub(r"\W+", "_", name)[:60] + "_" + uuid.uuid4().hex[:12]


# ------------------------------------------------------------------ symbol helpers
def opt(layer, name, value):
    omap = layer.find("Option")
    for o in omap.findall("Option"):
        if o.get("name") == name:
            o.set("value", str(value))
            return
    ET.SubElement(omap, "Option", {"value": str(value), "type": "QString", "name": name})


def get_opt(layer, name):
    for o in layer.find("Option").findall("Option"):
        if o.get("name") == name:
            return o.get("value")


def find_cat_symbol(code, value):
    rend = ch_layers[code].find("renderer-v2")
    syms = {s.get("name"): s for s in rend.find("symbols")}
    for c in rend.find("categories"):
        if c.get("value") == value:
            return copy.deepcopy(syms[c.get("symbol")])
    raise KeyError((code, value))


def first_layer(code, cls, value=None):
    rend = ch_layers[code].find("renderer-v2")
    for s in rend.find("symbols"):
        for l in s.iter("layer"):
            if l.get("class") == cls:
                return copy.deepcopy(l)
    raise KeyError((code, cls))


def nz_first_layer(cls):
    for l in NZ.iter("layer"):
        if l.get("class") == cls:
            return copy.deepcopy(l)
    raise KeyError(cls)


def fresh_ids(el):
    for l in el.iter("layer"):
        if l.get("id"):
            l.set("id", "{" + str(uuid.uuid4()) + "}")
        l.set("locked", "0")


EMPTY_DDP = ('<data_defined_properties><Option type="Map"><Option value="" type="QString" name="name"/>'
             '<Option name="properties"/><Option value="collection" type="QString" name="type"/></Option>'
             '</data_defined_properties>')


def symbol(kind, layers):
    s = ET.Element("symbol", {"is_animated": "0", "alpha": "1", "force_rhr": "0", "type": kind,
                              "frame_rate": "10", "clip_to_extent": "1", "name": "0"})
    s.append(ET.fromstring(EMPTY_DDP))
    for l in layers:
        s.append(l)
    fresh_ids(s)
    return s


TPL_FILL = first_layer("T65", "SimpleFill")
TPL_LINE = first_layer("T62", "SimpleLine")
TPL_PPF = first_layer("T64", "PointPatternFill")
TPL_SMARK = first_layer("T64", "SimpleMarker")
TPL_HASH = ET.parse(os.path.join(os.path.dirname(os.path.abspath(__file__)), "tpl_hashline.xml")).getroot()


def sfill(rgb, out_rgb=None, out_w="0"):
    l = copy.deepcopy(TPL_FILL)
    opt(l, "color", rgb + ",255")
    opt(l, "style", "solid")
    opt(l, "outline_color", (out_rgb or rgb) + ",255")
    opt(l, "outline_width", out_w)
    opt(l, "outline_style", "solid" if out_rgb else "no")
    return l


def sline(rgb, w, dash=None):
    l = copy.deepcopy(TPL_LINE)
    opt(l, "line_color", rgb + ",255")
    opt(l, "line_width", w)
    opt(l, "line_style", "solid")
    opt(l, "use_custom_dash", "1" if dash else "0")
    if dash:
        opt(l, "customdash", dash)
    return l


def smarker(rgb, size, shape="circle", angle_expr=None):
    l = copy.deepcopy(TPL_SMARK)
    opt(l, "name", shape)
    opt(l, "color", rgb + ",255")
    opt(l, "outline_style", "no")
    opt(l, "size", size)
    opt(l, "size_unit", "MM")
    opt(l, "offset", "0,0")          # Swiss template carried an 11,9 map-unit offset
    opt(l, "offset_unit", "MM")
    if angle_expr:
        set_angle(l, angle_expr)
    return l


def set_angle(layer, expr):
    ddp = layer.find("data_defined_properties")
    if ddp is not None:
        layer.remove(ddp)
    xml = ('<data_defined_properties><Option type="Map"><Option value="" type="QString" name="name"/>'
           '<Option type="Map" name="properties"><Option type="Map" name="angle">'
           '<Option value="true" type="bool" name="active"/>'
           f'<Option value="{expr.replace(chr(34), "&quot;")}" type="QString" name="expression"/>'
           '<Option value="3" type="int" name="type"/></Option></Option>'
           '<Option value="collection" type="QString" name="type"/></Option></data_defined_properties>')
    idx = list(layer).index(layer.find("Option")) + 1
    layer.insert(idx, ET.fromstring(xml))


def pattern(marker_layers, dist_x, dist_y=None, jitter="0"):
    l = copy.deepcopy(TPL_PPF)
    opt(l, "distance_x", dist_x)
    opt(l, "distance_y", dist_y or dist_x)
    opt(l, "displacement_x", str(float(dist_x) / 2))
    opt(l, "random_deviation_x", jitter)
    opt(l, "random_deviation_y", jitter)
    opt(l, "seed", "4242")
    sub = l.find("symbol")
    for old in sub.findall("layer"):
        sub.remove(old)
    for ml in marker_layers:
        sub.append(copy.deepcopy(ml))
    return l


def hashline(rgb, w, interval, length, offset="0"):
    l = copy.deepcopy(TPL_HASH)
    opt(l, "interval", interval)
    opt(l, "hash_length", length)
    opt(l, "hash_angle", "90")
    opt(l, "placements", "Interval")
    opt(l, "placement", "interval")
    opt(l, "offset", offset)
    opt(l, "rotate", "1")
    sub = l.find("symbol")
    for i, sl in enumerate(sub.findall("layer")):
        if i == 0:
            opt(sl, "line_color", rgb + ",255")
            opt(sl, "line_width", w)
            opt(sl, "line_style", "solid")
            opt(sl, "use_custom_dash", "0")
        else:
            sub.remove(sl)
    return l


def marker_layers_of(code, value):
    return [l for l in find_cat_symbol(code, value).findall("layer")]


ROCK = "62,62,62"      # Swiss Steinböschung / black contour colour
EARTH = "215,150,60"   # Swiss Böschung / brown contour colour
GLACIER = "0,107,199"  # Swiss GLETSCHER raster colour
SCREE = "63,63,63"     # Swiss GEROELL / FELS raster colour

BLDG_PT = "0.5"   # mm, building point square

CUSTOM = {
    "@building_pt": ("Building (point)", "marker",
                     lambda rot: [smarker("0,0,0", BLDG_PT, "square", rot)]),
    "@hut": ("Hut / shelter (point)", "marker",
             lambda rot: [smarker("0,0,0", BLDG_PT, "square", rot)] + [
                 copy.deepcopy(l) for l in find_cat_symbol("T48", "Gastgewerbe abgelegen (Fahne rechts)")
                 .find("./layer[@class='CentroidFill']/symbol").findall("layer")]),
    "@wetland": ("Wetland (Swiss wetland symbol)", "fill",
                 lambda rot: [pattern(marker_layers_of("T43", "Feuchtgebiet"), "2.4", "1.6", "0.25")]),
    "@scrub": ("Scrub (Swiss scrub-forest symbol)", "fill",
               lambda rot: [pattern(marker_layers_of("T43", "Gebüschwald (0.3)"), "1.4", "1.4", "0.25")]),
    "@scattered_scrub": ("Scattered scrub (Swiss scrub symbol, sparse)", "fill",
                         lambda rot: [pattern(marker_layers_of("T43", "Gebüschwald (0.25)"), "2.4", "2.4", "0.5")]),
    "@mangrove": ("Mangrove (Swiss scrub symbol)", "fill",
                  lambda rot: [sfill("210,238,255"),
                               pattern(marker_layers_of("T43", "Gebüschwald (0.38)"), "1.6", "1.6", "0.25")]),
    "@ice": ("Glacier / permanent ice", "fill",
             lambda rot: [sfill("255,255,255")]),
    "@scree": ("Scree / moraine (Swiss scree stipple)", "fill",
               lambda rot: [pattern([smarker(SCREE, "0.2")], "0.7", "0.7", "0.3")]),
    "@shingle": ("Shingle / sand (fine stipple)", "fill",
                 lambda rot: [pattern([smarker("110,110,110", "0.13")], "0.9", "0.9", "0.35")]),
    "@cliff": ("Cliff (Swiss rock colour)", "line",
               lambda rot: [sline(ROCK, "0.2"), hashline(ROCK, "0.12", "0.5", "0.7", "0.35")]),
    "@embankment": ("Embankment / cutting (Swiss embankment colour)", "line",
                    lambda rot: [sline(EARTH, "0.14"), hashline(EARTH, "0.1", "0.7", "0.6", "0.3")]),
    "@stopbank": ("Stopbank / causeway", "line",
                  lambda rot: [sline(EARTH, "0.14"), hashline(EARTH, "0.1", "0.7", "1.2")]),
    "@slip": ("Slip edge", "line",
              lambda rot: [sline(EARTH, "0.16", "1;0.5")]),
    "@seawall": ("Seawall", "line",
                 lambda rot: [sline("0,0,0", "0.25")]),
    "@tree": ("Tree (Swiss tree green)", "marker",
              lambda rot: [smarker("112,180,70", "0.35")]),
    "@residential": ("Residential area", "fill",
                     lambda rot: [sfill("222,222,222", "160,160,160", "0.1")]),
}

if hasattr(MOD, "custom_symbols"):          # style modules can add their own symbols
    CUSTOM.update(MOD.custom_symbols(globals()))


STATION_LEN = 150  # m of track drawn as the Swiss station bar
STATION_EXPR = (
    "with_variable('near', overlay_nearest('@@RAIL@@', $geometry, "
    "filter:=coalesce(\"subtype\", '') <> 'siding', max_distance:=0.003), "
    "if(array_length(@near) = 0, NULL, "
    "with_variable('pt', transform($geometry, @layer_crs, 'EPSG:2193'), "
    "with_variable('rl', transform(@near[0], layer_property('@@RAIL@@', 'crs'), 'EPSG:2193'), "
    "with_variable('d', line_locate_point(@rl, @pt), "
    f"transform(line_substring(@rl, max(0, @d - {STATION_LEN // 2}), min(length(@rl), @d + {STATION_LEN // 2})), "
    "'EPSG:2193', @layer_crs))))))")


def wrap_line_in_point(line_sym, expr):
    """marker symbol -> GeometryGenerator(Line) -> original Swiss line symbol"""
    gg = ET.Element("layer", {"class": "GeometryGenerator", "enabled": "1", "locked": "0", "pass": "0",
                              "id": "{" + str(uuid.uuid4()) + "}"})
    om = ET.SubElement(gg, "Option", {"type": "Map"})
    ET.SubElement(om, "Option", {"name": "SymbolType", "type": "QString", "value": "Line"})
    ET.SubElement(om, "Option", {"name": "geometryModifier", "type": "QString", "value": expr})
    ET.SubElement(om, "Option", {"name": "units", "type": "QString", "value": "MapUnit"})
    gg.append(ET.fromstring(EMPTY_DDP))
    sub = copy.deepcopy(line_sym)
    sub.set("name", "@0@0")
    gg.append(sub)
    outer = ET.Element("symbol", {"is_animated": "0", "alpha": "1", "force_rhr": "0", "type": "marker",
                                  "frame_rate": "10", "clip_to_extent": "1", "name": line_sym.get("name")})
    outer.append(ET.fromstring(EMPTY_DDP))
    outer.append(gg)
    return outer



SHELL = {"Point": "T32", "Line": "T62", "Polygon": "T64"}


# ------------------------------------------------------------------ renderer
def case_expr(cases, value_of):
    parts = []
    for cond, key in cases:
        v = value_of[key].replace("'", "''")
        parts.append(f"WHEN {cond} THEN '{v}'")
    return "CASE " + " ".join(parts) + " END"


def build_renderer(code, cases, rot_expr, geom):
    rend = copy.deepcopy(ch_layers[code].find("renderer-v2"))
    rend.set("referencescale", REFSCALE)
    syms = {s.get("name"): s for s in rend.find("symbols")}
    cats = {c.get("value"): c for c in rend.find("categories")}
    keys = []
    for _, k in cases:
        if k not in keys:
            keys.append(k)
    newcats = ET.Element("categories")
    newsyms = ET.Element("symbols")
    value_of = {}
    for i, k in enumerate(keys):
        if k.startswith("@"):
            label, kind, fn = CUSTOM[k]
            sym = symbol(kind, fn(rot_expr))
            value = label
        else:
            c = cats.get(k)
            if c is None:
                raise KeyError(f"{code}: no Swiss category {k!r}")
            sym = copy.deepcopy(syms[c.get("symbol")])
            value, label = tr(k), tr(c.get("label"))
        sym.set("name", str(i))
        newsyms.append(sym)
        value_of[k] = value
        ET.SubElement(newcats, "category", {"symbol": str(i), "label": label, "value": value,
                                             "render": "true", "uuid": str(uuid.uuid4()), "type": "string"})
    rend.remove(rend.find("categories"))
    rend.remove(rend.find("symbols"))
    rend.insert(0, newsyms)
    rend.insert(0, newcats)
    rend.set("type", "categorizedSymbol")
    rend.set("attr", case_expr(cases, value_of))
    for o in rend.iter("Option"):  # Swiss rotation field -> NZ orientation
        if o.get("name") == "expression" and o.get("value") and "WINKEL" in o.get("value"):
            o.set("value", rot_expr)
    return rend, value_of


def wrap_merged(inner):
    tpl = [m for m in nz_layers if m.findtext("layername") == "nztopo50_sea_polygon"][0]
    outer = copy.deepcopy(tpl.find("renderer-v2"))
    outer.set("referencescale", REFSCALE)
    outer.remove(outer.find("renderer-v2"))
    outer.insert(0, inner)
    return outer


# ------------------------------------------------------------------ map layers
RESET = {"blendMode": "0", "featureBlendMode": "0", "layerOpacity": "1"}


def make_layer(base, name, datasource, renderer):
    m = copy.deepcopy(base)
    lid = new_id(name)
    m.find("id").text = lid
    m.find("layername").text = name
    m.find("datasource").text = datasource
    old = m.find("renderer-v2")
    idx = list(m).index(old)
    m.remove(old)
    m.insert(idx, renderer)
    lab = m.find("labeling")
    if lab is not None:
        m.remove(lab)
    m.set("labelsEnabled", "0")
    m.set("hasScaleBasedVisibilityFlag", "0")
    m.set("symbologyReferenceScale", REFSCALE)  # layer attr overrides the renderer's referencescale
    for tag, val in RESET.items():
        e = m.find(tag)
        if e is not None:
            e.text = val
    for tag in ("map-layer-style-manager",):
        e = m.find(tag)
        if e is not None:
            m.remove(e)
    return m, lid


GROUP_OF = [
    (("T28",), "Grid"), (("T29", "T32", "T33", "T34", "T35", "T36", "T38", "T39"), "Point symbols"),
    (("T40", "T42"), "Structures"), (("T44", "T45", "T46"), "Transport"), (("T48",), "Buildings"),
    (("T43", "T50", "T51", "Glacier", "Scree"), "Land cover & relief"), (("T55", "T56", "T57"), "Water"),
    (("T60", "T61", "T62", "T63", "T64", "T65", "Residential"), "Areas & contours"),
]


def group_for(name):
    for prefixes, g in GROUP_OF:
        if name.startswith(prefixes):
            return g
    return None


out_layers, rows, problems = [], [], []

for spec in LAYERS:
    kind = spec["kind"]
    if kind == "nzcopy":
        cands = nz_checked[spec["nz"]]
        lid0 = next((i for i, c in cands if c == "Qt::Checked"), cands[0][0])
        m = copy.deepcopy(nz_by_id[lid0])
        lid = new_id(spec["nz"])
        m.find("id").text = lid
        if spec.get("subset"):
            ds = m.find("datasource")
            ds.text = ds.text.split("|subset=")[0] + "|subset=" + spec["subset"]
        if "blend" in spec:
            m.find("blendMode").text = str(spec["blend"])
        if "opacity" in spec:
            if m.find("layerOpacity") is not None:
                m.find("layerOpacity").text = str(spec["opacity"])
            rr = m.find("pipe/rasterrenderer")
            if rr is not None:
                rr.set("opacity", str(spec["opacity"]))
        out_layers.append((m, lid, spec["nz"], spec.get("group")))
        rows.append(dict(layer=spec["nz"], swiss_style="(NZ style kept)", nz_source=src_file(m),
                         subset=spec.get("subset", ""), category_en="", category_de="", condition="",
                         note=spec.get("note", "")))
        continue

    if "nzsrc" in spec:
        base = [x for x in nz_layers if x.findtext("layername") == spec["nzsrc"]][0]
        datasource = base.findtext("datasource")
        stem = spec["nzsrc"].split(" — ")[0]
    else:
        base = nz_by_src[spec.get("base_src", spec["src"])]
        datasource = "./" + spec["src"]
        stem = os.path.basename(spec["src"]).replace(".parquet", "")
    if spec.get("subset"):
        datasource += "|subset=" + spec["subset"]
    fields = fields_of(base)
    rot = '-coalesce(degrees("orientation"), 0)' if "orientation" in fields else "0"

    if kind == "swiss":
        code = spec["swiss"]
        chm = ch_layers[code]
        geom = chm.get("geometry")
        name = f"{tr_layer(chm.findtext('layername'))} — {stem}" + (f" ({spec['suffix']})" if spec.get("suffix") else "")
    else:
        code = SHELL[spec["geom"]]
        geom = spec["geom"]
        name = spec["name"]
    if base.get("geometry") != geom and not spec.get("geomgen"):
        problems.append(f"{name}: geometry Swiss={geom} NZ={base.get('geometry')}")

    # field check
    for cond, _ in spec["cases"]:
        for f in re.findall(r'"([^"]+)"', cond):
            if f not in fields:
                problems.append(f"{name}: field {f!r} not in {stem} ({', '.join(fields)})")
    for f in re.findall(r'"([^"]+)"', spec.get("subset", "")):
        if f not in fields:
            problems.append(f"{name}: subset field {f!r} not in {stem}")

    rend, value_of = build_renderer(code, spec["cases"], rot, geom)
    if spec.get("symbollevels"):
        rend.set("symbollevels", "1")
    if spec.get("geomgen") == "station":
        syms = rend.find("symbols")
        for i, s in enumerate(list(syms)):
            syms.remove(s)
            syms.insert(i, wrap_line_in_point(s, STATION_EXPR))
    if spec.get("merged"):
        rend = wrap_merged(rend)
    m, lid = make_layer(base, name, datasource, rend)
    if "min_scale" in spec:  # hide when zoomed out beyond 1:min_scale
        m.set("hasScaleBasedVisibilityFlag", "1")
        m.set("minScale", str(spec["min_scale"]))
        m.set("maxScale", "0")
    if "opacity" in spec:
        m.find("layerOpacity").text = str(spec["opacity"])
    out_layers.append((m, lid, name, spec.get("group") or group_for(name)))
    for cond, key in spec["cases"]:
        rows.append(dict(layer=name, swiss_style=chm.findtext("layername") if kind == "swiss" else "(derived)",
                         nz_source=stem, subset=spec.get("subset", ""), category_en=value_of[key],
                         category_de="" if key.startswith("@") else key, condition=cond,
                         note=spec.get("note", "")))

if problems:
    print("PROBLEMS:", *problems, sep="\n  ")

rail_ids = [lid for _, lid, n, _ in out_layers if n.startswith("T44 Railways — railway_line")]
for m, lid, n, _ in out_layers:
    for o in m.iter("Option"):
        if o.get("value") and "@@RAIL@@" in o.get("value"):
            o.set("value", o.get("value").replace("@@RAIL@@", rail_ids[0]))


# ------------------------------------------------------------------ contour numbers: Swiss colour + mask
CONTOUR_RGB = "215,150,60"   # Swiss Höhenkurve brown
CONTOUR_PREFIXES = ("T62 ", "T55 ")   # layers whose lines the contour numbers knock out
MASK_HALO = "0.5"            # mm stroke around the digits that is knocked out of the contour lines


def patch_contour_numbers():
    targets = []
    for m, lid, name, _ in out_layers:
        if name.startswith(tuple(CONTOUR_PREFIXES)):
            for sl in m.find("renderer-v2").iter("layer"):
                if sl.get("class") and sl.get("id") and sl.get("enabled") == "1":
                    targets.append(f"{lid};{sl.get('id')}")
    ref = ";".join(targets)
    for m, lid, name, _ in out_layers:
        if name != "nztopo50_carto_symbol":
            continue
        for rule in m.find("renderer-v2").iter("rule"):
            if "contour_number" not in (rule.get("filter") or ""):
                continue
            sym = [s for s in m.find("renderer-v2").find("symbols") if s.get("name") == rule.get("symbol")][0]
            font = [l for l in sym.findall("layer") if l.get("class") == "FontMarker"][0]
            opt(font, "color", CONTOUR_RGB + ",255")
            for old in [l for l in sym.findall("layer") if l.get("class") == "MaskMarker"]:
                sym.remove(old)
            # mask = same glyph (same char/angle/offset data-defined props) with a halo stroke
            glyph = copy.deepcopy(font)
            glyph.set("id", "{" + str(uuid.uuid4()) + "}")
            opt(glyph, "outline_color", "0,0,0,255")
            opt(glyph, "outline_width", MASK_HALO)
            mask = ET.Element("layer", {"class": "MaskMarker", "enabled": "1", "locked": "0", "pass": "0",
                                        "id": "{" + str(uuid.uuid4()) + "}"})
            om = ET.SubElement(mask, "Option", {"type": "Map"})
            ET.SubElement(om, "Option", {"name": "mask_symbollayers", "type": "QString", "value": ref})
            mask.append(ET.fromstring(EMPTY_DDP))
            sub = ET.SubElement(mask, "symbol", {"alpha": "1", "clip_to_extent": "1", "force_rhr": "0",
                                                 "frame_rate": "10", "is_animated": "0",
                                                 "name": "@" + sym.get("name") + "@0", "type": "marker"})
            sub.append(ET.fromstring(EMPTY_DDP))
            sub.append(glyph)
            sym.insert(list(sym).index(font), mask)
        # keep the (inactive) label rule consistent too
        lab = m.find("labeling")
        if lab is not None:
            for rule in lab.iter("rule"):
                if "contour_number" in (rule.get("filter") or ""):
                    ts = rule.find("./settings/text-style")
                    ts.set("textColor", CONTOUR_RGB + ",255")
                    tm = ts.find("text-mask")
                    if tm is not None:
                        tm.set("maskedSymbolLayers", ref)
    print(f"contour numbers: colour {CONTOUR_RGB}, masking {len(targets)} contour symbol layers")



# ------------------------------------------------------------------ carto text: Swiss typography
SWISS_FONT = "Liberation Sans Narrow"   # what the swisstopo SMV25 project uses
SWISS_TEXT = {"black": "0,0,0", "process_blue": "0,136,208", "warm_red": "221,25,25"}


def patch_carto_text():
    for m, lid, name, _ in out_layers:
        if name != "nztopo50_carto_text":
            continue
        s = m.find("labeling/settings")
        ts = s.find("text-style")
        ts.set("fontFamily", SWISS_FONT)
        tb = ts.find("text-buffer")  # Swiss halo: 0.5 mm opaque white
        tb.attrib.update(TEXT_HALO)
        exprs = TEXT_EXPRS or {
            "Family": f"'{SWISS_FONT}'",
            "FontStyle": ("CASE WHEN \"style\" ILIKE '%bold%' AND \"style\" ILIKE '%italic%' THEN 'Bold Italic' "
                          "WHEN \"style\" ILIKE '%bold%' THEN 'Bold' "
                          "WHEN \"style\" ILIKE '%italic%' THEN 'Italic' ELSE 'Regular' END"),
            "Color": "CASE " + " ".join(f"WHEN \"colour\" = '{k}' THEN '{v}'" for k, v in SWISS_TEXT.items())
                     + " ELSE '0,0,0' END",
        }
        props = s.find("dd_properties").find("Option").find("Option[@name='properties']")
        for p in props.findall("Option"):
            if p.get("name") in exprs:
                for q in list(p):
                    p.remove(q)
                ET.SubElement(p, "Option", {"name": "active", "type": "bool", "value": "true"})
                ET.SubElement(p, "Option", {"name": "expression", "type": "QString", "value": exprs[p.get("name")]})
                ET.SubElement(p, "Option", {"name": "type", "type": "int", "value": "3"})
        print("carto text: font/colours/halo applied")


TEXT_EXPRS = None   # style module may give its own Family / FontStyle / Color expressions
TEXT_HALO = {"bufferDraw": "1", "bufferSize": "0.5", "bufferSizeUnits": "MM",
             "bufferColor": "255,255,255,255", "bufferOpacity": "1", "bufferNoFill": "0"}
SKIP_PATCHES = set()
BACKGROUND = None
globals().update(getattr(MOD, "OVERRIDES", {}))

if "carto_text" not in SKIP_PATCHES:
    patch_carto_text()
if "contour_numbers" not in SKIP_PATCHES:
    patch_contour_numbers()


# ------------------------------------------------------------------ highway shields: draw the road number
SHIELD_TEXT_RGB = "227,26,28"   # same red as the NZ shield outline / label rule
SHIELD_TEXT_SIZE = "2.2"        # mm (font em size) - fits inside the 3.21 mm shield
SHIELD_TEXT_OFFSET = "0.08,-0.45"  # mm, LINZ nztopo50.qgs value


def patch_highway_shields():
    for m, lid, name, _ in out_layers:
        if name != "nztopo50_carto_symbol":
            continue
        rend = m.find("renderer-v2")
        syms = {s.get("name"): s for s in rend.find("symbols")}
        tpl = None
        for rule in rend.iter("rule"):
            if "contour_number" in (rule.get("filter") or ""):
                tpl = [l for l in syms[rule.get("symbol")].findall("layer") if l.get("class") == "FontMarker"][0]
        for rule in rend.iter("rule"):
            if "highway_shield" not in (rule.get("filter") or ""):
                continue
            sym = syms[rule.get("symbol")]
            for old in [l for l in sym.findall("layer") if l.get("class") == "FontMarker"]:
                sym.remove(old)
            txt = copy.deepcopy(tpl)
            txt.set("id", "{" + str(uuid.uuid4()) + "}")
            opt(txt, "color", SHIELD_TEXT_RGB + ",255")
            opt(txt, "font", "Nimbus Sans LINZ")
            opt(txt, "font_style", "Narrow")
            opt(txt, "size", SHIELD_TEXT_SIZE)
            opt(txt, "offset", SHIELD_TEXT_OFFSET)
            opt(txt, "outline_width", "0")
            opt(txt, "angle", "0")
            # keep only the data-defined text (= "label"); shields stay upright
            props = [o for o in txt.find("data_defined_properties").iter("Option") if o.get("name") == "properties"][0]
            for p in list(props):
                props.remove(p)
            expr = '"label"'  # all LINZ highway_shield features carry the SH number in label
            ch = ET.SubElement(props, "Option", {"name": "char", "type": "Map"})
            ET.SubElement(ch, "Option", {"name": "active", "type": "bool", "value": "true"})
            ET.SubElement(ch, "Option", {"name": "expression", "type": "QString", "value": expr})
            ET.SubElement(ch, "Option", {"name": "type", "type": "int", "value": "3"})
            txt.set("pass", "0")
            # QGIS won't draw a FontMarker after the shield SVG in the same layer, so - like LINZ's
            # nztopo50.qgs - the number goes in its own layer drawn directly above the shields.
            nl = copy.deepcopy(m)
            nid = new_id("highway_numbers")
            nl.find("id").text = nid
            nl.find("layername").text = "nztopo50_carto_symbol — highway numbers"
            nl.find("datasource").text = m.findtext("datasource").split("|subset=")[0] + "|subset=\"type\" = 'highway_shield'"
            for tag in ("labeling", "vectorjoins"):
                e = nl.find(tag)
                if e is not None:
                    for c in list(e):
                        e.remove(c)
            nl.set("labelsEnabled", "0")
            old_r = nl.find("renderer-v2")
            idx = list(nl).index(old_r)
            nl.remove(old_r)
            nr = ET.Element("renderer-v2", {"type": "singleSymbol", "enableorderby": "0", "forceraster": "0",
                                            "referencescale": old_r.get("referencescale", REFSCALE),
                                            "symbollevels": "0"})
            ss = ET.SubElement(nr, "symbols")
            ss.append(symbol("marker", [txt]))
            ET.SubElement(nr, "rotation")
            ET.SubElement(nr, "sizescale")
            nl.insert(idx, nr)
            pos = [i for i, x in enumerate(out_layers) if x[1] == lid][0]
            out_layers.insert(pos, (nl, nid, "nztopo50_carto_symbol — highway numbers", None))
            print("highway shields: road number layer added (field 'label')")
            return


if "highway_shields" not in SKIP_PATCHES:
    patch_highway_shields()

# ------------------------------------------------------------------ assemble project
root = NZ
for tag in ("Layouts", "visibility-presets", "legend", "mapViewDocks"):
    e = root.find(tag)
    if e is not None:
        for c in list(e):
            e.remove(c)
root.set("projectname", "NZ Topo50 — swisstopo SMV25 style")
root.find("title").text = "NZ Topo50 — swisstopo SMV25 style"

pl = root.find("projectlayers")
for c in list(pl):
    pl.remove(c)
lo = root.find("layerorder")
for c in list(lo):
    lo.remove(c)
tree = root.find("layer-tree-group")
for c in list(tree):
    if c.tag in ("layer-tree-layer", "layer-tree-group"):
        tree.remove(c)
co = tree.find("custom-order")
if co is not None:
    for c in list(co):
        co.remove(c)
    co.set("enabled", "0")

groups = {}
insert_at = 1 if tree.find("customproperties") is not None else 0
for m, lid, name, g in out_layers:
    pl.append(m)
    ET.SubElement(lo, "layer", {"id": lid})
    parent = tree
    if g:
        if g not in groups:
            grp = ET.Element("layer-tree-group", {"checked": "Qt::Checked", "expanded": "0",
                                                  "groupLayer": "", "name": g})
            ET.SubElement(grp, "customproperties").append(ET.Element("Option"))
            tree.insert(insert_at, grp)
            insert_at += 1
            groups[g] = grp
        parent = groups[g]
    else:
        tl_slot = ET.Element("layer-tree-layer")
        tree.insert(insert_at, tl_slot)
        insert_at += 1
        parent = None
    attrs = {"checked": "Qt::Checked", "expanded": "0", "id": lid, "legend_exp": "",
             "legend_split_behavior": "0", "name": name, "patch_size": "-1,-1",
             "providerKey": m.find("provider").text, "source": m.findtext("datasource")}
    if parent is None:
        tl_slot.attrib.update(attrs)
        ET.SubElement(tl_slot, "customproperties").append(ET.Element("Option"))
    else:
        tl = ET.SubElement(parent, "layer-tree-layer", attrs)
        ET.SubElement(tl, "customproperties").append(ET.Element("Option"))

if co is None:
    co = ET.SubElement(tree, "custom-order")
co.set("enabled", "1")  # draw order = mapping order, independent of the tidy group tree
for _, lid, _, _ in out_layers:
    ET.SubElement(co, "item").text = lid

if BACKGROUND:
    gui = root.find("properties").find("Gui")
    if gui is None:
        gui = ET.SubElement(root.find("properties"), "Gui")
    for part, v in zip(("Red", "Green", "Blue"), BACKGROUND):
        e = gui.find(f"CanvasColor{part}Part")
        if e is None:
            e = ET.SubElement(gui, f"CanvasColor{part}Part", {"type": "int"})
        e.text = str(v)

ET.indent(NZT, space=" ")
with open(out_path, "wb") as fh:
    fh.write(b"<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>\n")
    NZT.write(fh, encoding="utf-8", xml_declaration=False)

with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)

print(f"{len(out_layers)} layers -> {out_path}; {len(rows)} mapping rows -> {csv_path}")
