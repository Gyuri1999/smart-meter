"""Σχέδιο τοποθέτησης PCB (SVG) από το layout.py -> pcb/placement.svg"""
import os
from layout import *

K = 9.0                      # px ανά mm
MX, MY = 70, 80              # περιθώρια
W, H = 1180, PCB_H * K + 2 * MY + 40


def X(x): return MX + x * K
def Y(y): return MY + (PCB_H - y) * K


def rect(x0, y0, x1, y1, **a):
    attrs = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in a.items())
    return f'<rect x="{X(x0):.1f}" y="{Y(y1):.1f}" width="{(x1 - x0) * K:.1f}" height="{(y1 - y0) * K:.1f}" {attrs}/>'


def text(x, y, s, size=13, anchor="middle", fill="#111", weight=700):
    return f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" fill="{fill}" font-weight="{weight}">{s}</text>'


o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H:.0f}" width="{W}" height="{H:.0f}" '
     'font-family="Helvetica Neue, Helvetica, Arial, sans-serif">',
     f'<rect width="{W}" height="{H:.0f}" fill="#fff"/>']

# Περίγραμμα πλακέτας
n = CORNER_NOTCH
pts = [(n, 0), (PCB_W - n, 0), (PCB_W - n, n), (PCB_W, n), (PCB_W, PCB_H - n), (PCB_W - n, PCB_H - n),
       (PCB_W - n, PCB_H), (n, PCB_H), (n, PCB_H - n), (0, PCB_H - n), (0, n), (n, n)]
o.append('<polygon points="' + " ".join(f"{X(a):.1f},{Y(b):.1f}" for a, b in pts) +
         '" fill="#1f6b3a" stroke="#0d3b1e" stroke-width="2"/>')
# Ζώνη 230V
o.append(rect(0, ISO_SLOT[3], 38.0, PCB_H, fill="#ff6f00", fill_opacity="0.18"))
o.append(text(X(1.5), Y(63.5), "⚡ 230V ZONE", 13, "start", "#ffcc80"))
# Σχισμή απομόνωσης
x0, y0, x1, y1 = ISO_SLOT
o.append(rect(x0, y0, x1, y1, fill="#fff"))
o.append(text(X(19), Y(y0) + 18, "σχισμή απομόνωσης / isolation slot", 11, fill="#fff", weight=400))
# Antenna keep-out
a = ANTENNA_KEEPOUT
o.append(rect(*a, fill="none", stroke="#ffeb3b", stroke_width="1.5", stroke_dasharray="5 4"))
o.append(text(X((a[0] + a[2]) / 2), Y(a[3]) - 4, "χωρίς χαλκό / antenna keep-out", 10, fill="#ffeb3b", weight=400))
# ZMPT module
z = ZMPT_ZONE
o.append(rect(*z, fill="#1565c0", fill_opacity="0.55", stroke="#90caf9", stroke_width="2", stroke_dasharray="6 4"))
o.append(text(X((z[0] + z[2]) / 2), Y((z[1] + z[3]) / 2), "ZMPT101B", 15, fill="#fff"))
o.append(text(X((z[0] + z[2]) / 2), Y((z[1] + z[3]) / 2) + 18, "module (δεματικό)", 11, fill="#e3f2fd", weight=400))
o.append(text(X((z[0] + z[2]) / 2), Y(z[3]) + 16, "AC κλέμα ↑", 11, fill="#ffe0b2", weight=400))
o.append(text(X((z[0] + z[2]) / 2), Y(z[1]) - 6, "header ↓", 11, fill="#e3f2fd", weight=400))
for cx, cy, w, h in ZIP_SLOTS:
    o.append(rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, fill="#fff", rx="5"))
# ESP32
e = ESP_BOARD
o.append(rect(*e, fill="#2b2b2b", fill_opacity="0.85", stroke="#000", stroke_width="1.5"))
o.append(rect(e[0] + 4.5, e[1] - 1.2, e[2] - 4.5, e[1] + 6.3, fill="#cfcfcf"))
o.append(text(X((e[0] + e[2]) / 2), Y(e[1] + 2.5), "USB-C", 10, fill="#333"))
o.append(text(X((e[0] + e[2]) / 2), Y(14.5), "U1", 15, fill="#fff"))
o.append(text(X((e[0] + e[2]) / 2), Y(14.5) + 15, "ESP32-C3", 10, fill="#ddd", weight=400))
for cx, names, anchor, dx in ((ESP_COL_X[0], ESP_LEFT_PINS, "start", 9), (ESP_COL_X[1], ESP_RIGHT_PINS, "end", -9)):
    for i, nm in enumerate(names):
        py = ESP_PIN_Y0 + i * ESP_PITCH
        used = nm in ("5V", "GND", "3V3", "GPIO2", "GPIO0", "GPIO20", "GPIO21")
        o.append(f'<circle cx="{X(cx):.1f}" cy="{Y(py):.1f}" r="6" fill="#f4d03f"/>')
        o.append(text(X(cx) + dx, Y(py) + 3.5, nm.replace("GPIO", "G"), 8.5, anchor,
                      "#fff" if used else "#888", 700 if used else 400))
