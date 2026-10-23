"""Shashank's L-shaped kitchen, built to the carpenter's site sketch and the modular elevation of the sink wall.

All sizes in millimetres below, converted to metres for Blender. Origin: floor, at the inner corner of the hob wall and
the left wall. +X runs along the hob wall towards the right (sink) wall, -Y runs from the hob wall into the room (so standing in the room facing the hob wall, the sink run is on the right,
as in the sketch). Sizes below are written as positive distances from the hob wall; box() flips them.

    Blender -b --factory-startup --python blender/kitchen.py -- [--shots hob,sink,iso,plan] [--res 1600] [--samples 96]
                                                                 [--engine cycles|eevee]

The saved .blend is set to EEVEE so it moves in real time in the viewport; --engine picks what renders the PNGs
(cycles: slower, truer light; eevee: seconds per shot).

Writes out/kitchen.blend, out/kitchen.glb and one PNG per shot in out/.
"""
import math
import re
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
opt = lambda k, d: ARGS[ARGS.index(k) + 1] if k in ARGS else d
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
OUT.mkdir(parents=True, exist_ok=True)

# --- dimensions (mm) ---------------------------------------------------------------------------------------------
ROOM_W = 1800          # hob wall, left wall to right wall (sketch: 1800)
ROOM_D = 2930          # right wall, hob wall to back wall (sketch: 2930)
CEIL = 2810            # floor to ceiling (elevation: 2810)
LEFT_WALL = 290 + 1220  # left wall length from the hob wall (sketch: 290 + 1220); open to the house beyond
# back (window) wall, from the sketch: 280 wall | 990 window | 850 wall = 2120, so it runs 320 past the left wall's line
BACK_X0 = ROOM_W - (280 + 990 + 850)     # -320
WIN_X, WIN_W = BACK_X0 + 280, 990
WIN_SILL, WIN_TOP = 1000, 2100
WALL_T = 150

PLINTH = 100           # skirting under the base units
COUNTER_H = 860        # counter top height (CHT 860)
TOP_T = 40             # stone top thickness
DEPTH = 600            # counter depth (D 600)
CARCASS_D = 560
SHUTTER_T = 20

# hob wall base run (left to right): drawers, hob drawers, then the corner block that the sink run butts into
HOB_RUN = [("drawers2", 575), ("drawers3", 600)]
CORNER = 625           # sink-wall elevation: 625 corner before the first base unit
# sink wall base run (from the corner towards the back wall), from the elevation
SINK_RUN = [("framed_shutter", 600), ("stone_frame", 75), ("sink_shutter", 600), ("stone_frame", 76), ("wm_bay", 932)]

UPPER_TOTAL = 1372            # wall unit + loft + cover, bottom of the wall units to the ceiling: 54in (site)
WALL_H = 720                  # wall units 720 tall (elevation)
WALL_Z0 = CEIL - UPPER_TOTAL  # 1438
LOFT_H = UPPER_TOTAL - WALL_H - 70   # loft above, 70 cover panel to the ceiling
WALL_D = 350
# hob wall: left unit (glass below), chimney opening, right unit; the corner 350 belongs to the sink-wall units
HOB_WALL = [("tower", 575), ("chimney", 600), ("door", 275)]
# sink wall units from the corner (elevation: 650 | 350 | 900 | 900 | 50 filler)
SINK_WALL = [("door", 650), ("door", 350), ("glass2", 900), ("door2", 900), ("filler", 50)]   # glass pair in the middle

MICROWAVE = (455, 262, 344)  # w, h, d (mm): standard 20 L solo microwave (LG MS2043)
OVEN = (457, 305, 279)       # w, h, d (mm): AGARO Marvel 25 L OTG
OPEN_H = 457                 # sink wall: 1.5ft open shelf along the whole wall, tall cabinets above it
TOWER_H, TOWER_D = 914, 430  # left of the chimney: 3ft glass-door appliance cabinet, deeper so the microwave fits
HOB_W = 600
SINK_LEN, SINK_DEP = 960, 500      # single bowl with drainer (site photo): bowl at the W/M end, drainer towards the corner
BOWL_LEN, BOWL_DEP = 390, 400
RAISED_TOP, RAISED_T = 1000, 20    # the slab over the W/M bay sits higher than the counter (site photo); height to confirm
WM = (600, 550, 850)        # front-load 7-8 kg washing machine (LG / Samsung / Bosch), w x d x h
FRIDGE = (555, 680, 1650)   # 250 L double-door fridge, w x d x h: on the window wall, at its far end (right of the window as you face it)

m = lambda v: v / 1000.0

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"


# --- materials ---------------------------------------------------------------------------------------------------
def srgb(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def mat(name, hexcol, rough=0.5, metal=0.0, emit=0.0, coat=0.0, trans=0.0, alpha=1.0):
    mt = bpy.data.materials.new(name); mt.use_nodes = True
    b = mt.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*srgb(hexcol), 1)
    b.inputs["Roughness"].default_value = rough; b.inputs["Metallic"].default_value = metal
    b.inputs["Coat Weight"].default_value = coat
    b.inputs["Transmission Weight"].default_value = trans
    b.inputs["Alpha"].default_value = alpha    # see-through in EEVEE and in the browser, not just in Cycles
    if emit:
        b.inputs["Emission Color"].default_value = (*srgb(hexcol), 1); b.inputs["Emission Strength"].default_value = emit
    return mt


def marble(name, scale=1.2):
    """Warm white stone with soft grey-gold veins: distorted wave bands masked by noise."""
    mt = bpy.data.materials.new(name); mt.use_nodes = True
    nt = mt.node_tree; N = nt.nodes.new; L = nt.links.new
    b = nt.nodes["Principled BSDF"]; b.inputs["Roughness"].default_value = 0.12; b.inputs["Coat Weight"].default_value = 0.3
    tc = N("ShaderNodeTexCoord")
    wv = N("ShaderNodeTexWave"); wv.inputs["Scale"].default_value = scale; wv.inputs["Distortion"].default_value = 14
    wv.inputs["Detail"].default_value = 6; wv.inputs["Detail Roughness"].default_value = 0.65
    rp = N("ShaderNodeValToRGB"); rp.color_ramp.elements[0].position = 0.0; rp.color_ramp.elements[1].position = 0.12
    rp.color_ramp.elements[0].color = (*srgb("#A79C8C"), 1); rp.color_ramp.elements[1].color = (*srgb("#EEE9E1"), 1)
    L(tc.outputs["Object"], wv.inputs["Vector"]); L(wv.outputs["Fac"], rp.inputs["Fac"])
    L(rp.outputs["Color"], b.inputs["Base Color"])
    return mt


