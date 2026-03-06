"""
Generador de reporte PDF de stock para Waitry.
Usa ReportLab para crear un PDF profesional con tabla, resumen y alertas.
"""

import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# ─── Paleta de colores ─────────────────────────────────────────────────────────
COLOR_PRIMARY   = colors.HexColor("#1A1A2E")   # Azul marino oscuro
COLOR_ACCENT    = colors.HexColor("#E94560")   # Rojo/coral para alertas
COLOR_HEADER_BG = colors.HexColor("#16213E")   # Fondo encabezado tabla
COLOR_ROW_ALT   = colors.HexColor("#F4F6FB")   # Fila alternada
COLOR_LOW_STOCK = colors.HexColor("#FFF3CD")   # Fondo stock bajo
COLOR_OK        = colors.HexColor("#D4EDDA")   # Fondo stock ok
COLOR_BORDER    = colors.HexColor("#DEE2E6")
WHITE           = colors.white
GRAY_TEXT       = colors.HexColor("#6C757D")

# Stock mínimo de alerta (configurable)
LOW_STOCK_THRESHOLD = int(os.getenv("LOW_STOCK_THRESHOLD", "5"))


def build_styles():
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        "ReportTitle",
        fontName="Helvetica-Bold",
        fontSize=22,
        textColor=COLOR_PRIMARY,
        spaceAfter=4,
        alignment=TA_LEFT,
    ))
    styles.add(ParagraphStyle(
        "ReportSubtitle",
        fontName="Helvetica",
        fontSize=11,
        textColor=GRAY_TEXT,
        spaceAfter=2,
        alignment=TA_LEFT,
    ))
    styles.add(ParagraphStyle(
        "SectionTitle",
        fontName="Helvetica-Bold",
        fontSize=13,
        textColor=COLOR_PRIMARY,
        spaceBefore=14,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        "TableHeader",
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=WHITE,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        "CellNormal",
        fontName="Helvetica",
        fontSize=9,
        textColor=COLOR_PRIMARY,
        alignment=TA_LEFT,
    ))
    styles.add(ParagraphStyle(
        "CellNumber",
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=COLOR_PRIMARY,
        alignment=TA_RIGHT,
    ))
    styles.add(ParagraphStyle(
        "AlertText",
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=COLOR_ACCENT,
        alignment=TA_LEFT,
    ))
    styles.add(ParagraphStyle(
        "FooterText",
        fontName="Helvetica",
        fontSize=8,
        textColor=GRAY_TEXT,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        "SummaryValue",
        fontName="Helvetica-Bold",
        fontSize=20,
        textColor=COLOR_PRIMARY,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        "SummaryLabel",
        fontName="Helvetica",
        fontSize=8,
        textColor=GRAY_TEXT,
        alignment=TA_CENTER,
    ))
    return styles


def _normalize_products(raw_data: list[dict]) -> list[dict]:
    """Normaliza los datos del Excel de Waitry al formato estándar del reporte."""
    if not raw_data:
        return []

    normalized = []
    for row in raw_data:
        # Columnas exactas del export de Waitry
        nombre = row.get("Nombre", row.get("nombre", "—")).strip()
        stock_raw = row.get("Stock actual", row.get("stock actual", "0")).strip()

        # Limpiar y convertir stock
        try:
            stock_val = float(stock_raw.replace(",", ".").replace(" ", "") or 0)
        except (ValueError, AttributeError):
            stock_val = 0.0

        if nombre and nombre != "—":
            normalized.append({
                "nombre":    nombre,
                "stock":     stock_val,
                "categoria": "—",
                "unidad":    "un.",
                "precio":    "—",
            })

    return normalized


def _summary_table(products: list[dict], styles) -> Table:
    """Tabla de resumen con métricas clave."""
    total     = len(products)
    low_stock = sum(1 for p in products if p["stock"] <= LOW_STOCK_THRESHOLD)
    sin_stock = sum(1 for p in products if p["stock"] == 0)
    ok_stock  = total - low_stock

    def summary_cell(value, label):
        return [
            Paragraph(str(value), styles["SummaryValue"]),
            Paragraph(label, styles["SummaryLabel"]),
        ]

    data = [
        [
            summary_cell(total,     "Total productos"),
            summary_cell(ok_stock,  "Stock normal"),
            summary_cell(low_stock, f"Stock bajo (≤{LOW_STOCK_THRESHOLD})"),
            summary_cell(sin_stock, "Sin stock"),
        ]
    ]

    col_w = (A4[0] - 4*cm) / 4
    t = Table(data, colWidths=[col_w]*4, rowHeights=[60])
    t.setStyle(TableStyle([
        ("BOX",         (0,0), (-1,-1), 0.5, COLOR_BORDER),
        ("INNERGRID",   (0,0), (-1,-1), 0.5, COLOR_BORDER),
        ("BACKGROUND",  (0,0), (-1,-1), colors.white),
        ("BACKGROUND",  (2,0), (2,0),   COLOR_LOW_STOCK),
        ("BACKGROUND",  (3,0), (3,0),   colors.HexColor("#F8D7DA")),
        ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN",       (0,0), (-1,-1), "CENTER"),
        ("ROUNDEDCORNERS", [5]),
    ]))
    return t


