"""Ordnance Survey 1:50 000 (Landranger raster legend, 2022) look for a clean NZTopo50 plugin download.

Colours and line widths were read straight from the vector OS legend PDF
(50k-raster-legend, version 2022-01); widths are in points there and converted to mm here.
NZ road classes are mapped onto OS classes:
  state highway with 4+ lanes -> Motorway (blue)        state highway -> Primary route (green)
  sealed, 2+ lanes            -> Road > 4 m (yellow)    sealed, 1 lane -> Road < 4 m (yellow, narrow)
  metalled / unmetalled       -> Other road, drive or track (white)
  vehicle track               -> Other road, drive or track      foot track -> Path
OS magenta (A road) and orange (B road) have no NZ equivalent in the LINZ data and are unused,
except magenta for roads under construction and stations, as on the OS legend.
"""
from stylekit import make_helpers, registry, pt

# ---------------------------------------------------------------- OS palette (from the legend PDF)
BLACK = "35,31,32"          # #231f20
MOTORWAY = "0,174,239"      # #00aeef
PRIMARY = "0,166,80"        # #00a650
MAGENTA = "236,0,140"       # #ec008c  (A roads, stations, under construction)
SECONDARY = "250,162,26"    # #faa21a
YELLOW = "255,242,0"        # #fff200
WHITE = "255,255,255"
WATER_LINE = "0,174,239"    # #00aeef
WATER_FILL = "212,239,252"  # #d4effc
WOOD = "219,234,185"        # #dbeab9
TREE = "0,166,80"           # #00a650
ORCHARD = "255,253,234"     # #fffdea
PARK = "230,231,232"        # #e6e7e8
BUILDING = "254,220,194"    # #fedcc2
SAND = "255,235,202"        # #ffebca
MUD = "216,221,201"         # #d8ddc9
CONTOUR = "246,150,121"     # #f69679
TRIG = "0,174,239"          # cyan triangulation pillar
GRID = "0,174,239"
TEXT_BLUE = "0,114,188"     # water names (darker than the line blue, for legibility)
NZSYM = "./symbol/"
MYSYM = "./os50_symbol/"

G_TEXT, G_PTS, G_LINES, G_TRANS, G_WATER, G_RELIEF, G_AREAS = (
    "Text & grid", "Point symbols", "Utilities & fences", "Transport", "Water", "Heights & rock", "Areas")
T = "\"type\""


def L(name, src, geom, cases, group, **kw):
    return dict(kind="custom", name=f"OS50 {name}", src=src, geom=geom, cases=cases, group=group, **kw)