# Εξαρτήματα
for ref, (desc, pins, (x0, y0, x1, y1), h) in PARTS.items():
    mains = ref in ("J1", "F1", "J2")
    o.append(rect(x0, y0, x1, y1, fill="#e65100" if mains else "#3d5afe", fill_opacity="0.8", stroke="#fff", stroke_width="1.2", rx="3"))
    for i, (px, py) in enumerate(pins):
        o.append(f'<circle cx="{X(px):.1f}" cy="{Y(py):.1f}" r="5.5" fill="#f4d03f" stroke="#7a5c00" stroke-width="1"/>')
        if i == 0:
            o.append(rect(px - 0.75, py - 0.75, px + 0.75, py + 0.75, fill="none", stroke="#fff", stroke_width="1.5"))
    if ref in ("C1", "J6", "J7"):          # μικρά: ετικέτα δίπλα / label beside
        o.append(text(X(x1) + 6, Y((y0 + y1) / 2) + 5, ref, 13, "start", "#fff"))
    else:
        o.append(text(X((x0 + x1) / 2), Y((y0 + y1) / 2) + 5, ref, 13, fill="#fff"))

# Διαστάσεις
o.append(f'<line x1="{X(0)}" y1="{Y(0) + 28}" x2="{X(PCB_W)}" y2="{Y(0) + 28}" stroke="#555" stroke-width="1.5" marker-start="url(#a)" marker-end="url(#a)"/>')
o.append(text(X(PCB_W / 2), Y(0) + 46, f"{PCB_W:.0f} mm", 15, fill="#333"))
o.append(f'<line x1="{X(0) - 28}" y1="{Y(0)}" x2="{X(0) - 28}" y2="{Y(PCB_H)}" stroke="#555" stroke-width="1.5"/>')
o.append(f'<text x="{X(0) - 38}" y="{Y(PCB_H / 2)}" font-size="15" fill="#333" font-weight="700" text-anchor="middle" transform="rotate(-90 {X(0) - 38} {Y(PCB_H / 2)})">{PCB_H:.0f} mm</text>')
o.append(text(X(PCB_W / 2), MY - 40, "↑ ΠΑΝΩ / TOP — 230V L, N", 15, fill="#e65100"))
o.append(text(X(PCB_W / 2), MY - 20, "(0,0) = κάτω αριστερά · top view (component side)", 11, fill="#666", weight=400))

# Πίνακας εξαρτημάτων
tx = X(PCB_W) + 60
o.append(text(tx, MY, "Εξαρτήματα / Parts", 20, "start"))
o.append(text(tx, MY + 22, "pin 1 = τετράγωνο · συντεταγμένες σε mm", 12, "start", "#666", 400))
yy = MY + 54
o.append(text(tx, yy, "U1", 13, "start"))
o.append(text(tx + 40, yy, "ESP32-C3 Super Mini σε 2× 1x8 θηλυκά headers", 12, "start", "#222", 400))
o.append(text(tx + 40, yy + 15, f"σειρές x={ESP_COL_X[0]}, {ESP_COL_X[1]} · pins y={ESP_PIN_Y0}…{ESP_PIN_Y0 + 7 * ESP_PITCH:.2f}", 11, "start", "#222", 400))
yy += 36
for ref, (desc, pins, _, _) in PARTS.items():
    o.append(text(tx, yy, ref, 13, "start", "#e65100" if ref in ("J1", "F1", "J2") else "#111"))
    p = " ".join(f"({px:g}, {py:g})" for px, py in pins) if pins else "άκρη πλακέτας, άνοιγμα προς τα κάτω"
    o.append(text(tx + 40, yy, desc, 12, "start", "#222", 400))
    o.append(text(tx + 40, yy + 15, p, 11, "start", "#666", 400))
    yy += 36
yy += 10
o.append(text(tx, yy, "Συνδέσεις / Nets", 20, "start"))
yy += 26
for net, members in NETS.items():
    o.append(text(tx, yy, net, 12.5, "start", "#e65100" if net in ("L_IN", "L_FUSED", "N") else "#111"))
    o.append(text(tx + 85, yy, " · ".join(members), 11.5, "start", "#333", 400))
    yy += 20

o.append('<defs><marker id="a" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#555"/></marker></defs>')
o.append("</svg>")
os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "pcb"), exist_ok=True)
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pcb", "placement.svg")
open(out, "w", encoding="utf-8").write("\n".join(o))
print(out, W, H)
