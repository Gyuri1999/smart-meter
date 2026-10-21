"""
PCB του Smart Meter: δρομολογημένη πλακέτα σε μορφή EAGLE (.brd) για το Fusion Electronics,
με έλεγχο αποστάσεων / συνδεσιμότητας και εικόνες προεπισκόπησης.

Τρέξιμο:  python pcb_gen.py   (χρειάζεται: pip install shapely pillow)
Έξοδος :  pcb/smart_meter.brd, pcb/pcb_top.png, pcb/pcb_bottom.png
"""
import os
from xml.sax.saxutils import escape
from layout import *

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "pcb")
os.makedirs(OUT, exist_ok=True)

TOP, BOT = 1, 16
MAINS_NETS = {"L_IN", "L_FUSED", "N"}
MAINS_W, PWR_W, SIG_W = 1.5, 0.8, 0.4

# ============================================================ ΠΑΚΕΤΑ / FOOTPRINTS
# Κάθε pad: (name, x, y, drill, diameter, square). Αρχή = pin 1.
ESP_PADS = ([(n, 0.0, i * ESP_PITCH) for i, n in enumerate(["5V", "GND", "3V3", "IO4", "IO3", "IO2", "IO1", "IO0"])] +
            [(n, ESP_COL_X[1] - ESP_COL_X[0], i * ESP_PITCH)
             for i, n in enumerate(["IO5", "IO6", "IO7", "IO8", "IO9", "IO10", "IO20", "IO21"])])

PACKAGES = {
    "ESP32C3_SUPERMINI": {
        "pads": [(n, x, y, 1.0, 1.7, n == "5V") for n, x, y in ESP_PADS],
        "silk": [("rect", ESP_BOARD[0] - ESP_COL_X[0], ESP_BOARD[1] - ESP_PIN_Y0,
                  ESP_BOARD[2] - ESP_COL_X[0], ESP_BOARD[3] - ESP_PIN_Y0),
                 ("rect", 3.0, -3.6, 12.24, 1.0)],                       # USB-C
        "text": [(4.0, 8.0, "ESP32-C3"), (5.6, -1.6, "USB")],
    },
    # Κλέμα 5.08: άνοιγμα καλωδίου προς +y (UP) ή -y (DOWN)
    "TERM2_UP": {"pads": [("1", 0, 0, 1.3, 2.6, True), ("2", 5.08, 0, 1.3, 2.6, False)],
                 "silk": [("rect", -2.5, -4.0, 7.58, 6.0), ("line", -2.5, 4.5, 7.58, 4.5)]},
    "TERM2_DOWN": {"pads": [("1", 0, 0, 1.3, 2.6, True), ("2", 5.08, 0, 1.3, 2.6, False)],
                   "silk": [("rect", -2.5, -6.0, 7.58, 4.0), ("line", -2.5, -4.5, 7.58, -4.5)]},
    "FUSE_TR5": {"pads": [("1", 0, 0, 1.0, 2.4, True), ("2", 5.08, 0, 1.0, 2.4, False)],
                 "silk": [("circle", 2.54, 0, 4.2)]},
    "HDR1X3": {"pads": [(str(i + 1), i * 2.54, 0, 1.0, 1.7, i == 0) for i in range(3)],
               "silk": [("rect", -1.27, -1.27, 6.35, 1.27)]},
    "R_AXIAL_400": {"pads": [("1", 0, 0, 0.9, 1.8, True), ("2", 10.16, 0, 0.9, 1.8, False)],
                    "silk": [("rect", 2.0, -1.0, 8.16, 1.0), ("line", 0.9, 0, 2.0, 0), ("line", 8.16, 0, 9.26, 0)]},
    "CPOL_D5_P2": {"pads": [("+", 0, 0, 0.8, 1.6, True), ("-", 2.0, 0, 0.8, 1.6, False)],
                   "silk": [("circle", 1.0, 0, 2.6)], "text": [(-2.6, 1.6, "+")]},
    "DO41_400": {"pads": [("K", 0, 0, 1.1, 2.0, True), ("A", 10.16, 0, 1.1, 2.0, False)],
                 "silk": [("rect", 2.0, -1.3, 8.16, 1.3), ("rect", 2.4, -1.3, 2.9, 1.3),
                          ("line", 1.0, 0, 2.0, 0), ("line", 8.16, 0, 9.16, 0)]},
}