LAYERS = [
    dict(kind="nzcopy", nz="nztopo50_carto_text", checked=True, group=G_TEXT,
         note="NZ placed text with OS typography (Source Sans Pro, OS colours)"),
    dict(kind="nzcopy", nz="nztopo50_carto_symbol", checked=True, group=G_TEXT,
         subset="\"type\" <> 'golf_course'"),
    L("grid", "data/nz_topo50_grid.parquet", "Line", [("TRUE", "@grid")], G_TEXT),

    # ---------------- points
    L("triangulation pillars", "data/trig_point.parquet", "Point", [("TRUE", "@trig")], G_PTS),
    L("spot heights", "data/relief_point.parquet", "Point", [(f"{T} IN ('height', 'saddle')", "@height")], G_PTS),
    L("structures", "data/structure_point.parquet", "Point", [
        (f"{T} = 'lighthouse'", "@lighthouse"), (f"{T} = 'beacon'", "@beacon"),
        (f"{T} IN ('mast', 'tower', 'radar_dome', 'satellite_station')", "@mast"),
        (f"{T} = 'windmill'", "@windpump"), (f"{T} = 'gate'", "@gate")], G_PTS),
    L("antiquities", "data/place_point.parquet", "Point", [
        (f"{T} IN ('pa', 'historic_site', 'monument', 'grave')", "@antiquity"), (f"{T} = 'cave'", "@cave")], G_PTS),
    L("buildings (points)", "data/building_point.parquet", "Point", [
        ("\"subtype\" = 'church'", "@worship"), ("TRUE", "@building_pt")], G_PTS),
    L("springs", "data/water_point.parquet", "Point", [(f"{T} = 'spring'", "@spring")], G_PTS),

    # ---------------- utilities
    L("power lines & pipelines", "data/extras/utility_line.parquet", "Line", [
        (f"{T} = 'powerline' AND \"support_type\" = 'pylon'", "@powerline"),
        (f"{T} = 'pipeline'", "@pipeline")], G_LINES),

    # ---------------- transport (top to bottom)
    L("railway stations", "data/extras/rail_station.parquet", "Point", [("TRUE", "@station")], G_TRANS),
    L("bridges", "data/bridge_line.parquet", "Line", [
        (f"{T} IN ('foot_traffic', 'farm')", "@bridge_foot"), ("TRUE", "@bridge")], G_TRANS),
    L("railways", "data/railway_line.parquet", "Line", [
        ("\"vehicle_type\" IN ('tram', 'rail_cart', 'cablecar')", "@rail_light"),
        ("\"subtype\" = 'siding'", "@rail_siding"), ("TRUE", "@rail")], G_TRANS),
    L("tunnels", "data/tunnel_line.parquet", "Line", [
        (f"{T} IN ('train', 'tram', 'cablecar')", "@rail_tunnel"),
        (f"{T} = 'vehicle' AND \"subtype\" IS NULL", "@road_tunnel")], G_TRANS),
    L("roads", "data/road_line.parquet", "Line", [
        ("\"status\" = 'under_construction'", "@rd_construction"),
        ("\"highway_number\" IS NOT NULL AND \"lane_count\" >= 4", "@rd_motorway"),
        ("\"highway_number\" IS NOT NULL", "@rd_primary"),
        ("\"surface\" = 'sealed' AND \"lane_count\" >= 2", "@rd_wide"),
        ("\"surface\" = 'sealed'", "@rd_narrow"), ("TRUE", "@rd_other")], G_TRANS, symbollevels=True),
    L("tracks & paths", "data/track_line.parquet", "Line", [
        ("\"subtype\" = 'vehicle'", "@rd_other"), ("TRUE", "@path")], G_TRANS, symbollevels=True),
    L("ferries", "data/extras/ferry_line.parquet", "Line", [("TRUE", "@ferry")], G_TRANS),

    # ---------------- heights & rock
    L("cliffs, cuttings, embankments", "data/relief_line.parquet", "Line", [
        (f"{T} = 'cliff_edge'", "@cliff"), (f"{T} IN ('embankment', 'cutting_edge')", "@embankment"),
        (f"{T} = 'slip_edge'", "@cliff"), (f"{T} IN ('waterfall', 'waterfall_edge')", "@waterfall")], G_RELIEF),
    L("contours", "data/contour.parquet", "Line", [
        ("\"elevation\" % 100 = 0", "@contour_index"), ("TRUE", "@contour")], G_RELIEF),
    L("ice contours", "data/nztopo50_ice_contour.parquet", "Line", [("TRUE", "@ice_contour")], G_RELIEF),

    # ---------------- water lines
    L("rivers, streams, drains", "data/water_line.parquet", "Line", [
        (f"{T} = 'canal'", "@canal"), (f"{T} = 'waterfall'", "@waterfall"), ("TRUE", "@stream")], G_WATER),
    L("weirs, dams, races", "data/structure_line.parquet", "Line", [
        (f"{T} IN ('dam', 'weir')", "@weir"), (f"{T} IN ('flume', 'water_race')", "@canal"),
        (f"{T} IN ('wharf', 'wharf_edge', 'breakwater')", "@wharf")], G_WATER),
    L("high water mark", "data/coastline.parquet", "Line", [("TRUE", "@coast")], G_WATER),

    # ---------------- areas
    L("buildings", "data/building.parquet", "Polygon", [("TRUE", "@building")], G_AREAS),
    L("built-up areas", "data/residential_area.parquet", "Polygon", [("TRUE", "@builtup")], G_AREAS),
    L("landfill, quarries, parks, cemeteries", "data/landuse.parquet", "Polygon", [
        (f"{T} IN ('landfill', 'quarry', 'gravel_pit', 'pumice_pit', 'mine')", "@landfill"),
        (f"{T} IN ('golf_course', 'showground', 'sportsfield', 'racetrack', 'horse_track', 'cemetery')", "@park")],
      G_AREAS),
    L("lakes & rivers", "data/water.parquet", "Polygon", [("TRUE", "@lake")], G_WATER),
    L("rapids (extra)", "data/extras/landcover_extra.parquet", "Polygon", [(f"{T} = 'rapid'", "@lake")], G_WATER),
    L("marsh, sand, shingle, mud, scree, ice", "data/landcover.parquet", "Polygon", [
        (f"{T} = 'swamp'", "@marsh"), (f"{T} = 'sand'", "@sand"), (f"{T} = 'shingle'", "@shingle"),
        (f"{T} = 'mud'", "@mud"), (f"{T} IN ('scree', 'moraine', 'moraine_wall')", "@scree"),
        (f"{T} = 'ice'", "@ice")], G_AREAS),
    L("snow (extra)", "data/extras/landcover_extra.parquet", "Polygon", [(f"{T} IN ('snow', 'ice')", "@ice")], G_AREAS),
    L("woods & orchards", "data/vegetation.parquet", "Polygon", [
        (f"{T} = 'native'", "@wood_broadleaf"),
        (f"{T} = 'exotic' AND \"subtype\" = 'non-coniferous'", "@wood_broadleaf"),
        (f"{T} = 'exotic'", "@wood_conifer"),
        (f"{T} IN ('scrub', 'scattered_scrub')", "@scrub"),
        (f"{T} IN ('orchard', 'vineyard')", "@orchard")], G_AREAS),
    L("mangroves", "data/marine.parquet", "Polygon", [(f"{T} = 'mangrove'", "@marsh")], G_WATER),
    L("sea", "data/nztopo50_sea_polygon.parquet", "Polygon", [("TRUE", "@sea")], G_WATER, merged=True),
]