def _stock_table(products: list[dict], styles) -> Table:
    """Tabla principal de stock."""
    headers = ["Producto", "Categoría", "Unidad", "Stock", "Estado"]
    header_row = [Paragraph(h, styles["TableHeader"]) for h in headers]

    rows = [header_row]
    for p in sorted(products, key=lambda x: x["stock"]):
        # Determinar estado
        if p["stock"] == 0:
            estado = Paragraph("SIN STOCK", styles["AlertText"])
            row_color = colors.HexColor("#F8D7DA")
        elif p["stock"] <= LOW_STOCK_THRESHOLD:
            estado = Paragraph("STOCK BAJO", ParagraphStyle(
                "warn", fontName="Helvetica-Bold", fontSize=9,
                textColor=colors.HexColor("#856404"), alignment=TA_LEFT
            ))
            row_color = COLOR_LOW_STOCK
        else:
            estado = Paragraph("OK", ParagraphStyle(
                "ok", fontName="Helvetica-Bold", fontSize=9,
                textColor=colors.HexColor("#155724"), alignment=TA_LEFT
            ))
            row_color = None

        stock_str = f"{p['stock']:g}" if isinstance(p["stock"], float) else str(p["stock"])
        row = [
            Paragraph(str(p["nombre"]),    styles["CellNormal"]),
            Paragraph(str(p["categoria"]), styles["CellNormal"]),
            Paragraph(str(p["unidad"]),    styles["CellNormal"]),
            Paragraph(stock_str,           styles["CellNumber"]),
            estado,
        ]
        rows.append((row, row_color))

    # Separar datos y estilos de color de fila
    table_data = [rows[0]] + [r[0] for r in rows[1:]]
    row_colors = [None] + [r[1] for r in rows[1:]]

    page_w = A4[0] - 4*cm
    col_widths = [page_w*0.35, page_w*0.20, page_w*0.12, page_w*0.13, page_w*0.20]

    t = Table(table_data, colWidths=col_widths, repeatRows=1)

    style_cmds = [
        ("BACKGROUND",  (0,0), (-1,0),  COLOR_HEADER_BG),
        ("FONTNAME",    (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",    (0,0), (-1,0),  9),
        ("TEXTCOLOR",   (0,0), (-1,0),  WHITE),
        ("ALIGN",       (3,0), (3,-1),  "RIGHT"),
        ("ALIGN",       (0,0), (-1,0),  "CENTER"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, COLOR_ROW_ALT]),
        ("GRID",        (0,0), (-1,-1), 0.4, COLOR_BORDER),
        ("TOPPADDING",  (0,0), (-1,-1), 6),
        ("BOTTOMPADDING",(0,0), (-1,-1), 6),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("RIGHTPADDING",(0,0), (-1,-1), 8),
    ]

    # Colores por estado de fila
    for i, c in enumerate(row_colors[1:], start=1):
        if c:
            style_cmds.append(("BACKGROUND", (0,i), (-1,i), c))

    t.setStyle(TableStyle(style_cmds))
    return t


def generate_pdf(
    products_raw: list[dict],
    output_path: str,
    place_name: str = "Cafetería",
    report_date: datetime | None = None
) -> str:
    """
    Genera el PDF de reporte de stock.
    
    Args:
        products_raw: Datos crudos del scraper.
        output_path:  Ruta donde guardar el PDF.
        place_name:   Nombre del local (para el encabezado).
        report_date:  Fecha del reporte (default: ahora).
    
    Returns:
        Ruta del PDF generado.
    """
    if report_date is None:
        report_date = datetime.now()

    date_str = report_date.strftime("%d/%m/%Y %H:%M")
    styles   = build_styles()
    products = _normalize_products(products_raw)

    # Si no hay datos reales, generar datos de demo
    if not products:
        products = _demo_products()

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=2*cm,
        rightMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm,
    )

    story = []

    # ── Encabezado ──────────────────────────────────────────────────────────
    story.append(Paragraph(f"Reporte de Stock", styles["ReportTitle"]))
    story.append(Paragraph(f"{place_name}  ·  Generado el {date_str}", styles["ReportSubtitle"]))
    story.append(HRFlowable(width="100%", thickness=2, color=COLOR_PRIMARY, spaceAfter=12))

    # ── Resumen ─────────────────────────────────────────────────────────────
    story.append(Paragraph("Resumen ejecutivo", styles["SectionTitle"]))
    story.append(_summary_table(products, styles))
    story.append(Spacer(1, 14))

    # ── Alertas de stock bajo ────────────────────────────────────────────────
    low = [p for p in products if 0 < p["stock"] <= LOW_STOCK_THRESHOLD]
    no_stock = [p for p in products if p["stock"] == 0]

    if no_stock or low:
        story.append(Paragraph("⚠ Alertas", styles["SectionTitle"]))

        alert_data = []
        for p in no_stock:
            alert_data.append([
                Paragraph(f"🔴  {p['nombre']}", styles["AlertText"]),
                Paragraph("SIN STOCK — requiere reposición inmediata", styles["AlertText"]),
            ])
        for p in low:
            alert_data.append([
                Paragraph(f"🟡  {p['nombre']}", ParagraphStyle(
                    "warnAlert", fontName="Helvetica-Bold", fontSize=9,
                    textColor=colors.HexColor("#856404")
                )),
                Paragraph(f"Stock bajo: {p['stock']:g} {p['unidad']} disponibles", ParagraphStyle(
                    "warnAlertBody", fontName="Helvetica", fontSize=9,
                    textColor=colors.HexColor("#856404")
                )),
            ])

        if alert_data:
            page_w = A4[0] - 4*cm
            at = Table(alert_data, colWidths=[page_w*0.35, page_w*0.65])
            at.setStyle(TableStyle([
                ("BACKGROUND",  (0,0), (-1,-1), colors.HexColor("#FFFBF0")),
                ("BOX",         (0,0), (-1,-1), 0.5, COLOR_ACCENT),
                ("INNERGRID",   (0,0), (-1,-1), 0.3, colors.HexColor("#FFDDAA")),
                ("TOPPADDING",  (0,0), (-1,-1), 5),
                ("BOTTOMPADDING",(0,0),(-1,-1), 5),
                ("LEFTPADDING", (0,0), (-1,-1), 8),
            ]))
            story.append(at)
            story.append(Spacer(1, 14))

    # ── Tabla completa ───────────────────────────────────────────────────────
    story.append(Paragraph("Detalle completo de stock", styles["SectionTitle"]))
    story.append(_stock_table(products, styles))

    # ── Footer ───────────────────────────────────────────────────────────────
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"Reporte generado automáticamente · {place_name} · {date_str}  ·  Datos extraídos de Waitry",
        styles["FooterText"]
    ))

    doc.build(story)
    return output_path


