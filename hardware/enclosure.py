"""
Κουτί ράγας DIN (4 θέσεις) για το Smart Meter -- CadQuery.

Τρέξιμο:  python enclosure.py   ->  enclosure/*.step, *.stl, pcb/pcb_outline.dxf
Άξονες κουτιού: X κατά μήκος της ράγας (0..70), Y κατακόρυφα (0 κάτω .. 90 πάνω),
Z από την πίσω πλευρά (ράγα, Z=0) προς τα μπροστά.
"""
import os
import cadquery as cq
from layout import *

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "enclosure")
os.makedirs(OUT, exist_ok=True)
os.makedirs(os.path.join(HERE, "pcb"), exist_ok=True)

PCB_TOP = PCB_Z + PCB_T
TERM_Z = (PCB_TOP + 2.0, PCB_TOP + 8.5)       # ύψος ανοιγμάτων για καλώδια κλεμών


def box(x0, y0, z0, x1, y1, z1):
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def cyl_z(x, y, z0, z1, d):
    return cq.Workplane("XY").circle(d / 2).extrude(z1 - z0).translate((x, y, z0))


def part_box_x(ref):
    """Περιοχή X (στο κουτί) του σώματος ενός εξαρτήματος."""
    x0, _, x1, _ = PARTS[ref][2]
    return x0 + PCB_OFFSET[0], x1 + PCB_OFFSET[0]


# ====================================================================== PCB
def pcb_outline():
    n = CORNER_NOTCH
    pts = [(n, 0), (PCB_W - n, 0), (PCB_W - n, n), (PCB_W, n), (PCB_W, PCB_H - n),
           (PCB_W - n, PCB_H - n), (PCB_W - n, PCB_H), (n, PCB_H), (n, PCB_H - n),
           (0, PCB_H - n), (0, n), (n, n)]
    board = cq.Workplane("XY").polyline(pts).close().extrude(PCB_T)
    x0, y0, x1, y1 = ISO_SLOT
    board = board.cut(box(x0 - 1, y0, -1, x1, y1, PCB_T + 1))
    for cx, cy, w, h in ZIP_SLOTS:
        board = board.cut(cq.Workplane("XY").slot2D(h, w, 90).extrude(PCB_T + 2)
                          .translate((cx, cy, -1)))
    return board


# ===================================================================== ΒΑΣΗ
def make_base():
    base = box(0, 0, 0, BOX_W, BOX_H, BASE_D)
    base = base.cut(box(WALL, WALL, WALL, BOX_W - WALL, BOX_H - WALL, BASE_D + 1))
    base = base.edges("|Z").fillet(1.5)

    # Κολόνες για τις βίδες του καπακιού (M3 αυτοδιάτρητες, οπή 2.6)
    for x, y in SCREW_POS:
        base = base.union(cyl_z(x, y, WALL - 0.1, BASE_D, 6.0))
        base = base.cut(cyl_z(x, y, BASE_D - 16, BASE_D + 1, 2.6))

    # Ράφια όπου ακουμπάει η PCB
    base = base.union(box(WALL - 0.1, 12, WALL - 0.1, PCB_OFFSET[0] + 1.5, 78, PCB_Z))
    base = base.union(box(PCB_OFFSET[0] + PCB_W - 1.5, 12, WALL - 0.1, BOX_W - WALL + 0.1, 78, PCB_Z))
    base = base.union(box(12, PCB_OFFSET[1] + PCB_H - 1.5, WALL - 0.1, 58, BOX_H - WALL + 0.1, PCB_Z))

    # --- Ανοίγματα πάνω τοιχώματος: καλώδια 230V προς J1
    a, b = part_box_x("J1")
    base = base.cut(box(a + 1, BOX_H - WALL - 1, TERM_Z[0], b - 1, BOX_H + 1, TERM_Z[1]))

    # --- Ανοίγματα κάτω τοιχώματος: κλέμα 5V (J3) και κλέμα δαγκάνας (J5)
    for ref in ("J3", "J5"):
        a, b = part_box_x(ref)
        base = base.cut(box(a + 1, -1, TERM_Z[0], b - 1, WALL + 1, TERM_Z[1]))
    # USB-C του ESP32 (για προγραμματισμό)
    ex = (ESP_BOARD[0] + ESP_BOARD[2]) / 2 + PCB_OFFSET[0]
    uz = PCB_TOP + ESP_HEADER_H + 1.6 + 1.6
    base = base.cut(cq.Workplane("XZ").rect(13.5, 8.0).extrude(-(WALL + 2))
                    .edges("|Y").fillet(2.5).translate((ex, -1, uz)))

    # --- Κούμπωμα ράγας DIN (TS35) στην πίσω πλευρά (Z < 0)
    rail_top = RAIL_CENTER_Y + 17.5
    rail_bot = RAIL_CENTER_Y - 17.5
    # Σταθερό άγκιστρο πάνω
    base = base.union(box(18, rail_top + 0.3, -2.8, 52, rail_top + 3.5, 0.1))
    base = base.union(box(18, rail_top - 2.2, -2.8, 52, rail_top + 3.5, -1.3))
    # Ελατήριο κάτω: δοκός που λυγίζει προς τα κάτω (-Y) + δόντι πίσω από τη ράγα
    base = base.union(box(14, rail_bot - 8, -2.8, 18, rail_bot - 3.5, 0.1))      # στήριγμα αριστερά
    base = base.union(box(52, rail_bot - 8, -2.8, 56, rail_bot - 3.5, 0.1))      # στήριγμα δεξιά
    base = base.union(box(18 - 0.1, rail_bot - 8, -2.8, 52 + 0.1, rail_bot - 6.5, -1.3))  # δοκός 1.5mm
    tooth = box(30, rail_bot - 6.5, -2.8, 40, rail_bot + 2.3, -1.3)
    tooth = tooth.faces(">Y").edges("<Z").chamfer(1.2)                          # λοξότμηση για κούμπωμα
    base = base.union(tooth)
    base = base.union(box(32, rail_bot - 14, -2.8, 38, rail_bot - 8 + 0.1, -1.3))  # λαβή για κατσαβίδι
    base = base.union(box(32, rail_bot - 14, -2.8, 38, rail_bot - 12.5, -0.0))
    return base