# ref -> (package, value, x, y) -- x,y = θέση του pin 1 (από το layout.py)
ELEMENTS = {"U1": ("ESP32C3_SUPERMINI", "ESP32-C3 SuperMini", ESP_COL_X[0], ESP_PIN_Y0)}
PKG_OF = {"J1": ("TERM2_UP", "230V L N"), "J2": ("TERM2_UP", "ZMPT AC"), "F1": ("FUSE_TR5", "100mA T"),
          "J6": ("HDR1X3", "ZMPT VCC OUT GND"), "R1": ("R_AXIAL_400", "10k"), "R2": ("R_AXIAL_400", "10k"),
          "C1": ("CPOL_D5_P2", "10uF"), "D1": ("DO41_400", "1N5819"),
          "J5": ("TERM2_DOWN", "SCT-013"), "J3": ("TERM2_DOWN", "5V IN")}
for ref, (pkg, val) in PKG_OF.items():
    x, y = PARTS[ref][1][0]
    ELEMENTS[ref] = (pkg, val, x, y)

SIGNALS = {
    "L_IN": [("J1", "1"), ("F1", "1")],
    "L_FUSED": [("F1", "2"), ("J2", "1")],
    "N": [("J1", "2"), ("J2", "2")],
    "+5V_IN": [("J3", "1"), ("D1", "A")],
    "+5V": [("D1", "K"), ("U1", "5V")],
    "+3V3": [("U1", "3V3"), ("R1", "1"), ("J6", "1")],
    "GND": [("J3", "2"), ("U1", "GND"), ("R2", "1"), ("C1", "-"), ("J6", "3")],
    "BIAS": [("R1", "2"), ("R2", "2"), ("C1", "+"), ("J5", "2")],
    "ADC_I": [("U1", "IO0"), ("J5", "1")],
    "ADC_V": [("U1", "IO2"), ("J6", "2")],
}

# ============================================================ ΔΡΟΜΟΛΟΓΗΣΗ / ROUTING
# (net, layer, width, [points])
TRACKS = [
    # --- 230V
    ("L_IN", TOP, MAINS_W, [(10, 78), (10, 68.5), (20.46, 68.5)]),
    ("L_FUSED", TOP, MAINS_W, [(25.54, 68.5), (29, 68.5), (29, 78)]),
    ("N", BOT, MAINS_W, [(15.08, 78), (15.08, 63.5), (34.08, 63.5), (34.08, 78)]),
    # --- 5V
    ("+5V_IN", TOP, PWR_W, [(50.5, 6), (52, 13)]),
    ("+5V", BOT, PWR_W, [(41.84, 13), (41.84, 2.5), (7, 2.5), (7, 5.2)]),
    # --- GND
    ("GND", TOP, SIG_W, [(7, 7.74), (8.5, 6.47), (24, 6.47)]),               # ανάμεσα στα pins του ESP
    ("GND", TOP, 0.6, [(24, 6.47), (24, 1.5), (55.58, 1.5), (55.58, 6)]),
    ("GND", TOP, 0.6, [(55.58, 6), (55.58, 22.5), (53, 25), (51.54, 25)]),
    ("GND", TOP, 0.6, [(32, 36), (32, 39), (24, 44)]),
    ("GND", BOT, 0.6, [(32, 36), (32, 13), (33, 12)]),
    ("GND", TOP, 0.6, [(33, 12), (33, 1.5)]),
    # --- 3V3
    ("+3V3", TOP, 0.6, [(7, 10.28), (2.7, 10.28), (2.7, 53), (36, 53), (36, 23.5), (46.46, 23.5), (46.46, 25)]),
    ("+3V3", TOP, 0.6, [(24, 53), (24, 50)]),
    # --- Τάση (ZMPT OUT -> GPIO2)
    ("ADC_V", TOP, SIG_W, [(7, 17.9), (3.9, 17.9), (3.9, 33), (34.5, 33), (34.5, 21), (49, 21), (49, 25)]),
    # --- Ρεύμα (SCT tip -> GPIO0)
    ("ADC_I", BOT, SIG_W, [(7, 22.98), (4.6, 22.98), (4.6, 31), (25, 31), (25, 12), (30.5, 6)]),
    # --- Bias 1.65V
    ("BIAS", TOP, SIG_W, [(34.16, 50), (34.16, 44)]),
    ("BIAS", BOT, SIG_W, [(34.16, 44), (34.16, 40), (30, 36), (30, 10), (35.58, 6)]),
]
VIAS = [("GND", 33, 12, 0.4, 0.8)]