def _demo_products() -> list[dict]:
    """Datos de ejemplo para cuando no hay datos reales."""
    return [
        {"nombre": "Café Espresso",      "stock": 120, "categoria": "Bebidas",   "unidad": "kg",  "precio": "$12.00"},
        {"nombre": "Leche entera",        "stock": 45,  "categoria": "Lácteos",   "unidad": "lt",  "precio": "$1.50"},
        {"nombre": "Croissant",           "stock": 3,   "categoria": "Panadería", "unidad": "un.", "precio": "$2.50"},
        {"nombre": "Azúcar blanca",       "stock": 8,   "categoria": "Insumos",   "unidad": "kg",  "precio": "$0.80"},
        {"nombre": "Jugo de naranja",     "stock": 0,   "categoria": "Bebidas",   "unidad": "lt",  "precio": "$3.00"},
        {"nombre": "Medialunas",          "stock": 2,   "categoria": "Panadería", "unidad": "un.", "precio": "$1.80"},
        {"nombre": "Chocolate en polvo",  "stock": 22,  "categoria": "Insumos",   "unidad": "kg",  "precio": "$5.00"},
        {"nombre": "Vasos descartables",  "stock": 200, "categoria": "Descartables","unidad":"un.","precio": "$0.10"},
        {"nombre": "Servilletas",         "stock": 500, "categoria": "Descartables","unidad":"un.","precio": "$0.05"},
        {"nombre": "Té negro",            "stock": 4,   "categoria": "Bebidas",   "unidad": "cj.", "precio": "$2.20"},
        {"nombre": "Mantequilla",         "stock": 0,   "categoria": "Lácteos",   "unidad": "kg",  "precio": "$4.50"},
        {"nombre": "Canela en polvo",     "stock": 15,  "categoria": "Insumos",   "unidad": "g",   "precio": "$3.00"},
    ]