# ================================================================== ΚΑΠΑΚΙ
def make_cover():
    z0 = BASE_D
    cover = box(0, 0, z0, BOX_W, BOX_H, z0 + COVER_T).edges("|Z").fillet(1.5)
    ny0, ny1 = (BOX_H - NOSE_H) / 2, (BOX_H + NOSE_H) / 2
    nose = box(0, ny0, z0, BOX_W, ny1, z0 + COVER_T + NOSE_D)
    nose = nose.edges("|Z").fillet(1.5).faces(">Z").edges().fillet(2.0)
    nose = nose.cut(box(WALL, ny0 + WALL, z0 - 1, BOX_W - WALL, ny1 - WALL, z0 + COVER_T + NOSE_D - WALL))
    cover = cover.union(nose).cut(box(WALL, ny0 + WALL, z0 - 1, BOX_W - WALL, ny1 - WALL, z0 + COVER_T))

    # Πατούρα που κεντράρει το καπάκι μέσα στη βάση
    rim = box(WALL + 0.25, WALL + 0.25, z0 - 3, BOX_W - WALL - 0.25, BOX_H - WALL - 0.25, z0 + 0.1)
    rim = rim.cut(box(WALL + 1.45, WALL + 1.45, z0 - 4, BOX_W - WALL - 1.45, BOX_H - WALL - 1.45, z0 + 1))
    for x, y in SCREW_POS:
        rim = rim.cut(cyl_z(x, y, z0 - 4, z0 + 1, 8.0))
    cover = cover.union(rim)

    # Οπές βιδών M3 με φρεζάτο
    for x, y in SCREW_POS:
        cover = cover.cut(cyl_z(x, y, z0 - 4, z0 + COVER_T + 1, 3.4))
        cover = cover.cut(cq.Workplane("XY").circle(3.2).workplane(offset=1.7).circle(1.7)
                          .loft().rotate((0, 0, 0), (1, 0, 0), 180)
                          .translate((x, y, z0 + COVER_T + 0.01)))

    # Τρύπες για το κατσαβίδι πάνω από τις βίδες των κλεμών (στους "ώμους")
    for ref in ("J1", "J2", "J3", "J5"):
        a, b = part_box_x(ref)
        _, y0, _, y1 = PARTS[ref][2]
        yc = (y0 + y1) / 2 + PCB_OFFSET[1]
        cover = cover.cut(cq.Workplane("XY").slot2D(b - a - 2, 5.0).extrude(COVER_T + 2)
                          .translate(((a + b) / 2, yc, z0 - 1)))

    # Κολονάκια που πατάνε την PCB πάνω στα ράφια
    for x, y in [(PCB_OFFSET[0] + 1.5, 60.0), (PCB_OFFSET[0] + PCB_W - 1.5, 18.0)]:
        cover = cover.union(cyl_z(x, y, PCB_TOP + 0.3, z0 + 0.1, 4.0))

    # Επιγραφή στη μύτη
    front = z0 + COVER_T + NOSE_D
    txt = (cq.Workplane("XY").workplane(offset=front - 0.6)
           .center(BOX_W / 2, BOX_H / 2 + 4).text("SMART METER", 7.0, 1.0, kind="bold"))
    cover = cover.cut(txt)
    txt2 = (cq.Workplane("XY").workplane(offset=front - 0.6)
            .center(BOX_W / 2, BOX_H / 2 - 7).text("ESP32-C3", 5.0, 1.0))
    cover = cover.cut(txt2)
    # Αερισμός στη μύτη (πάνω/κάτω)
    for i in range(6):
        x = 13 + i * 9
        for y in (ny0, ny1):
            cover = cover.cut(box(x, y - 3, front - 12, x + 3, y + 3, front - 4))
    return cover