# Περιοχές χωρίς χαλκό (tRestrict/bRestrict)
RESTRICT = [ZMPT_ZONE, ANTENNA_KEEPOUT]

# Ετικέτες silkscreen (x, y, size, text)
SILK_TEXT = [
    (8.6, 71.0, 1.3, "L"), (13.7, 71.0, 1.3, "N"), (2.0, 74.0, 1.2, "230V"),
    (27.6, 71.0, 1.1, "L"), (32.7, 71.0, 1.1, "N"), (27.0, 81.3, 1.0, "ZMPT AC"),
    (18.5, 74.0, 1.0, "F1 100mA T"),
    (1.5, 58.0, 1.0, "!! 230V ABOVE SLOT"),
    (45.0, 26.8, 0.9, "VCC OUT GND"),
    (29.0, 11.0, 1.0, "TIP"), (34.0, 11.0, 1.0, "SLV"), (28.5, 12.6, 1.1, "SCT-013"),
    (49.0, 11.0, 1.0, "+5V"), (54.0, 11.0, 1.0, "GND"),
    (25.0, 55.0, 1.4, "SMART METER v1"),
    (41.0, 29.0, 1.0, "ZMPT101B module"),
]


# ============================================================ ΓΕΩΜΕΤΡΙΑ
def outline_segments():
    """Γραμμές/τόξα του περιγράμματος: [('line', x1,y1,x2,y2) | ('arc', x1,y1,x2,y2,curve)]"""
    n = CORNER_NOTCH
    sx0, sy0, sx1, sy1 = ISO_SLOT
    pts = [(n, 0), (PCB_W - n, 0), (PCB_W - n, n), (PCB_W, n), (PCB_W, PCB_H - n), (PCB_W - n, PCB_H - n),
           (PCB_W - n, PCB_H), (n, PCB_H), (n, PCB_H - n), (0, PCB_H - n), (0, sy1), (sx1, sy1), (sx1, sy0),
           (0, sy0), (0, n), (n, n), (n, 0)]
    segs = [("line", *pts[i], *pts[i + 1]) for i in range(len(pts) - 1)]
    for cx, cy, w, h in ZIP_SLOTS:
        r, hs = w / 2, h / 2 - w / 2
        segs += [("line", cx - r, cy - hs, cx - r, cy + hs), ("arc", cx - r, cy + hs, cx + r, cy + hs, -180),
                 ("line", cx + r, cy + hs, cx + r, cy - hs), ("arc", cx + r, cy - hs, cx - r, cy - hs, -180)]
    return segs


def pad_positions():
    out = []   # (ref, pad, x, y, drill, dia, square)
    for ref, (pkg, _, ex, ey) in ELEMENTS.items():
        for name, px, py, drill, dia, sq in PACKAGES[pkg]["pads"]:
            out.append((ref, name, ex + px, ey + py, drill, dia, sq))
    return out


# ============================================================ EAGLE .brd
LAYERS = [(1, "Top", 4), (16, "Bottom", 1), (17, "Pads", 2), (18, "Vias", 2), (19, "Unrouted", 6),
          (20, "Dimension", 24), (21, "tPlace", 7), (22, "bPlace", 7), (23, "tOrigins", 15), (24, "bOrigins", 15),
          (25, "tNames", 7), (26, "bNames", 7), (27, "tValues", 7), (28, "bValues", 7), (29, "tStop", 7),
          (30, "bStop", 7), (31, "tCream", 7), (32, "bCream", 7), (35, "tGlue", 7), (36, "bGlue", 7),
          (39, "tKeepout", 4), (40, "bKeepout", 1), (41, "tRestrict", 4), (42, "bRestrict", 1),
          (43, "vRestrict", 2), (44, "Drills", 7), (45, "Holes", 7), (46, "Milling", 3), (47, "Measures", 7),
          (48, "Document", 7), (49, "Reference", 7), (51, "tDocu", 7), (52, "bDocu", 7)]


def f(v):
    return f"{v:.4f}".rstrip("0").rstrip(".")