def tiles():
    mt = bpy.data.materials.new("FloorTiles"); mt.use_nodes = True
    nt = mt.node_tree; N = nt.nodes.new; L = nt.links.new
    b = nt.nodes["Principled BSDF"]; b.inputs["Roughness"].default_value = 0.18
    tc = N("ShaderNodeTexCoord")
    br = N("ShaderNodeTexBrick"); br.offset = 0.0
    br.inputs["Scale"].default_value = 1 / 0.6; br.inputs["Mortar Size"].default_value = 0.003
    br.inputs["Brick Width"].default_value = 1.0; br.inputs["Row Height"].default_value = 1.0
    br.inputs["Color1"].default_value = (*srgb("#E8DCC8"), 1); br.inputs["Color2"].default_value = (*srgb("#E2D5BF"), 1)
    br.inputs["Mortar"].default_value = (*srgb("#C9BBA4"), 1)
    L(tc.outputs["Object"], br.inputs["Vector"]); L(br.outputs["Color"], b.inputs["Base Color"])
    return mt


M = dict(
    base=mat("BaseAcrylicGreyBlue", "#7F98A2", rough=0.08, coat=1.0),
    wall=mat("WallAcrylicWhite", "#F1F0EC", rough=0.08, coat=1.0),
    carcass=mat("Carcass", "#E9E4DA", rough=0.6),
    reveal=mat("ShutterReveal", "#2E3133", rough=0.7),   # dark shadow gap behind the shutters
    stone=marble("CounterMarble", 1.4),
    splash=marble("BacksplashMarble", 0.9),
    steel=mat("SteelProfile", "#C9CBCC", rough=0.25, metal=1.0),
    paint=mat("WallPaint", "#E4E1DB", rough=0.9),
    ceiling=mat("Ceiling", "#F2F0EB", rough=0.9),
    floor=tiles(),
    glass=mat("ShutterGlass", "#E8ECEB", rough=0.05, alpha=0.1),
    shelf_glass=mat("ShelfGlass", "#DDE8E6", rough=0.02, trans=1.0),
    black=mat("BlackGlass", "#0E0E10", rough=0.1, coat=1.0),
    sink=mat("SinkSteel", "#8F9396", rough=0.35, metal=1.0),
    led=mat("LEDStrip", "#FFD9A0", emit=12.0),
    warm=mat("CabinetGlow", "#FFE2B8", rough=0.6, emit=0.6),
    frame=mat("WindowFrame", "#ECEBE6", rough=0.4),
    pane=mat("WindowPane", "#CFE0E8", rough=0.02, trans=1.0),
    appliance=mat("WasherWhite", "#F4F4F2", rough=0.3, coat=0.5),
    fridge=mat("FridgeSteel", "#4A4C4F", rough=0.3, metal=0.8),
    appliance_dark=mat("ApplianceGraphite", "#2B2D30", rough=0.35, metal=0.4),
    sink_bowl=mat("SinkBowlSteel", "#A4A8AB", rough=0.45, metal=1.0),
    drain=mat("DrainHole", "#111213", rough=0.8),
)


# --- geometry helpers --------------------------------------------------------------------------------------------
COLL = {}


def coll(name):
    if name not in COLL:
        c = bpy.data.collections.new(name); scene.collection.children.link(c); COLL[name] = c
    return COLL[name]