# ======================================================== ΕΙΚΟΝΙΚΗ PCB (fit)
def make_pcb_mock():
    ox, oy = PCB_OFFSET
    board = pcb_outline().translate((ox, oy, PCB_Z))
    parts = cq.Workplane("XY")
    for ref, (_, _, (x0, y0, x1, y1), h) in PARTS.items():
        parts = parts.union(box(x0 + ox, y0 + oy, PCB_TOP, x1 + ox, y1 + oy, PCB_TOP + h))
    zx0, zy0, zx1, zy1 = ZMPT_ZONE
    module = box(zx0 + ox, zy0 + oy, PCB_TOP, zx1 + ox, zy1 + oy, PCB_TOP + ZMPT_HEIGHT)
    ex0, ey0, ex1, ey1 = ESP_BOARD
    hz = PCB_TOP + ESP_HEADER_H
    esp = box(ex0 + ox, ey0 + oy, hz, ex1 + ox, ey1 + oy, hz + 1.6)
    esp = esp.union(box(ex0 + ox + 4.5, ey0 + oy - 1.2, hz + 1.6, ex1 + ox - 4.5, ey0 + oy + 6.3, hz + 4.8))
    for cx in ESP_COL_X:
        esp = esp.union(box(cx - 1.27 + ox, ESP_PIN_Y0 - 1.27 + oy, PCB_TOP,
                            cx + 1.27 + ox, ESP_PIN_Y0 + 7 * ESP_PITCH + 1.27 + oy, hz))
    return board, parts, module, esp


if __name__ == "__main__":
    base = make_base()
    cover = make_cover()
    board, parts, module, esp = make_pcb_mock()

    for name, obj in (("base", base), ("cover", cover)):
        cq.exporters.export(obj, os.path.join(OUT, f"smart_meter_{name}.step"))
        cq.exporters.export(obj, os.path.join(OUT, f"smart_meter_{name}.stl"), tolerance=0.02, angularTolerance=0.1)

    asm = cq.Assembly(name="smart_meter")
    asm.add(base, name="base", color=cq.Color(0.92, 0.92, 0.9))
    asm.add(cover, name="cover", color=cq.Color(0.85, 0.85, 0.82, 0.6))
    asm.add(board, name="pcb", color=cq.Color(0.1, 0.45, 0.2))
    asm.add(parts, name="parts", color=cq.Color(0.2, 0.4, 0.8))
    asm.add(module, name="zmpt101b", color=cq.Color(0.1, 0.3, 0.75))
    asm.add(esp, name="esp32c3", color=cq.Color(0.15, 0.15, 0.15))
    asm.save(os.path.join(OUT, "smart_meter_assembly.step"))

    # Περίγραμμα PCB για το Fusion Electronics
    cq.exporters.export(pcb_outline().faces("<Z").wires().toPending().extrude(0.01).faces("<Z"),
                        os.path.join(HERE, "pcb", "pcb_outline.dxf"))

    # Έλεγχος συγκρούσεων / interference check
    inner = [("parts", parts), ("module", module), ("esp", esp), ("board", board)]
    for sname, shell in (("base", base), ("cover", cover)):
        for pname, p in inner:
            v = shell.intersect(p).val().Volume() if shell.intersect(p).vals() else 0.0
            print(f"overlap {sname:5s} x {pname:6s}: {v:8.2f} mm3")
    print("done")
