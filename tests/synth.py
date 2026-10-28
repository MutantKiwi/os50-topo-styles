"""Make synthetic GeoPackage stand-ins for every parquet the project references, then load the
project in PyQGIS and check layers, renderers and category coverage.

usage: python3 synth.py <project.qgs> <schema_dir> <testdir>
"""
import json, math, os, random, re, shutil, sys, glob
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from qgis.core import (QgsApplication, QgsProject, QgsVectorLayer, QgsFields, QgsField, QgsFeature,
                       QgsGeometry, QgsPointXY, QgsVectorFileWriter, QgsCoordinateReferenceSystem,
                       QgsCoordinateTransformContext, QgsExpression, QgsExpressionContext,
                       QgsExpressionContextUtils, QgsMapSettings, QgsMapRendererParallelJob, QgsRectangle,
                       QgsWkbTypes, QgsRenderContext, QgsCoordinateTransform)
from qgis.PyQt.QtCore import QVariant, QSize
from qgis.PyQt.QtGui import QColor
import xml.etree.ElementTree as ET

proj_path, schema_dir, testdir = sys.argv[1:4]
app = QgsApplication([], False)
app.initQgis()
random.seed(7)

SCHEMA_ALIAS = {"road_line_tunnel": "road_line", "railway_line_tunnel": "railway_line",
                "nz_topo50_grid": "nztopo50_grid"}
EXTRA = {
    "tunnel": [0, 0, 0, 1], "lane_count": [1, 2, 4, None], "highway_number": [None, None, "1", "2"],
    "hierarchy": [None, "local", "arterial", "motorway"], "elevation": [100, 120, 140, 200, 220],
    "orientation": [0.0, 0.7, 1.6], "designation": [None, None, "supplementary"],
    "perennial": [None, None, "dry"],
}
EXTRA_ENUM = {  # values seen in the user's NZ project but not (yet) in the schema
    ("landcover_point", "type"): ["rock_outcrop", "cemetery", "fumarole", "swamp"],
    ("landcover_point", "subtype"): [None, "small_rock_outcrop", "large_rock_outcrop", "large_boulder"],
    ("vegetation", "type"): ["exotic", "native", "scattered_scrub", "scrub", "orchard", "vineyard"],
    ("water_point", "type"): ["rock", "soakhole", "spring", "swamp", "waterfall"],
    ("railway_line_tunnel", "subtype"): [None, "siding", "tunnel"],
}


def enums(stem):
    f = os.path.join(schema_dir, SCHEMA_ALIAS.get(stem, stem) + ".json")
    out = {}
    if not os.path.exists(f):
        return out
    s = json.load(open(f))
    defs = s.get("$defs", {})

    def find(v):
        if isinstance(v, dict):
            if "$ref" in v:
                d = defs.get(v["$ref"].split("/")[-1], {})
                return d.get("enum") or ([d["const"]] if "const" in d else None) or find(d)
            if "enum" in v:
                return v["enum"]
            if "const" in v:
                return [v["const"]]
            vals = []
            for x in v.get("anyOf", []) + v.get("oneOf", []):
                r = find(x)
                if r:
                    vals += r
            return vals or None
        return None
    for k, v in s.get("properties", {}).items():
        e = find(v)
        if e:
            out[k] = list(e) + [None]
    return out


root = ET.parse(proj_path).getroot()
stems = {}
for m in root.find("projectlayers").findall("maplayer"):
    ds = m.findtext("datasource")
    if m.findtext("provider") != "ogr":
        continue
    path = ds.split("|")[0]
    fields = [f.get("name") for f in m.findall("./fieldConfiguration/field")]
    stems.setdefault(path, (m.get("geometry"), fields, m.findtext("./srs/spatialrefsys/authid")))