def box(name, x0, x1, y0, y1, z0, z1, material, group="Cabinets", bevel=0.0):
    """Axis-aligned box from mm extents."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=(m(x0 + x1) / 2, -m(y0 + y1) / 2, m(z0 + z1) / 2))
    o = bpy.context.object; o.name = name
    o.scale = (m(abs(x1 - x0)), m(abs(y1 - y0)), m(abs(z1 - z0)))
    bpy.ops.object.transform_apply(scale=True)
    o.data.materials.append(material)
    if bevel:
        bv = o.modifiers.new("Bevel", "BEVEL"); bv.width = m(bevel); bv.segments = 2
    for c in o.users_collection:
        c.objects.unlink(o)
    coll(group).objects.link(o)
    return o


def cyl(name, cx, cy, cz, r, h, material, group="Appliances", axis="z", verts=32):
    """Cylinder centred at (cx, cy, cz) mm, radius r, length h, along a model axis."""
    rot = {"z": (0, 0, 0), "y": (math.pi / 2, 0, 0), "x": (0, math.pi / 2, 0)}[axis]
    bpy.ops.mesh.primitive_cylinder_add(radius=m(r), depth=m(h), location=(m(cx), -m(cy), m(cz)), rotation=rot,
                                        vertices=verts)
    o = bpy.context.object; o.name = name
    o.data.materials.append(material)
    for c in o.users_collection:
        c.objects.unlink(o)
    coll(group).objects.link(o)
    return o


def cut(obj, x0, x1, y0, y1, z0, z1):
    """Boolean a box-shaped hole out of obj and apply it."""
    cutter = box(obj.name + "_Cutter", x0, x1, y0, y1, z0, z1, M["drain"])
    md = obj.modifiers.new("Cut", "BOOLEAN"); md.operation = "DIFFERENCE"; md.object = cutter
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_move_to_index(modifier="Cut", index=0)
    bpy.ops.object.modifier_apply(modifier="Cut")
    bpy.data.objects.remove(cutter)


# --- room --------------------------------------------------------------------------------------------------------
box("Floor", -1500, ROOM_W + WALL_T, -WALL_T, ROOM_D + WALL_T, -20, 0, M["floor"], "Room")
box("Wall_Hob", -WALL_T, ROOM_W + WALL_T, -WALL_T, 0, 0, CEIL, M["paint"], "Room")
box("Wall_Right", ROOM_W, ROOM_W + WALL_T, 0, ROOM_D, 0, CEIL, M["paint"], "Room")
box("Wall_Left", -WALL_T, 0, 0, LEFT_WALL, 0, CEIL, M["paint"], "Room")
# back wall with the door opening
# back wall with the window: a fixed top light over two sliding panes, like the reference photo
box("Wall_Back_L", BACK_X0, WIN_X, ROOM_D, ROOM_D + WALL_T, 0, CEIL, M["paint"], "Room")
box("Wall_Back_R", WIN_X + WIN_W, ROOM_W + WALL_T, ROOM_D, ROOM_D + WALL_T, 0, CEIL, M["paint"], "Room")
box("Wall_Back_Sill", WIN_X, WIN_X + WIN_W, ROOM_D, ROOM_D + WALL_T, 0, WIN_SILL, M["paint"], "Room")
box("Wall_Back_Head", WIN_X, WIN_X + WIN_W, ROOM_D, ROOM_D + WALL_T, WIN_TOP, CEIL, M["paint"], "Room")
WY0, WY1 = ROOM_D + 50, ROOM_D + 110
FR = 50
TRANSOM = WIN_TOP - 450
for nm, ext in (("L", (WIN_X, WIN_X + FR, WIN_SILL, WIN_TOP)), ("R", (WIN_X + WIN_W - FR, WIN_X + WIN_W, WIN_SILL, WIN_TOP)),
                ("B", (WIN_X, WIN_X + WIN_W, WIN_SILL, WIN_SILL + FR)), ("T", (WIN_X, WIN_X + WIN_W, WIN_TOP - FR, WIN_TOP)),
                ("Transom", (WIN_X, WIN_X + WIN_W, TRANSOM - FR / 2, TRANSOM + FR / 2)),
                ("Mullion", (WIN_X + WIN_W / 2 - 20, WIN_X + WIN_W / 2 + 20, WIN_SILL, TRANSOM)),
                ("TopMullion", (WIN_X + WIN_W / 3 - 20, WIN_X + WIN_W / 3 + 20, TRANSOM, WIN_TOP))):
    box(f"Window_Frame{nm}", ext[0], ext[1], WY0, WY1, ext[2], ext[3], M["frame"], "Room")
box("Window_Glass", WIN_X + FR, WIN_X + WIN_W - FR, WY0 + 25, WY0 + 31, WIN_SILL + FR, WIN_TOP - FR, M["pane"], "Room")
box("Window_Sill", WIN_X - 20, WIN_X + WIN_W + 20, ROOM_D - 25, ROOM_D + 50, WIN_SILL - 20, WIN_SILL, M["splash"], "Room")
box("Ceiling", -WALL_T, ROOM_W + WALL_T, -WALL_T, ROOM_D + WALL_T, CEIL, CEIL + 20, M["ceiling"], "Ceiling")

CARCASS_TOP = COUNTER_H - TOP_T          # 820
FRONT_H = CARCASS_TOP - PLINTH           # 720


def drawers(prefix, x0, x1, heights, gap=3):
    """Drawer fronts on the hob run (front face at y = CARCASS_D..+SHUTTER_T), steel profile at each top edge."""
    z = PLINTH
    for i, h in enumerate(heights):
        box(f"{prefix}_Drawer{i}", x0 + gap / 2, x1 - gap / 2, CARCASS_D, CARCASS_D + SHUTTER_T, z + gap / 2, z + h - 22,
            M["base"], bevel=1.5)
        box(f"{prefix}_Profile{i}", x0, x1, CARCASS_D + 2, CARCASS_D + SHUTTER_T, z + h - 22, z + h, M["steel"])
        z += h


# --- hob wall base run -------------------------------------------------------------------------------------------
box("HobRun_Carcass", 0, ROOM_W, 0, CARCASS_D, PLINTH, CARCASS_TOP, M["carcass"])
box("HobRun_Plinth", 0, ROOM_W - DEPTH, CARCASS_D - 40, CARCASS_D - 20, 0, PLINTH, M["splash"])
x = 0
for kind, w in HOB_RUN:
    if kind == "drawers2":
        drawers("Base_Left", x, x + w, [360, 360])
    else:
        drawers("Base_Hob", x, x + w, [180, 180, 360])
        hob_cx = x + w / 2
    x += w
# filler where the hob run's fronts meet the sink run's fronts in the corner
box("Corner_Filler", x, ROOM_W - DEPTH + SHUTTER_T, CARCASS_D, CARCASS_D + SHUTTER_T, PLINTH, CARCASS_TOP, M["base"])
box("Counter_HobRun", 0, ROOM_W, 0, DEPTH, CARCASS_TOP, COUNTER_H, M["stone"], "Counter", bevel=2)

# --- sink wall base run ------------------------------------------------------------------------------------------
SX = ROOM_W - CARCASS_D                   # carcass front face on the sink run (x)
FX0, FX1 = SX - SHUTTER_T, SX             # shutter plane
y = CORNER
box("Corner_Filler_Sink", FX0, FX1, DEPTH, CORNER, PLINTH, CARCASS_TOP, M["base"])
for i, (kind, w) in enumerate(SINK_RUN):
    y0, y1 = y, y + w
    if kind in ("framed_shutter", "sink_shutter"):
        box(f"SinkRun_Carcass{i}", SX, ROOM_W, y0, y1, PLINTH, CARCASS_TOP, M["carcass"])
        box(f"SinkRun_{kind}", FX0, FX1, y0 + 1.5, y1 - 1.5, PLINTH + 1.5, CARCASS_TOP - 24, M["base"], bevel=1.5)
        box(f"SinkRun_{kind}_Profile", FX0, FX1 - 2, y0, y1, CARCASS_TOP - 22, CARCASS_TOP, M["steel"])
        box(f"SinkRun_{kind}_Plinth", SX + 20, SX + 40, y0, y1, 0, PLINTH, M["splash"])
        if kind == "sink_shutter":
            sink_cy = (y0 + y1) / 2
            sink_carcass = f"SinkRun_Carcass{i}"
    elif kind == "stone_frame":
        box(f"SinkRun_StoneFrame{i}", FX0, ROOM_W, y0, y1, 0, CARCASS_TOP, M["splash"])
    elif kind == "wm_bay":
        wm_y0 = y0
    y = y1
# main counter up to the W/M bay; over the bay a thinner slab set higher, with a tiled riser at the step, open below
box("Counter_SinkRun", ROOM_W - DEPTH, ROOM_W, DEPTH, wm_y0, CARCASS_TOP, COUNTER_H, M["stone"], "Counter", bevel=2)
box("Counter_Raised", ROOM_W - DEPTH, ROOM_W, wm_y0, ROOM_D, RAISED_TOP - RAISED_T, RAISED_TOP, M["stone"], "Counter", bevel=2)
box("Counter_Riser", ROOM_W - DEPTH, ROOM_W, wm_y0, wm_y0 + 20, COUNTER_H, RAISED_TOP - RAISED_T, M["splash"], "Counter")

# --- hob, sink, fridge -------------------------------------------------------------------------------------------
box("Hob_Glass", hob_cx - HOB_W / 2, hob_cx + HOB_W / 2, 60, 560, COUNTER_H, COUNTER_H + 8, M["black"], "Appliances", bevel=2)
for i, bx in enumerate((-180, 0, 180)):
    bpy.ops.mesh.primitive_cylinder_add(radius=m(45 if i == 1 else 38), depth=m(22),
                                        location=(m(hob_cx + bx), -m(300), m(COUNTER_H + 19)), vertices=24)
    o = bpy.context.object; o.name = f"Hob_Burner{i}"; o.data.materials.append(M["black"])
    for c in o.users_collection:
        c.objects.unlink(o)
    coll("Appliances").objects.link(o)

# inset single-bowl sink with drainer (site photo): bowl at the W/M end, ribbed drainer towards the corner
sx_c = ROOM_W - DEPTH / 2
bowl_y1 = sink_cy + 300 - 85              # bowl ends 85 short of the sink opening's far side (site photo)
bowl_y0 = bowl_y1 - BOWL_LEN
bowl_cy = (bowl_y0 + bowl_y1) / 2
SY0, SY1 = bowl_y1 + 40 - SINK_LEN, bowl_y1 + 40
SXa, SXb = sx_c - SINK_DEP / 2, sx_c + SINK_DEP / 2
BXa, BXb = sx_c - BOWL_DEP / 2, sx_c + BOWL_DEP / 2
DECK = COUNTER_H + 1.2                    # 1.2 mm steel deck sits on the stone
BOWL_D, BOWL_R = 200, 30                  # bowl depth, corner radius
cut(bpy.data.objects["Counter_SinkRun"], BXa, BXb, bowl_y0, bowl_y1, CARCASS_TOP - 10, COUNTER_H + 10)
cut(bpy.data.objects[sink_carcass],      # hollow under the bowl
    BXa - 20, BXb + 20, bowl_y0 - 20, bowl_y1 + 20, COUNTER_H - BOWL_D - 80, CARCASS_TOP + 10)
# deck round the bowl opening: drainer plate, end strip, two side strips
box("Sink_Deck_Drainer", SXa, SXb, SY0, bowl_y0, COUNTER_H, DECK, M["sink"], "Appliances")
box("Sink_Deck_End", SXa, SXb, bowl_y1, SY1, COUNTER_H, DECK, M["sink"], "Appliances")
box("Sink_Deck_Back", BXb, SXb, bowl_y0, bowl_y1, COUNTER_H, DECK, M["sink"], "Appliances")
box("Sink_Deck_Front", SXa, BXa, bowl_y0, bowl_y1, COUNTER_H, DECK, M["sink"], "Appliances")
# rolled outer rim
RIM = 12
for nm, ext in (("Front", (SXa, SXa + RIM, SY0, SY1)), ("Back", (SXb - RIM, SXb, SY0, SY1)),
                ("Corner", (SXa, SXb, SY0, SY0 + RIM)), ("End", (SXa, SXb, SY1 - RIM, SY1))):
    box(f"Sink_Rim{nm}", *ext, DECK, DECK + 4, M["sink"], "Appliances", bevel=1.8)
# lip round the bowl
for nm, ext in (("Front", (BXa - 8, BXa, bowl_y0 - 8, bowl_y1 + 8)), ("Back", (BXb, BXb + 8, bowl_y0 - 8, bowl_y1 + 8)),
                ("Near", (BXa, BXb, bowl_y0 - 8, bowl_y0)), ("Far", (BXa, BXb, bowl_y1, bowl_y1 + 8))):
    box(f"Sink_BowlLip{nm}", *ext, DECK, DECK + 2.5, M["sink"], "Appliances", bevel=1)
# drainer: pressed border and ribs running down towards the bowl
DR0, DR1 = SY0 + RIM + 30, bowl_y0 - 30
for nm, ext in (("Front", (SXa + 45, SXa + 51, DR0, DR1)), ("Back", (SXb - 51, SXb - 45, DR0, DR1)),
                ("Corner", (SXa + 45, SXb - 45, DR0, DR0 + 6))):
    box(f"Sink_DrainerBorder{nm}", *ext, DECK, DECK + 2.5, M["sink"], "Appliances", bevel=1.2)
n_ribs = 9
for k in range(n_ribs):
    rx = SXa + 75 + k * (SINK_DEP - 150) / (n_ribs - 1)
    box(f"Sink_Rib{k}", rx - 3, rx + 3, DR0 + 30, DR1, DECK, DECK + 2.5, M["sink"], "Appliances", bevel=1.2)
# hollow bowl: open-top box, rounded corners, 1 mm wall
bowl = box("Sink_Bowl", BXa, BXb, bowl_y0, bowl_y1, COUNTER_H - BOWL_D, DECK, M["sink_bowl"], "Appliances")
bm = bmesh.new(); bm.from_mesh(bowl.data)
bmesh.ops.delete(bm, geom=[max(bm.faces, key=lambda f: f.calc_center_median().z)], context="FACES_ONLY")
bm.to_mesh(bowl.data); bm.free()
bv = bowl.modifiers.new("Round", "BEVEL"); bv.width = m(BOWL_R); bv.segments = 6; bv.limit_method = "ANGLE"
sd = bowl.modifiers.new("Wall", "SOLIDIFY"); sd.thickness = m(1); sd.offset = 1
bowl.data.shade_smooth()
# waste: strainer ring, dark hole, centre button; overflow slot on the far wall
FLOOR = COUNTER_H - BOWL_D
cyl("Sink_WasteRing", sx_c, bowl_cy, FLOOR + 1.5, 45, 3, M["steel"])
cyl("Sink_WasteHole", sx_c, bowl_cy, FLOOR + 3.2, 34, 0.6, M["drain"])
cyl("Sink_WasteCap", sx_c, bowl_cy, FLOOR + 4, 12, 3, M["steel"])
box("Sink_Overflow", sx_c - 25, sx_c + 25, bowl_y1 - 3, bowl_y1 - 1.5, COUNTER_H - 45, COUNTER_H - 33, M["drain"],
    "Appliances")
# wall-mounted tap over the bowl
box("Tap_Arm", ROOM_W - 160, ROOM_W - 8, bowl_cy - 14, bowl_cy + 14, COUNTER_H + 300, COUNTER_H + 328, M["steel"], "Appliances")
box("Tap_Spout", ROOM_W - 175, ROOM_W - 147, bowl_cy - 14, bowl_cy + 14, COUNTER_H + 220, COUNTER_H + 328, M["steel"],
    "Appliances")

wm_cy = wm_y0 + 932 / 2
WMX = ROOM_W - 20 - WM[1]                 # washing machine front face
box("WashingMachine", WMX, ROOM_W - 20, wm_cy - WM[0] / 2, wm_cy + WM[0] / 2, 0, WM[2], M["appliance"], "Appliances", bevel=8)
bpy.ops.mesh.primitive_cylinder_add(radius=m(170), depth=m(10), location=(m(WMX - 5), -m(wm_cy), m(420)),
                                    rotation=(0, math.pi / 2, 0), vertices=40)
o = bpy.context.object; o.name = "WashingMachine_Door"; o.data.materials.append(M["black"])

# fridge: back to the window wall at its far end (the side away from the sink run), door facing the hob wall
FR0, FR1 = BACK_X0, BACK_X0 + FRIDGE[0]
FY = ROOM_D - 30 - FRIDGE[1]              # fridge front face
box("Fridge", FR0, FR1, FY, ROOM_D - 30, 0, FRIDGE[2], M["fridge"], "Appliances", bevel=10)
box("Fridge_Split", FR0 + 5, FR1 - 5, FY - 2, FY + 2, 1180, 1190, M["black"], "Appliances")
box("Fridge_Handle", FR1 - 60, FR1 - 40, FY - 25, FY - 5, 1250, 1500, M["steel"], "Appliances")

# --- backsplash --------------------------------------------------------------------------------------------------
box("Splash_HobWall", 0, ROOM_W, 0, 8, COUNTER_H, WALL_Z0, M["splash"], "Counter")
box("Splash_SinkWall", ROOM_W - 8, ROOM_W, 0, ROOM_D, COUNTER_H, WALL_Z0, M["splash"], "Counter")

# --- wall units and lofts ----------------------------------------------------------------------------------------
WZ1 = WALL_Z0 + WALL_H                    # 2158
LZ1 = WZ1 + LOFT_H                        # 2740 (70 cover above)


def shell(name, x0, x1, y0, y1, z0, z1, along_x, t=18):
    """Open-fronted wall-unit carcass (back, sides, top, bottom) so a glass front shows the inside."""
    if along_x:                              # hob wall: depth along y, back against y = 0
        parts = (("Back", x0, x1, y0, y0 + t, z0, z1), ("SideL", x0, x0 + t, y0, y1, z0, z1),
                 ("SideR", x1 - t, x1, y0, y1, z0, z1), ("Bottom", x0, x1, y0, y1, z0, z0 + t),
                 ("Top", x0, x1, y0, y1, z1 - t, z1))
    else:                                    # sink wall: depth along x, back against x = ROOM_W
        parts = (("Back", x1 - t, x1, y0, y1, z0, z1), ("SideL", x0, x1, y0, y0 + t, z0, z1),
                 ("SideR", x0, x1, y1 - t, y1, z0, z1), ("Bottom", x0, x1, y0, y1, z0, z0 + t),
                 ("Top", x0, x1, y0, y1, z1 - t, z1))
    for nm, *ext in parts:
        box(f"{name}_{nm}", *ext, M["carcass"])


def wall_front(name, a0, a1, z0, z1, along_x, kind, depth=WALL_D):
    """One shutter on a wall unit. along_x: hob wall (front at y = WALL_D), else sink wall (front at x = ROOM_W - WALL_D)."""
    g = 3     # 6 mm seam between shutters, dark reveal behind it (not behind glass)
    if kind == "glass":
        pass
    elif along_x:
        box(name + "_Reveal", a0, a1, depth - SHUTTER_T - 1, depth - SHUTTER_T + 2, z0, z1, M["reveal"])
    else:
        box(name + "_Reveal", ROOM_W - WALL_D + SHUTTER_T - 2, ROOM_W - WALL_D + SHUTTER_T + 1, a0, a1, z0, z1, M["reveal"])
    if along_x:
        ext = (a0 + g, a1 - g, depth - SHUTTER_T, depth, z0 + g, z1 - g)
    else:
        ext = (ROOM_W - WALL_D, ROOM_W - WALL_D + SHUTTER_T, a0 + g, a1 - g, z0 + g, z1 - g)
    if kind == "glass":
        fr = 22   # steel frame round the glass
        A0, A1, Z0, Z1 = a0 + g, a1 - g, z0 + g, z1 - g
        bars = (("L", A0, A0 + fr, Z0, Z1), ("R", A1 - fr, A1, Z0, Z1), ("B", A0 + fr, A1 - fr, Z0, Z0 + fr),
                ("T", A0 + fr, A1 - fr, Z1 - fr, Z1))
        for nm, b0, b1, c0, c1 in bars:      # steel frame: four bars round the glass
            if along_x:
                box(f"{name}_Frame{nm}", b0, b1, ext[2], ext[3], c0, c1, M["steel"])
            else:
                box(f"{name}_Frame{nm}", ext[0], ext[1], b0, b1, c0, c1, M["steel"])
        if along_x:
            box(name + "_Glass", A0 + fr, A1 - fr, depth - SHUTTER_T / 2 - 3, depth - SHUTTER_T / 2 + 3, Z0 + fr, Z1 - fr,
                M["glass"])
        else:
            box(name + "_Glass", ext[0] + SHUTTER_T / 2 - 3, ext[0] + SHUTTER_T / 2 + 3, A0 + fr, A1 - fr, Z0 + fr, Z1 - fr,
                M["glass"])
    else:
        box(name, *ext, M["wall"], bevel=1.5)


# hob wall
x = 0
for i, (kind, w) in enumerate(HOB_WALL):
    x0, x1 = x, x + w
    if kind == "chimney":
        box("Splash_Chimney", x0, x1, 0, 8, WALL_Z0, WZ1, M["splash"], "Counter")
        box("Chimney_Hood", x0 + 30, x1 - 30, 8, 330, WALL_Z0 + 60, WALL_Z0 + 260, M["black"], "Appliances", bevel=4)
        box("Chimney_Duct", (x0 + x1) / 2 - 130, (x0 + x1) / 2 + 130, 8, 220, WALL_Z0 + 260, WZ1, M["black"], "Appliances")
        box("Chimney_Soffit", x0, x1, 0, WALL_D, WZ1 - 20, WZ1, M["wall"])
    else:
        if kind == "tower":               # 3ft glass-door cabinet (microwave below, OTG above), closed cabinet over it
            TZ1, TD = WALL_Z0 + TOWER_H, TOWER_D - SHUTTER_T
            shell(f"HobWall_Unit{i}", x0, x1, 0, TD, WALL_Z0, TZ1, True)
            box(f"HobWall_Unit{i}_Top", x0, x1, 0, TD, TZ1, LZ1, M["carcass"])
            wall_front(f"HobWall_Unit{i}_Top", x0, x1, TZ1, LZ1, True, "door", depth=TOWER_D)
            box(f"HobWall_Unit{i}_Cover", x0, x1, WALL_D, TOWER_D, LZ1, CEIL, M["wall"])
            shelf_z = WALL_Z0 + 18 + MICROWAVE[1] + 130
            box(f"HobWall_Unit{i}_Shelf", x0 + 18, x1 - 18, 18, TD, shelf_z, shelf_z + 18, M["carcass"])
            box(f"HobWall_Unit{i}_Glow", x0 + 20, x1 - 20, 18, 21, WALL_Z0 + 25, TZ1 - 25, M["warm"])
            wall_front(f"HobWall_Unit{i}", x0, x1, WALL_Z0, TZ1, True, "glass", depth=TOWER_D)
            cx = (x0 + x1) / 2
            for nm, (aw, ah, ad), zb in (("Microwave", MICROWAVE, WALL_Z0 + 18), ("Oven", OVEN, shelf_z + 18)):
                fy = TD - 18                  # appliance fronts 18 behind the glass door
                box(nm, cx - aw / 2, cx + aw / 2, fy - ad, fy, zb, zb + ah, M["appliance_dark"], "Appliances", bevel=6)
                box(f"{nm}_Door", cx - aw / 2 + 12, cx + aw / 2 - 110, fy, fy + 4, zb + 14, zb + ah - 14,
                    M["black"], "Appliances", bevel=3)
                box(f"{nm}_Panel", cx + aw / 2 - 95, cx + aw / 2 - 14, fy, fy + 3, zb + 14, zb + ah - 14,
                    M["steel"], "Appliances")
                for k in range(2):           # control knobs
                    cyl(f"{nm}_Knob{k}", cx + aw / 2 - 55, fy + 3, zb + ah * (0.68 - 0.36 * k), 14, 14, M["black"],
                        "Appliances", axis="y")
        elif kind == "glass_low":
            split = WALL_Z0 + 330
            box(f"HobWall_Unit{i}_Glow", x0 + 20, x1 - 20, 20, 25, WALL_Z0 + 20, split - 20, M["warm"])
            wall_front(f"HobWall_Unit{i}_Low", x0, x1, WALL_Z0, split, True, "glass")
            wall_front(f"HobWall_Unit{i}_High", x0, x1, split, WZ1, True, "door")
        else:
            wall_front(f"HobWall_Unit{i}", x0, x1, WALL_Z0, WZ1, True, "door")
    if kind != "tower":
        box(f"HobWall_Loft{i}", x0, x1, 0, WALL_D - SHUTTER_T, WZ1, LZ1, M["carcass"])
        wall_front(f"HobWall_Loft{i}", x0, x1, WZ1, LZ1, True, "door")
        box(f"HobWall_Profile{i}", x0, x1, WALL_D - 18, WALL_D, WZ1 - 6, WZ1 + 6, M["steel"])
    x = x1
HOB_WALL_END = x                          # 1450 = ROOM_W - WALL_D

# sink wall: a 1.5ft open shelf runs the length of the wall; above it every piece is one tall cabinet to the cover strip
OZ1 = WALL_Z0 + OPEN_H
SINK_WALL_END = sum(w for _, w in SINK_WALL)
shell("SinkWall_Shelf", ROOM_W - WALL_D, ROOM_W, 0, SINK_WALL_END, WALL_Z0, OZ1, False)
box("SinkWall_ShelfGlow", ROOM_W - 21, ROOM_W - 18, WALL_D + 20, SINK_WALL_END - 20, WALL_Z0 + 25, OZ1 - 25, M["warm"])
y = 0
for i, (kind, w) in enumerate(SINK_WALL):
    y0, y1 = y, y + w
    vis0 = max(y0, WALL_D)                # the first 350 hides behind the hob-wall units in the corner
    mid = (y0 + y1) / 2
    if kind == "filler":
        box(f"SinkWall_Filler{i}", ROOM_W - WALL_D, ROOM_W, y0, y1, OZ1, LZ1, M["wall"])
    elif kind == "glass2":                # lit glass pair, same height as its neighbours, with glass shelves
        shell(f"SinkWall_Unit{i}", ROOM_W - WALL_D + SHUTTER_T, ROOM_W, y0, y1, OZ1, LZ1, False)
        box(f"SinkWall_Unit{i}_Glow", ROOM_W - 21, ROOM_W - 18, y0 + 20, y1 - 20, OZ1 + 25, LZ1 - 25, M["warm"])
        for k in (1, 2, 3):
            sz = OZ1 + (LZ1 - OZ1) * k / 4
            box(f"SinkWall_Unit{i}_Shelf{k}", ROOM_W - WALL_D + SHUTTER_T + 10, ROOM_W - 25, y0 + 20, y1 - 20, sz - 4, sz + 4,
                M["shelf_glass"])
        wall_front(f"SinkWall_Unit{i}a", y0, mid, OZ1, LZ1, False, "glass")
        wall_front(f"SinkWall_Unit{i}b", mid, y1, OZ1, LZ1, False, "glass")
    else:
        box(f"SinkWall_Unit{i}", ROOM_W - WALL_D + SHUTTER_T, ROOM_W, y0, y1, OZ1, LZ1, M["carcass"])
        if kind in ("door2", "tall_open"):
            wall_front(f"SinkWall_Unit{i}a", y0, mid, OZ1, LZ1, False, "door")
            wall_front(f"SinkWall_Unit{i}b", mid, y1, OZ1, LZ1, False, "door")
        else:
            wall_front(f"SinkWall_Unit{i}", vis0, y1, OZ1, LZ1, False, "door")
    y = y1
# 70 mm cover panel from the lofts to the ceiling, both walls
box("HobWall_TopCover", 0, ROOM_W - WALL_D, 0, WALL_D, LZ1, CEIL, M["wall"])
box("SinkWall_TopCover", ROOM_W - WALL_D, ROOM_W, 0, y, LZ1, CEIL, M["wall"])

# LED strips under the wall units
box("LED_HobWall_L", 20, HOB_WALL[0][1] - 20, 40, 60, WALL_Z0 - 4, WALL_Z0, M["led"], "Lights")
box("LED_HobWall_R", HOB_WALL[0][1] + HOB_WALL[1][1] + 20, HOB_WALL_END, 40, 60, WALL_Z0 - 4, WALL_Z0, M["led"], "Lights")
box("LED_SinkWall", ROOM_W - 60, ROOM_W - 40, WALL_D, y - 20, WALL_Z0 - 4, WALL_Z0, M["led"], "Lights")

# --- dimensions (Dimensions collection; red lines and mm labels on the counters and cabinets) -----------------------
from mathutils import Matrix
def flat(name, hexcol, strength=1.6):
    """Pure emission, so the labels keep their colour whatever the lighting."""
    mt = bpy.data.materials.new(name); mt.use_nodes = True
    nt = mt.node_tree
    for nd in list(nt.nodes):
        nt.nodes.remove(nd)
    em = nt.nodes.new("ShaderNodeEmission"); em.inputs["Color"].default_value = (*srgb(hexcol), 1)
    em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs[0], nt.nodes.new("ShaderNodeOutputMaterial").inputs["Surface"])
    return mt


M["dim"] = flat("Dimension", "#D4141E")
W = lambda x, y, z: Vector((m(x), -m(y), m(z)))
FACE = {   # text x-axis, plane normal (Blender space), for each surface the labels sit on
    "hob": (Vector((1, 0, 0)), Vector((0, -1, 0))),     # hob-run fronts, read from the room
    "sink": (Vector((0, -1, 0)), Vector((-1, 0, 0))),   # sink-run fronts
    "top": (Vector((1, 0, 0)), Vector((0, 0, 1))),      # counter tops, read from above
    "topy": (Vector((0, -1, 0)), Vector((0, 0, 1))),
}
DIM_TEXT = []


def rod(name, a, b, r=0.005):
    d = b - a
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=d.length, location=(a + b) / 2, vertices=8)
    o = bpy.context.object; o.name = name
    o.rotation_mode = "QUATERNION"; o.rotation_quaternion = d.to_track_quat("Z", "Y")
    o.data.materials.append(M["dim"])
    for c in o.users_collection:
        c.objects.unlink(o)
    coll("Dimensions").objects.link(o)


def label(name, text, at, face, size=0.075, align="CENTER"):
    u, n = FACE[face]
    v = n.cross(u)
    cu = bpy.data.curves.new(name, "FONT"); cu.body = text; cu.size = size
    cu.align_x = align; cu.align_y = "CENTER"
    o = bpy.data.objects.new(name, cu); o.data.materials.append(M["dim"])
    o.matrix_world = Matrix.Translation(at + n * 0.002) @ Matrix((u, v, n)).transposed().to_4x4()
    coll("Dimensions").objects.link(o); DIM_TEXT.append(o)


def ft_in(mm):
    """Millimetres as feet and inches, to the nearest inch: 860 -> '2ft 10in'."""
    f, i = divmod(round(mm / 25.4), 12)
    return f"{f}ft {i}in"


def dim(name, p0, p1, text, face, lift=0.05, left=False):
    """Dimension line p0-p1 (mm, model coordinates) with slash ticks and its label, drawn on `face`.
    Every number in the label is written in mm and shown in feet and inches."""
    text = re.sub(r"\d+", lambda g: ft_in(int(g.group())), text)
    u, n = FACE[face]
    a, b = W(*p0), W(*p1)
    if face.startswith("top"):              # float the counter-top dims clear of the hob and sink
        a, b = a + n * 0.015, b + n * 0.015
    d = (b - a).normalized()
    side = n.cross(d)
    rod(f"Dim_{name}_Line", a, b)
    for i, e in enumerate((a, b)):
        t = (d + side).normalized() * 0.025
        rod(f"Dim_{name}_Tick{i}", e - t, e + t)
    mid = (a + b) / 2
    if abs(d.dot(u)) > 0.9:                 # runs along the text: label above the line
        label(f"Dim_{name}_Text", text, mid + n.cross(u) * lift, face)
    else:                                   # vertical: label beside the line
        label(f"Dim_{name}_Text", text, mid + u * (-0.03 if left else 0.03), face, align="RIGHT" if left else "LEFT")


# base units: widths across the fronts, low on the doors
BZ = PLINTH + 90
HY = CARCASS_D + SHUTTER_T + 40           # just in front of the hob-run fronts
x = 0
for i, (kind, w) in enumerate(HOB_RUN):
    dim(f"base_hob{i}", (x, HY, BZ), (x + w, HY, BZ), f"{w}", "hob"); x += w
dim("base_hobcorner", (x, HY, BZ), (ROOM_W, HY, BZ), f"{ROOM_W - x} corner", "hob")
SXD = FX0 - 40                            # just in front of the sink-run fronts
y = CORNER
for i, (kind, w) in enumerate(SINK_RUN):
    txt = {"stone_frame": f"{w}", "wm_bay": f"{w} W/M (open)", "framed_shutter": f"{w} framed shutter",
           "sink_shutter": f"{w} sink"}[kind]
    z = BZ - 80 if kind == "stone_frame" else BZ
    dim(f"base_sink{i}", (SXD, y, z), (SXD, y + w, z), txt, "sink"); y += w

# counters: lengths and depths on the tops
dim("top_hob_len", (0, DEPTH - 50, COUNTER_H), (ROOM_W, DEPTH - 50, COUNTER_H), f"{ROOM_W} counter", "top")
dim("top_hob_dep", (60, 0, COUNTER_H), (60, DEPTH, COUNTER_H), f"{DEPTH}", "top")
dim("top_sink_len", (ROOM_W - DEPTH + 50, DEPTH, COUNTER_H), (ROOM_W - DEPTH + 50, wm_y0, COUNTER_H),
    f"{int(wm_y0 - DEPTH)} counter", "topy")
dim("top_raised_len", (ROOM_W - DEPTH + 50, wm_y0, RAISED_TOP), (ROOM_W - DEPTH + 50, ROOM_D, RAISED_TOP),
    f"{int(ROOM_D - wm_y0)} raised slab", "topy")
dim("top_sink_dep", (ROOM_W - DEPTH, 2400, RAISED_TOP), (ROOM_W, 2400, RAISED_TOP), f"{DEPTH}", "top")

# heights, at the left end of the hob run and at the W/M bay
HX = 40
dim("h_counter", (HX, HY, 0), (HX, HY, COUNTER_H), f"{COUNTER_H} counter top", "hob")
dim("h_plinth", (HX + 160, HY, 0), (HX + 160, HY, PLINTH), f"{PLINTH}", "hob")
# sink run: raised slab height to the right of the washing machine, and the step between the two counters
dim("hs_raised", (SXD, ROOM_D - 230, 0), (SXD, ROOM_D - 230, RAISED_TOP), f"{RAISED_TOP} slab top (check)", "sink",
    left=True)
dim("hs_step", (SXD, wm_y0 - 40, COUNTER_H), (SXD, wm_y0 - 40, RAISED_TOP), f"{RAISED_TOP - COUNTER_H} step", "sink",
    left=True)
dim("hs_counter", (SXD, DEPTH + 60, 0), (SXD, DEPTH + 60, COUNTER_H), f"{COUNTER_H}", "sink")
# sink-wall upper cabinets: heights at the back-wall end, in front of the shutters
UXD, UY = ROOM_W - WALL_D - 40, sum(w for _, w in SINK_WALL) - 120
y = 0
for i, (kind, w) in enumerate(SINK_WALL):    # each piece: tall cabinet and cover heights near its left edge
    if kind != "filler":
        py = max(y, WALL_D) + 60
        dim(f"hs_tall{i}", (UXD, py, OZ1), (UXD, py, LZ1), f"{LZ1 - OZ1}", "sink")
        dim(f"hs_cover{i}", (UXD, py, LZ1), (UXD, py, CEIL), f"{CEIL - LZ1}", "sink")
    y += w
dim("hs_open", (UXD, WALL_D + 60, WALL_Z0), (UXD, WALL_D + 60, OZ1), f"{OPEN_H} open shelf", "sink")
dim("hs_upper", (UXD, UY + 90, WALL_Z0), (UXD, UY + 90, CEIL), f"{UPPER_TOTAL} total to ceiling", "sink", left=True)
dim("hs_gap", (UXD, UY, RAISED_TOP), (UXD, UY, WALL_Z0), f"{WALL_Z0 - RAISED_TOP} above slab", "sink", left=True)
WY = TOWER_D + 40
TZ1 = WALL_Z0 + TOWER_H
dim("h_gap", (HX, WY, COUNTER_H), (HX, WY, WALL_Z0), f"{WALL_Z0 - COUNTER_H}", "hob")
dim("h_tower", (HX, WY, WALL_Z0), (HX, WY, TZ1), f"{TOWER_H} oven + microwave", "hob")
dim("h_toptower", (HX, WY, TZ1), (HX, WY, LZ1), f"{LZ1 - TZ1} cabinet", "hob")
RX = HOB_WALL_END - 50                    # the ordinary wall unit and loft, right of the chimney
dim("h_wall", (RX, WY, WALL_Z0), (RX, WY, WZ1), f"{WALL_H} wall unit", "hob", left=True)
dim("h_loft", (RX, WY, WZ1), (RX, WY, LZ1), f"{LOFT_H} loft", "hob", left=True)
UX = HOB_WALL[0][1] + HOB_WALL[1][1] + 40   # just right of the chimney, label over the chimney loft
dim("h_upper", (UX, WY, WALL_Z0), (UX, WY, CEIL), f"{UPPER_TOTAL} total to ceiling", "hob", left=True)

# wall units: widths just under the units
WZD = WALL_Z0 - 60
x = 0
for i, (kind, w) in enumerate(HOB_WALL):
    txt = f"{w} chimney" if kind == "chimney" else f"{w}"
    dim(f"wall_hob{i}", (x, WY, WZD), (x + w, WY, WZD), txt, "hob"); x += w
dim("wall_hobcorner", (x, WY, WZD), (ROOM_W, WY, WZD), f"{ROOM_W - x}", "hob")
SWX = ROOM_W - WALL_D - 40
y = 0
for i, (kind, w) in enumerate(SINK_WALL):
    a0 = max(y, WALL_D)
    txt = f"{w} glass" if kind == "glass2" else f"{w} (from wall)" if i == 0 else f"{w}"
    z = WZD - 90 if kind == "filler" or i == 0 else WZD
    dim(f"wall_sink{i}", (SWX, a0, z), (SWX, y + w, z), txt, "sink"); y += w

# keep the red dims out of the glossy shutters' reflections
for o in bpy.data.objects:
    if o.name.startswith("Dim_"):
        o.visible_glossy = False

# text as mesh so it survives the .glb export
for o in DIM_TEXT:
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True); bpy.context.view_layer.objects.active = o
    bpy.ops.object.convert(target="MESH")

# --- lighting and render -----------------------------------------------------------------------------------------
lt = bpy.data.lights.new("CeilingPanel", "AREA"); lt.energy = 110; lt.size = 0.6; lt.color = (1.0, 0.95, 0.88)
lo = bpy.data.objects.new("CeilingPanel", lt); lo.location = (m(900), -m(1400), m(CEIL - 40)); coll("Lights").objects.link(lo)
for name, loc in (("UnderCabHob", (900, 250, WALL_Z0 - 30)), ("UnderCabSink", (ROOM_W - 250, 1500, WALL_Z0 - 30))):
    l2 = bpy.data.lights.new(name, "AREA"); l2.energy = 40; l2.shape = "RECTANGLE"; l2.size = 1.2; l2.size_y = 0.08
    l2.color = (1.0, 0.82, 0.6)
    o2 = bpy.data.objects.new(name, l2); o2.location = (m(loc[0]), -m(loc[1]), m(loc[2])); coll("Lights").objects.link(o2)
    if name == "UnderCabSink":
        o2.rotation_euler = (0, 0, math.pi / 2); l2.size = 2.4

world = bpy.data.worlds.new("World"); scene.world = world; world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (*srgb("#DCD6CC"), 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.3

scene.render.engine = "CYCLES"
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "METAL"; prefs.get_devices()
    for d in prefs.devices:
        d.use = True
    scene.cycles.device = "GPU"
except Exception:
    pass
scene.cycles.samples = int(opt("--samples", 96)); scene.cycles.use_denoising = True
scene.cycles.preview_samples = 16; scene.cycles.use_preview_denoising = True   # if someone flips the viewport to Cycles
scene.eevee.use_raytracing = True; scene.eevee.taa_render_samples = 64; scene.eevee.taa_samples = 16
scene.view_settings.view_transform = "AgX"; scene.view_settings.look = "AgX - Medium High Contrast"; scene.view_settings.exposure = -0.4
RES = int(opt("--res", 1600))


def look_at(cam, target):
    d = Vector(target) - cam.location
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def hide(names, state):
    for o in scene.objects:
        if any(o.name.startswith(n) for n in names):
            o.hide_render = state


SHOTS = {
    # name: (camera mm, target mm, lens, aspect w/h, objects hidden)
    "hob": ((850, 2850, 1500), (850, 0, 1250), 16, (4, 5), ["Wall_Back", "Window", "Dim_"]),
    "sink": ((-700, 1650, 1450), (ROOM_W, 1650, 1250), 16, (1, 1), ["Wall_Left", "Dim_"]),
    "iso": ((-3600, 1700, 3400), (1000, 1450, 800), 22, (4, 3), ["Ceiling", "Wall_Left", "Dim_"]),
    "plan": ((ROOM_W / 2 - 150, ROOM_D / 2, 9000), (ROOM_W / 2 - 150, ROOM_D / 2, 0), None, (4, 5),
             ["Ceiling", "HobWall_", "SinkWall_", "Chimney", "LED_", "Splash_Chimney", "Dim_"]),
    # the same views with the measurements
    "sink_close": ((ROOM_W - 1050, 1450, 1650), (ROOM_W - 300, 1500, COUNTER_H - 60), 28, (4, 3), ["Wall_Left", "Dim_"]),
    "oven_close": ((420, 1500, 1550), (290, 0, 1780), 30, (4, 5), ["Wall_Left", "Wall_Back", "Window", "Dim_"]),
    "hob_dims": ((850, 2850, 1500), (850, 0, 1250), 16, (4, 5), ["Wall_Back", "Window", "Dim_wall_sink", "Dim_base_sink",
                                                                 "Dim_hs_", "Dim_top_sink", "Dim_top_raised"]),
    "sink_dims": ((-700, 1650, 1450), (ROOM_W, 1650, 1250), 16, (1, 1), ["Wall_Left", "Dim_base_hob", "Dim_wall_hob",
                                                                         "Dim_h_", "Dim_top_hob"]),
    "plan_dims": ((ROOM_W / 2 - 150, ROOM_D / 2, 9000), (ROOM_W / 2 - 150, ROOM_D / 2, 0), None, (4, 5),
                  ["Ceiling", "HobWall_", "SinkWall_", "Chimney", "LED_", "Splash_Chimney", "Dim_base", "Dim_wall", "Dim_h"]),
}

cam_data = bpy.data.cameras.new("Cam"); cam = bpy.data.objects.new("Cam", cam_data); scene.collection.objects.link(cam)
scene.camera = cam

bpy.context.preferences.filepaths.save_version = 0
scene.render.engine = "BLENDER_EEVEE"
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "kitchen.blend"))
scene.render.engine = "BLENDER_EEVEE" if opt("--engine", "cycles") == "eevee" else "CYCLES"
bpy.ops.export_scene.gltf(filepath=str(OUT / "kitchen.glb"), export_format="GLB", use_selection=False, export_apply=True)

for name in opt("--shots", ",".join(SHOTS)).split(","):
    loc, tgt, lens, (aw, ah), hidden = SHOTS[name]
    flip = lambda p: (m(p[0]), -m(p[1]), m(p[2]))
    cam.location = Vector(flip(loc)); look_at(cam, flip(tgt))
    if lens is None:
        cam_data.type = "ORTHO"; cam_data.ortho_scale = m(ROOM_D + 600)
    else:
        cam_data.type = "PERSP"; cam_data.lens = lens
    cam_data.clip_end = 50
    hide(hidden, True)
    scene.render.resolution_x = RES; scene.render.resolution_y = int(RES * ah / aw)
    scene.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    hide(hidden, False)
    print("wrote", scene.render.filepath)