def silk_xml(items, layer=21):
    o = []
    for it in items:
        if it[0] == "rect":
            _, x0, y0, x1, y1 = it
            for a, b, c, d in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)):
                o.append(f'<wire x1="{f(a)}" y1="{f(b)}" x2="{f(c)}" y2="{f(d)}" width="0.2" layer="{layer}"/>')
        elif it[0] == "line":
            _, a, b, c, d = it
            o.append(f'<wire x1="{f(a)}" y1="{f(b)}" x2="{f(c)}" y2="{f(d)}" width="0.2" layer="{layer}"/>')
        elif it[0] == "circle":
            _, x, y, r = it
            o.append(f'<circle x="{f(x)}" y="{f(y)}" radius="{f(r)}" width="0.2" layer="{layer}"/>')
    return o


def write_brd(path):
    o = ['<?xml version="1.0" encoding="utf-8"?>', '<!DOCTYPE eagle SYSTEM "eagle.dtd">',
         '<eagle version="9.6.2">', '<drawing>', '<settings>', '<setting alwaysvectorfont="no"/>',
         '<setting verticaltext="up"/>', '</settings>',
         '<grid distance="0.1" unitdist="mm" unit="mm" style="lines" multiple="1" display="no" '
         'altdistance="0.01" altunitdist="mm" altunit="mm"/>', '<layers>']
    for num, name, color in LAYERS:
        o.append(f'<layer number="{num}" name="{name}" color="{color}" fill="1" visible="yes" active="yes"/>')
    o += ['</layers>', '<board>', '<plain>']
    for s in outline_segments():
        if s[0] == "line":
            o.append(f'<wire x1="{f(s[1])}" y1="{f(s[2])}" x2="{f(s[3])}" y2="{f(s[4])}" width="0" layer="20"/>')
        else:
            o.append(f'<wire x1="{f(s[1])}" y1="{f(s[2])}" x2="{f(s[3])}" y2="{f(s[4])}" width="0" layer="20" curve="{s[5]}"/>')
    for x0, y0, x1, y1 in RESTRICT:
        for layer in (41, 42):
            o.append(f'<polygon width="0.2" layer="{layer}">' +
                     "".join(f'<vertex x="{f(x)}" y="{f(y)}"/>' for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))) +
                     "</polygon>")
    o += silk_xml([("rect", *ZMPT_ZONE)], 21)
    for x, y, size, t in SILK_TEXT:
        o.append(f'<text x="{f(x)}" y="{f(y)}" size="{f(size)}" layer="21" font="vector" ratio="12">{escape(t)}</text>')
    o += ['</plain>', '<libraries>', '<library name="smart_meter">',
          '<description>Smart Meter ESP32-C3 footprints</description>', '<packages>']
    for name, p in PACKAGES.items():
        o.append(f'<package name="{name}">')
        for pn, px, py, drill, dia, sq in p["pads"]:
            shape = ' shape="square"' if sq else ""
            o.append(f'<pad name="{escape(pn)}" x="{f(px)}" y="{f(py)}" drill="{f(drill)}" diameter="{f(dia)}"{shape}/>')
        o += silk_xml(p["silk"])
        for tx, ty, t in p.get("text", []):
            o.append(f'<text x="{f(tx)}" y="{f(ty)}" size="1" layer="21" font="vector">{escape(t)}</text>')
        o.append('<text x="0" y="-2.8" size="1.1" layer="25" font="vector">&gt;NAME</text>')
        o.append('<text x="0" y="-4.2" size="0.9" layer="27" font="vector">&gt;VALUE</text>')
        o.append("</package>")
    o += ['</packages>', '</library>', '</libraries>', '<attributes>', '</attributes>', '<variantdefs>',
          '</variantdefs>', '<classes>', '<class number="0" name="default" width="0" drill="0">', '</class>',
          '<class number="1" name="mains" width="1.5" drill="0">', '<clearance class="1" value="3"/>', '</class>',
          '</classes>', '<designrules name="smart_meter">',
          '<param name="mdWireWire" value="0.2mm"/>', '<param name="mdWirePad" value="0.2mm"/>',
          '<param name="mdWireVia" value="0.2mm"/>', '<param name="mdPadPad" value="0.2mm"/>',
          '<param name="mdCopperDimension" value="0.4mm"/>', '<param name="msWidth" value="0.2mm"/>',
          '<param name="msDrill" value="0.3mm"/>', '</designrules>', '<autorouter>', '</autorouter>', '<elements>']
    for ref, (pkg, val, x, y) in ELEMENTS.items():
        o.append(f'<element name="{ref}" library="smart_meter" package="{pkg}" value="{escape(val)}" x="{f(x)}" y="{f(y)}"/>')
    o += ['</elements>', '<signals>']
    for net, refs in SIGNALS.items():
        cls = ' class="1"' if net in MAINS_NETS else ""
        o.append(f'<signal name="{escape(net)}"{cls}>')
        for ref, pad in refs:
            o.append(f'<contactref element="{ref}" pad="{escape(pad)}"/>')
        for tnet, layer, w, pts in TRACKS:
            if tnet != net:
                continue
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                o.append(f'<wire x1="{f(x1)}" y1="{f(y1)}" x2="{f(x2)}" y2="{f(y2)}" width="{f(w)}" layer="{layer}"/>')
        for vnet, x, y, drill, dia in VIAS:
            if vnet == net:
                o.append(f'<via x="{f(x)}" y="{f(y)}" extent="1-16" drill="{f(drill)}" diameter="{f(dia)}"/>')
        o.append("</signal>")
    o += ['</signals>', '</board>', '</drawing>', '</eagle>']
    open(path, "w", encoding="utf-8").write("\n".join(o) + "\n")