os.makedirs(testdir, exist_ok=True)
crs = QgsCoordinateReferenceSystem("EPSG:2193")
X0, Y0 = 1570000, 5180000
for k, (path, (geom, fields, authid)) in enumerate(stems.items()):
    lcrs = QgsCoordinateReferenceSystem(authid)
    xf = QgsCoordinateTransform(crs, lcrs, QgsProject.instance())
    stem = os.path.basename(path).rsplit(".", 1)[0]
    en = enums(stem)
    vals = {}
    for f in fields:
        v = EXTRA_ENUM.get((stem, f)) or en.get(f) or EXTRA.get(f)
        vals[f] = v
    qf = QgsFields()
    for f in fields:
        sample = [x for x in (vals[f] or []) if x is not None]
        t = QVariant.Int if sample and all(isinstance(x, int) for x in sample) else \
            QVariant.Double if sample and all(isinstance(x, (int, float)) for x in sample) else QVariant.String
        qf.append(QgsField(f, t))
    wkb = {"Point": QgsWkbTypes.Point, "Line": QgsWkbTypes.LineString, "Polygon": QgsWkbTypes.Polygon}[geom]
    out = os.path.join(testdir, os.path.basename(path).rsplit(".", 1)[0] + ".gpkg")
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    w = QgsVectorFileWriter.create(out, qf, wkb, lcrs, QgsCoordinateTransformContext(), opts)
    n = 400
    for i in range(n):
        feat = QgsFeature(qf)
        attrs = []
        for f in fields:
            v = vals[f]
            attrs.append(random.choice(v) if v else (f"{f}_{i}" if qf.field(f).type() == QVariant.String else i))
        feat.setAttributes(attrs)
        cx, cy = X0 + (i % 20) * 400 + k * 7, Y0 + (i // 20) * 400 + k * 5
        if geom == "Point":
            g = QgsGeometry.fromPointXY(QgsPointXY(cx, cy))
        elif geom == "Line":
            g = QgsGeometry.fromPolylineXY([QgsPointXY(cx, cy), QgsPointXY(cx + 250, cy + 120), QgsPointXY(cx + 330, cy + 300)])
        else:
            s = 180 if ("area" not in stem and stem != "water") else 1200
            g = QgsGeometry.fromPolygonXY([[QgsPointXY(cx, cy), QgsPointXY(cx + s, cy), QgsPointXY(cx + s, cy + s),
                                            QgsPointXY(cx, cy + s), QgsPointXY(cx, cy)]])
        g.transform(xf)
        feat.setGeometry(g)
        w.addFeature(feat)
    del w

# project copy pointing at the gpkg stand-ins
txt = open(proj_path, encoding="utf-8").read()
txt = re.sub(r"\./([A-Za-z0-9_]+)\.parquet(\|layername=[A-Za-z0-9_]+)?", r"./\1.gpkg", txt)
txt = re.sub(r"\./lds-new-zealand-54layers-GPKG/[^|\"]+/([a-z0-9-]+)\.gpkg", r"./\1.gpkg", txt)
test_proj = os.path.join(testdir, "test.qgs")
open(test_proj, "w", encoding="utf-8").write(txt)
for p in glob.glob(os.path.join(testdir, "*.gpkg")):
    pass

proj = QgsProject.instance()
ok = proj.read(test_proj)
print("project read:", ok)
bad = 0
report = []
for lyr in proj.layerTreeRoot().layerOrder():
    if not isinstance(lyr, QgsVectorLayer):
        report.append(f"[raster] {lyr.name()} valid={lyr.isValid()}")
        continue
    r = lyr.renderer()
    rtype = r.type() if r else None
    line = f"{'OK ' if lyr.isValid() else 'BAD'} {lyr.name()[:70]:70} n={lyr.featureCount():4} {rtype}"
    if not lyr.isValid():
        bad += 1
    if rtype == "mergedFeatureRenderer":
        r = r.embeddedRenderer()
        rtype = r.type()
    if rtype == "categorizedSymbol":
        expr = QgsExpression(r.classAttribute())
        if expr.hasParserError():
            line += f"  PARSE ERROR {expr.parserErrorString()}"
            bad += 1
        ctx = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(lyr))
        expr.prepare(ctx)
        hits = {}
        errs = 0
        for f in lyr.getFeatures():
            ctx.setFeature(f)
            v = expr.evaluate(ctx)
            if expr.hasEvalError():
                errs += 1
            hits[v] = hits.get(v, 0) + 1
        catvals = [c.value() for c in r.categories()]
        missing = [c for c in catvals if c not in hits]
        unknown = [v for v in hits if v is not None and v not in catvals]
        nsym = sum(1 for c in r.categories() if c.symbol() and c.symbol().symbolLayerCount() > 0)
        line += f" cats={len(catvals)} sym_ok={nsym} nulls={hits.get(None, 0)} evalerr={errs}"
        if missing:
            line += f" UNREACHED={missing}"
        if unknown:
            line += f" UNKNOWN={unknown}"; bad += 1
        if errs or nsym != len(catvals):
            bad += 1
    report.append(line)
print("\n".join(report))
print("PROBLEM COUNT:", bad)

# quick render to make sure nothing crashes
ms = QgsMapSettings()
ms.setLayers(proj.layerTreeRoot().layerOrder()[:-1])
ms.setDestinationCrs(crs)
ms.setExtent(QgsRectangle(X0 - 200, Y0 - 200, X0 + 4000, Y0 + 3000))
ms.setOutputSize(QSize(1400, 1000))
ms.setBackgroundColor(QColor("white"))
job = QgsMapRendererParallelJob(ms)
job.start(); job.waitForFinished()
img = job.renderedImage()
img.save(os.path.join(testdir, "render_test.png"))
print("render errors:", [(e.layerID, e.message) for e in job.errors()][:10])
app.exitQgis()