OVERRIDES = dict(
    TEXT_EXPRS={
        "Family": "'Source Sans Pro'",
        "FontStyle": ("CASE WHEN \"style\" ILIKE '%bold%' AND \"style\" ILIKE '%italic%' THEN 'Bold Italic' "
                      "WHEN \"style\" ILIKE '%bold%' THEN 'Bold' "
                      "WHEN \"style\" ILIKE '%italic%' OR \"colour\" = 'process_blue' THEN 'Italic' ELSE 'Regular' END"),
        "Color": (f"CASE WHEN \"colour\" = 'process_blue' THEN '{TEXT_BLUE}' "
                  f"WHEN \"colour\" = 'warm_red' THEN '{MAGENTA}' ELSE '{BLACK}' END"),
    },
    TEXT_HALO={"bufferDraw": "0"},
    CONTOUR_RGB=CONTOUR,
    CONTOUR_PREFIXES=("OS50 contours", "OS50 ice contours"),
    BACKGROUND=(255, 255, 255),
)


def custom_symbols(ns):
    h = make_helpers(ns)
    ln, svg, mline, box, sfill, smarker, pattern, hashline, opt = (
        h["ln"], h["svg"], h["mline"], h["box"], h["sfill"], h["smarker"], h["pattern"], h["hashline"], h["opt"])
    S, add = registry()

    # widths from the OS legend (points)
    CAS, FIL = pt(2.268), pt(1.417)          # main road classes
    CAS_N, FIL_N = pt(1.701), pt(0.85)       # narrow / other roads
    CAS_M, FIL_M = pt(3.78), pt(2.1)         # motorway

    def road(fill, cas=CAS, fw=FIL):
        return [ln(BLACK, cas, pas="0", cap="flat"), ln(fill, fw, pas="1", cap="flat")]

    add("@grid", "Grid line", "line", [ln(GRID, "0.1")])

    # points
    add("@trig", "Triangulation pillar", "marker", [box("1.5", fill=WHITE, out=TRIG, w="0.18", shape="triangle")])
    add("@height", "Spot height", "marker", [smarker(BLACK, "0.35")])
    add("@lighthouse", "Lighthouse", "marker", [svg(NZSYM + "nztopo50_lighthouse.svg", "2.0")])
    add("@beacon", "Beacon", "marker", [svg(NZSYM + "nztopo50_marine_beacon.svg", "1.7")])
    add("@mast", "Mast", "marker", [svg(NZSYM + "nztopo50_mast.svg", "1.6")])
    add("@windpump", "Wind pump", "marker", [svg(NZSYM + "nztopo50_windmill.svg", "1.5")])
    add("@gate", "Gate", "marker", [svg(NZSYM + "nztopo50_gate.svg", "1.3")])
    add("@antiquity", "Site of antiquity", "marker", [svg(MYSYM + "os50_worship.svg", "1.2")])
    add("@cave", "Cave", "marker", [svg(NZSYM + "nztopo50_cave.svg", "1.6")])
    add("@worship", "Place of worship", "marker", [box("0.9", fill=BUILDING, w="0.1"), svg(MYSYM + "os50_worship.svg", "1.2")])
    add("@building_pt", "Building", "marker", [box("0.7", fill=BUILDING, w="0.1")])
    add("@spring", "Spring", "marker", [smarker(WATER_LINE, "0.5")])

    # utilities
    add("@powerline", "Electricity transmission line", "line",
        [ln(BLACK, pt(0.425)), mline([svg(MYSYM + "os50_pylon.svg", "1.0")], "8", along="4")])
    add("@pipeline", "Pipe line", "line",
        [ln(BLACK, pt(0.425), dash="1.3;1.3"), mline([svg(MYSYM + "os50_arrow.svg", "1.0")], "8", along="4")])

    # transport
    add("@station", "Station", "marker", [box("1.4", fill=MAGENTA, w="0.15", shape="circle")])
    add("@bridge", "Bridge", "line", [ln(BLACK, pt(0.425), offset="0.55", cap="flat"), ln(BLACK, pt(0.425), offset="-0.55", cap="flat")])
    add("@bridge_foot", "Footbridge", "line", [ln(BLACK, pt(0.425), offset="0.3", cap="flat"), ln(BLACK, pt(0.425), offset="-0.3", cap="flat")])
    add("@rail", "Railway (multiple or single track)", "line", [ln(BLACK, pt(1.134), cap="flat")])
    add("@rail_siding", "Siding", "line", [ln(BLACK, pt(0.567), cap="flat")])
    add("@rail_light", "Light rail, narrow gauge or tramway", "line",
        [ln(BLACK, pt(0.56), cap="flat"), hashline(BLACK, pt(0.56), "2.5", "0.8")])
    add("@rail_tunnel", "Railway tunnel", "line", [ln(BLACK, pt(1.12), dash=f"{pt(4.2)};{pt(2.8)}", cap="flat")])
    add("@road_tunnel", "Road tunnel", "line",
        [ln(BLACK, pt(0.425), dash="0.6;0.4", offset="0.4", cap="flat"), ln(BLACK, pt(0.425), dash="0.6;0.4", offset="-0.4", cap="flat")])
    add("@rd_motorway", "Motorway", "line", road(MOTORWAY, CAS_M, FIL_M))
    add("@rd_primary", "Primary route (state highway)", "line", road(PRIMARY))
    add("@rd_wide", "Road generally more than 4 m wide", "line", road(YELLOW))
    add("@rd_narrow", "Road generally less than 4 m wide", "line", road(YELLOW, CAS_N, FIL_N))
    add("@rd_other", "Other road, drive or track", "line", road(WHITE, CAS_N, FIL_N))
    add("@rd_construction", "Road under construction", "line",
        [ln(BLACK, CAS, pas="0", cap="flat"), ln(WHITE, FIL, pas="1", cap="flat"),
         ln(MAGENTA, FIL, dash=f"{pt(11.06)};{pt(5.4)}", pas="2", cap="flat")])
    add("@path", "Path", "line", [ln(BLACK, pt(0.56), dash=f"{pt(4.2)};{pt(1.4)}", pas="3", cap="flat")])
    add("@ferry", "Ferry", "line", [ln(WATER_FILL, "1.2", cap="flat"), ln(BLACK, pt(0.425), dash="1;0.6", cap="flat")])

    # heights & rock
    add("@cliff", "Cliff / outcrop", "line", [ln(BLACK, "0.15"), hashline(BLACK, "0.1", "0.4", "0.6", "0.3")])
    add("@embankment", "Cutting, embankment", "line", [hashline(BLACK, "0.1", "0.4", "0.6", "0.3")])
    add("@contour", "Contour", "line", [ln(CONTOUR, pt(0.28))])
    add("@contour_index", "Index contour", "line", [ln(CONTOUR, pt(0.56))])
    add("@ice_contour", "Contour on ice", "line", [ln(WATER_LINE, pt(0.28))])

    # water
    add("@stream", "River / stream", "line", [ln(WATER_LINE, pt(0.43))])
    add("@canal", "Canal / race", "line", [ln(WATER_LINE, pt(0.28), offset="0.25"), ln(WATER_LINE, pt(0.28), offset="-0.25")])
    add("@waterfall", "Waterfall", "line", [ln(WATER_LINE, "0.3"), hashline(WATER_LINE, "0.12", "0.6", "0.8")])
    add("@weir", "Weir / dam", "line", [ln(BLACK, "0.3")])
    add("@wharf", "Wharf / breakwater", "line", [ln(BLACK, "0.25")])
    add("@coast", "High water mark", "line", [ln(BLACK, pt(0.43))])
    add("@sea", "Sea", "fill", [sfill(WATER_FILL)])
    add("@lake", "Lake / river", "fill", [sfill(WATER_FILL, WATER_LINE, pt(0.28))])
    add("@marsh", "Marsh or salting", "fill", [pattern([svg(MYSYM + "os50_marsh.svg", "1.2", outline=WATER_LINE)], "2.6", "1.8", "0.3")])
    add("@sand", "Sand", "fill", [sfill(SAND), pattern([smarker(BLACK, "0.12")], "0.8", "0.8", "0.35")])
    add("@shingle", "Shingle", "fill", [pattern([smarker(BLACK, "0.25")], "0.9", "0.9", "0.35")])
    add("@mud", "Mud", "fill", [sfill(MUD)])
    add("@scree", "Scree", "fill", [pattern([smarker(BLACK, "0.18")], "0.8", "0.8", "0.35")])
    add("@ice", "Ice / snow", "fill", [sfill(WHITE, WATER_LINE, "0.1")])

    # areas
    add("@building", "Buildings", "fill", [sfill(BUILDING, BLACK, pt(0.28))])
    add("@builtup", "Built-up area", "fill", [sfill("250,233,220")])
    add("@landfill", "Landfill, quarry or spoil heap", "fill", [pattern([smarker(BLACK, "0.2")], "1.0", "1.0", "0.4")])
    add("@park", "Park or ornamental ground", "fill", [sfill(PARK, BLACK, pt(0.425))])
    add("@wood_broadleaf", "Non-coniferous wood", "fill",
        [sfill(WOOD), pattern([svg(MYSYM + "os50_tree_broadleaf.svg", "1.3", outline=TREE)], "3.2", "3.0", "0.6")])
    add("@wood_conifer", "Coniferous wood", "fill",
        [sfill(WOOD), pattern([svg(MYSYM + "os50_tree_conifer.svg", "1.4", outline=TREE)], "3.0", "3.0", "0.6")])
    add("@scrub", "Scrub / rough ground", "fill",
        [pattern([svg(MYSYM + "os50_tree_broadleaf.svg", "0.9", outline=TREE)], "3.4", "3.4", "0.8")])
    add("@orchard", "Orchard", "fill", [sfill(ORCHARD, BLACK, pt(0.425)), pattern([smarker(TREE, "0.25")], "0.9", "0.9")])
    return S