# ============================================================ ΕΛΕΓΧΟΣ / DRC
def run_checks():
    from shapely.geometry import Point, LineString, Polygon, box as sbox
    from shapely.ops import unary_union

    # Πλακέτα
    n = CORNER_NOTCH
    board = Polygon([(n, 0), (PCB_W - n, 0), (PCB_W - n, n), (PCB_W, n), (PCB_W, PCB_H - n), (PCB_W - n, PCB_H - n),
                     (PCB_W - n, PCB_H), (n, PCB_H), (n, PCB_H - n), (0, PCB_H - n), (0, n), (n, n)])
    board = board.difference(sbox(-1, ISO_SLOT[1], ISO_SLOT[2], ISO_SLOT[3]))
    for cx, cy, w, h in ZIP_SLOTS:
        board = board.difference(LineString([(cx, cy - h / 2 + w / 2), (cx, cy + h / 2 - w / 2)]).buffer(w / 2))

    pad_net = {(r, p): net for net, refs in SIGNALS.items() for r, p in refs}
    items = []   # (net, layers(set), geom, label)
    for ref, pad, x, y, drill, dia, sq in pad_positions():
        g = sbox(x - dia / 2, y - dia / 2, x + dia / 2, y + dia / 2) if sq else Point(x, y).buffer(dia / 2, 32)
        items.append((pad_net.get((ref, pad)), {TOP, BOT}, g, f"{ref}.{pad}"))
    for net, layer, w, pts in TRACKS:
        items.append((net, {layer}, LineString(pts).buffer(w / 2, 16), f"track {net} L{layer} {pts[0]}"))
    for net, x, y, drill, dia in VIAS:
        items.append((net, {TOP, BOT}, Point(x, y).buffer(dia / 2, 32), f"via {net} ({x},{y})"))

    errors = []
    # 1. Αποστάσεις μεταξύ διαφορετικών nets
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            n1, l1, g1, a = items[i]
            n2, l2, g2, b = items[j]
            if not (l1 & l2) or n1 == n2:
                continue
            m1, m2 = n1 in MAINS_NETS, n2 in MAINS_NETS
            need = 3.0 if (m1 != m2) else (2.0 if (m1 and m2) else 0.2)
            if m1 and m2 and a.startswith(("J1.", "J2.", "F1.")) and b.startswith(("J1.", "J2.", "F1.")):
                need = 2.0      # pads ίδιου εξαρτήματος 230V (κλέμα 5.08)
            d = g1.distance(g2)
            if d < need - 1e-6:
                errors.append(f"clearance {d:.2f} < {need} : {a}  <->  {b}")
    # 2. Μέσα στην πλακέτα, ≥0.4mm από την άκρη
    inner = board.buffer(-0.4)
    for net, layers, g, label in items:
        if not inner.buffer(1e-6).contains(g):
            errors.append(f"too close to edge / outside board: {label}")
    # 3. Χωρίς χαλκό σε ZMPT ζώνη και κεραία
    for x0, y0, x1, y1 in RESTRICT:
        r = sbox(x0, y0, x1, y1)
        for net, layers, g, label in items:
            if g.intersects(r):
                errors.append(f"copper in keep-out {x0, y0, x1, y1}: {label}")
    # 4. 230V: απόσταση από χαμηλή τάση μέσω σχισμής ≥ 3mm σε ευθεία
    mains = unary_union([g for net, _, g, _ in items if net in MAINS_NETS])
    lv = unary_union([g for net, _, g, _ in items if net and net not in MAINS_NETS])
    dmin = mains.distance(lv)
    if dmin < 6.0:
        errors.append(f"230V to low-voltage distance {dmin:.2f} mm")
    # 5. Συνδεσιμότητα: κάθε net ένα ενιαίο κομμάτι
    for net, refs in SIGNALS.items():
        mine = [(layers, g, label) for nn, layers, g, label in items if nn == net]
        parent = list(range(len(mine)))

        def find(k):
            while parent[k] != k:
                parent[k] = parent[parent[k]]
                k = parent[k]
            return k
        for i in range(len(mine)):
            for j in range(i + 1, len(mine)):
                if mine[i][0] & mine[j][0] and mine[i][1].intersects(mine[j][1]):
                    parent[find(i)] = find(j)
        groups = {find(k) for k in range(len(mine))}
        if len(groups) != 1:
            errors.append(f"net {net} not connected: {len(groups)} pieces")
    print(f"230V <-> low voltage min distance: {dmin:.2f} mm")
    print(f"checked {len(items)} copper items, {len(SIGNALS)} nets")
    return errors, board, items


# ============================================================ ΕΙΚΟΝΕΣ
def render(board, items, layer, path, mirror=False):
    from PIL import Image, ImageDraw, ImageFont
    K, M = 14, 30
    W, H = int(PCB_W * K + 2 * M), int(PCB_H * K + 2 * M)
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)

    def P(x, y):
        if mirror:
            x = PCB_W - x
        return (M + x * K, M + (PCB_H - y) * K)

    def poly(g, fill, outline=None):
        geoms = getattr(g, "geoms", [g])
        for gg in geoms:
            d.polygon([P(*c) for c in gg.exterior.coords], fill=fill, outline=outline)
            for hole in gg.interiors:
                d.polygon([P(*c) for c in hole.coords], fill="white")
    poly(board, (24, 92, 50), (10, 50, 25))
    from shapely.geometry import box as sbox
    zx = sbox(0, ISO_SLOT[3], 38, PCB_H).intersection(board)
    poly(zx, (70, 95, 40))
    copper_col = (200, 120, 40) if layer == TOP else (90, 140, 210)
    for net, layers, g, label in items:
        if layer in layers and not label.startswith(("via",)) and "." not in label.split()[0]:
            poly(g, copper_col)
    for net, layers, g, label in items:
        if label.startswith("via") or "." in label.split()[0]:
            poly(g, (215, 175, 60))
    for ref, pad, x, y, drill, dia, sq in pad_positions():
        r = drill / 2 * K
        cx, cy = P(x, y)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill="white")
    for net, x, y, drill, dia in VIAS:
        r = drill / 2 * K
        cx, cy = P(x, y)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill="white")
    if layer == TOP:
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 15)
        except OSError:
            font = ImageFont.load_default()
        for ref, (pkg, val, ex, ey) in ELEMENTS.items():
            for it in PACKAGES[pkg]["silk"]:
                if it[0] == "rect":
                    d.rectangle([P(ex + it[1], ey + it[4]), P(ex + it[3], ey + it[2])], outline="white", width=2)
                elif it[0] == "circle":
                    cx, cy = P(ex + it[1], ey + it[2])
                    rr = it[3] * K
                    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline="white", width=2)
            lx, ly = P(ex, ey - 2.8)
            d.text((lx, ly), ref, fill="white", font=font)
        x0, y0, x1, y1 = ZMPT_ZONE
        d.rectangle([P(x0, y1), P(x1, y0)], outline=(160, 200, 255), width=2)
        d.text(P(x0 + 3, (y0 + y1) / 2), "ZMPT101B", fill=(160, 200, 255), font=font)
    title = "TOP (component side)" if layer == TOP else "BOTTOM (seen from below)"
    d.text((M, 6), title, fill="black")
    img.save(path)


if __name__ == "__main__":
    write_brd(os.path.join(OUT, "smart_meter.brd"))
    errors, board, items = run_checks()
    render(board, items, TOP, os.path.join(OUT, "pcb_top.png"))
    render(board, items, BOT, os.path.join(OUT, "pcb_bottom.png"), mirror=True)
    if errors:
        print("ERRORS:")
        for e in errors:
            print("  ", e)
    else:
        print("DRC OK -- no errors")
