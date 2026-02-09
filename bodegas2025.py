import streamlit as st
import pandas as pd
import plotly.express as px
import base64
from pathlib import Path
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage

# =========================
# Configuración base
# =========================
st.set_page_config(page_title="Análisis Financiero - OK-DTA V2", layout="wide")

# --- Logo -> data URI ---
def data_uri(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""  # si no está, ocultamos el <img>
    b64 = base64.b64encode(p.read_bytes()).decode()
    ext = p.suffix.lower().replace(".", "") or "png"
    return f"data:image/{ext};base64,{b64}"

LOGO_URI = data_uri("Logo_balmaceda.png")  # el archivo está en la misma carpeta del .py
LOGO_SIZE = 210  # px

# =======================
# HEADER COMPACTO
# =======================
st.markdown("""
<style>
/* Quitar espacio superior global */
main {
    padding-top: 0rem !important;
}
.block-container {
    padding-top: 1rem !important;   /* 🔥 Subido aún más */
}

/* Header súper compacto */
.header-title {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-top: -7px;    /* 🔥 antes -20px → lo subimos más */
    margin-bottom: -1px;  /* reduce espacio bajo el título */
}

/* Título más cercano a la lupa */
.header-title h1 {
    margin: 0;
    padding: 0;
    font-size: 2.35rem;
    font-weight: 700;
}

/* Logo más pequeño y mejor alineado */
.header-title img {
    width: 160px;         /* 🔥 antes 160px */
    height: 140px;
    object-fit: contain;
    border-radius: 12px;
}

/* Responsivo */
@media (max-width: 1200px) {
    .header-title img { width: 100px; height: 100px; }
}
@media (max-width: 640px) {
    .header-title img { width: 65px; height: 65px; }
}
</style>

<div class="header-title">
    <h1>🔎 Análisis Financiero de Bodegas</h1>
    <img src='""" + LOGO_URI + """' alt='Logo'>
</div>
""", unsafe_allow_html=True)

st.caption("Fuente: Google Sheets (CSV) · Agrupaciones dinámicas y visualizaciones interactivas")



# =========================
# Carga de datos
# =========================
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSuoX_V5rYls-pBu7F3_VP2APS3FL7-eYbn9uDWUGJQZbxNfQTm9gRlyDlE69wWJjsDQpDzi2lt31Ak/pub?gid=1154929321&single=true&output=csv"

st.sidebar.header("⚙️ Controles")
if st.sidebar.button("🔄 Actualizar datos (limpiar caché)"):
    st.cache_data.clear()

@st.cache_data
def load_data(url: str) -> pd.DataFrame:
    df = pd.read_csv(url)
    # Normalización y tipos
    df["Fecha"] = pd.to_datetime(df.get("Fecha"), errors="coerce")
    df["Monto"] = pd.to_numeric(
        df["Monto"].astype(str).str.replace(r"[^\d\.-]", "", regex=True),
        errors="coerce"
    )
    # Columnas esperadas
    for c in ["Obs", "CC1", "Sit", "Responsable", "Año", "Esp", "CC"]:
        if c not in df.columns:
            df[c] = pd.NA

    # Normalización fuerte de CC y Sit
    df["CC"]  = df["CC"].astype(str).str.strip().str.upper()
    df["Sit"] = df["Sit"].astype(str).str.strip().str.upper()
    df["Obs"] = df["Obs"].astype(str)
    df["CC1"] = df["CC1"].astype(str)

    df = df.dropna(subset=["Monto", "CC"])
    return df

df = load_data(CSV_URL)

# SIN filtros (por ahora): usar todo el dataset
df_f = df.copy()

# =========================
# Carga de Electricidad (Excel local o URL XLSX)
# =========================
ELECTRICIDAD_XLSX = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSm1GzFOATXqiYiGSKUZWZ5C2dE9nXv7bTtR3XmchtWhC9ZRMRK5OGDQfZhb624dA/pub?output=xlsx"

@st.cache_data
def load_electricidad(path_or_url: str) -> dict[str, pd.DataFrame]:
    if path_or_url.startswith(("http://", "https://")):
        sheets = pd.read_excel(path_or_url, sheet_name=None)
    else:
        p = Path(path_or_url)
        if not p.exists():
            return {}
        sheets = pd.read_excel(p, sheet_name=None)
    cleaned: dict[str, pd.DataFrame] = {}
    for name, df_sheet in sheets.items():
        if df_sheet is None:
            continue
        df_sheet = df_sheet.copy()
        df_sheet.columns = [str(c).strip() for c in df_sheet.columns]
        cleaned[name] = df_sheet
    return cleaned


def _infer_date_column(df_in: pd.DataFrame) -> str | None:
    best_col = None
    best_ratio = 0.0
    for col in df_in.columns:
        s = pd.to_datetime(df_in[col], errors="coerce")
        ratio = s.notna().mean()
        if ratio > best_ratio and ratio >= 0.5:
            best_ratio = ratio
            best_col = col
    return best_col

def _pick_primary_numeric(df_in: pd.DataFrame) -> str | None:
    preferred = ["TOTAL", "MONTO", "VALOR", "COSTO", "KW", "KWH", "CONSUMO", "ENERGIA"]
    cols = [str(c) for c in df_in.columns]
    for p in preferred:
        for c in cols:
            if p in c.upper():
                return c
    num_df = df_in.apply(pd.to_numeric, errors="coerce")
    num_cols = [c for c in num_df.columns if num_df[c].notna().any()]
    return num_cols[0] if num_cols else None

def _clean_header_list(row_vals: list) -> list[str]:
    out = []
    for v in row_vals:
        if pd.isna(v):
            break
        out.append(str(v).strip())
    return out

def _dedupe_cols(cols: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out: list[str] = []
    for c in cols:
        if c in seen:
            seen[c] += 1
            out.append(f"{c}.{seen[c]}")
        else:
            seen[c] = 0
            out.append(c)
    return out

def _fmt_cell(v, is_pct=False, is_currency=False, is_int=False):
    try:
        if pd.isna(v):
            return ""
    except Exception:
        if v is None:
            return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if is_int:
        try:
            return f"{float(v):,.0f}"
        except Exception:
            return str(v)
    if is_pct:
        try:
            return f"{float(v):.2%}"
        except Exception:
            return str(v)
    if is_currency:
        try:
            return f"${float(v):,.0f}"
        except Exception:
            return str(v)
    if hasattr(v, "strftime"):
        try:
            return v.strftime("%H:%M")
        except Exception:
            return str(v)
    return str(v)

def _render_table(df_in: pd.DataFrame, header_bg="#1f4e78", header_fg="white",
                  row_alt="#f8f4e8", compact=True, int_cols=None, cur_cols_extra=None) -> None:
    pct_cols = [c for c in df_in.columns if "%" in str(c)]
    cur_cols = [c for c in df_in.columns if "$" in str(c) or "TOTAL" in str(c).upper()]
    int_cols = set(int_cols or [])
    cur_cols = set(cur_cols) | set(cur_cols_extra or [])

    rows_html = []
    for i, row in df_in.iterrows():
        tds = []
        for c in df_in.columns:
            v = _fmt_cell(
                row[c],
                is_pct=(c in pct_cols),
                is_currency=(c in cur_cols),
                is_int=(c in int_cols),
            )
            tds.append(f"<td>{v}</td>")
        cls = "alt" if i % 2 == 0 else ""
        rows_html.append(f"<tr class='{cls}'>" + "".join(tds) + "</tr>")

    ths = "".join([f"<th>{c}</th>" for c in df_in.columns])
    table_html = f"""
    <div class="elec-table-wrap">
      <table class="elec-table">
        <thead><tr>{ths}</tr></thead>
        <tbody>{''.join(rows_html)}</tbody>
      </table>
    </div>
    """

    st.markdown(
        f"""
        <style>
        .elec-table-wrap {{ overflow-x: auto; }}
        .elec-table {{
            border-collapse: collapse;
            width: 100%;
            font-size: { "12px" if compact else "13px" };
        }}
        .elec-table th {{
            background: {header_bg};
            color: {header_fg};
            text-align: center;
            padding: 6px 8px;
            border: 1px solid #d5d5d5;
            font-weight: 700;
        }}
        .elec-table td {{
            padding: 6px 8px;
            border: 1px solid #d5d5d5;
            text-align: center;
            white-space: nowrap;
        }}
        .elec-table tr.alt td {{
            background: {row_alt};
        }}
        </style>
        {table_html}
        """,
        unsafe_allow_html=True,
    )

def _parse_mes_sheet(df_raw: pd.DataFrame) -> dict[str, pd.DataFrame]:
    def _find_row_any(label: str) -> int | None:
        txt = df_raw.astype(str).apply(lambda s: s.str.strip())
        hits = txt.apply(lambda row: row.str.contains(label, case=False, na=False).any(), axis=1)
        if hits.any():
            return int(hits.idxmax())
        return None

    def _slice_until_blank(start_row: int, col_idx: int, col_slice: slice) -> pd.DataFrame:
        end = len(df_raw)
        for i in range(start_row, len(df_raw)):
            v = df_raw.iloc[i, col_idx] if col_idx < df_raw.shape[1] else None
            if pd.isna(v) or str(v).strip() == "":
                end = i
                break
            txt = str(v).upper()
            if "INPUTS POR BODEGA" in txt or "LIQUIDACIÓN POR BODEGA" in txt:
                end = i
                break
        return df_raw.iloc[start_row:end, col_slice].copy()

    # INPUTS GENERALES
    row_ig = _find_row_any("INPUTS GENERALES")
    if row_ig is not None:
        ig = _slice_until_blank(row_ig + 1, 0, slice(0, 3))
    else:
        ig = df_raw.iloc[3:8, 0:3].copy()
    ig.columns = ["Parámetro", "Valor", "Unidad"]
    ig = ig.dropna(how="all")

    # BOLETA CGE
    row_bc = _find_row_any("BOLETA CGE")
    if row_bc is not None:
        # +2 porque la fila inmediatamente inferior suele ser encabezado Concepto/Monto
        bc = _slice_until_blank(row_bc + 2, 5, slice(5, 7))
    else:
        bc = df_raw.iloc[4:9, 5:7].copy()
    bc.columns = ["Concepto", "Monto $"]
    bc = bc.dropna(how="all")

    def _find_row(label: str) -> int | None:
        col0 = df_raw.iloc[:, 0].astype(str)
        hits = col0.str.contains(label, case=False, na=False)
        if hits.any():
            return int(hits.idxmax())
        return None

    def _slice_section(start_row: int) -> pd.DataFrame:
        end = len(df_raw)
        col0 = df_raw.iloc[:, 0]
        for i in range(start_row, len(df_raw)):
            v = col0.iloc[i]
            if pd.isna(v):
                end = i
                break
            if isinstance(v, str) and ("LIQUIDACIÓN POR BODEGA" in v.upper() or "INPUTS POR BODEGA" in v.upper()):
                if i != start_row:
                    end = i
                    break
        return df_raw.iloc[start_row:end]

    # INPUTS POR BODEGA
    row_inputs = _find_row("INPUTS POR BODEGA")
    if row_inputs is not None:
        hdr_row = row_inputs + 1
        data_row = row_inputs + 2
        hdr_in = _clean_header_list(df_raw.iloc[hdr_row, 0:15].tolist())
        hdr_in = _dedupe_cols(hdr_in)
        data_in = _slice_section(data_row).iloc[:, 0:len(hdr_in)].copy()
        data_in.columns = hdr_in
    else:
        hdr_in = _clean_header_list(df_raw.iloc[11, 0:9].tolist())
        hdr_in = _dedupe_cols(hdr_in)
        data_in = df_raw.iloc[12:20, 0:len(hdr_in)].copy()
        data_in.columns = hdr_in

    # LIQUIDACIÓN POR BODEGA
    row_liq = _find_row("LIQUIDACIÓN POR BODEGA")
    if row_liq is not None:
        hdr_row = row_liq + 1
        data_row = row_liq + 2
        hdr_liq = _clean_header_list(df_raw.iloc[hdr_row, 0:20].tolist())
        hdr_liq = _dedupe_cols(hdr_liq)
        data_liq = _slice_section(data_row).iloc[:, 0:len(hdr_liq)].copy()
        data_liq.columns = hdr_liq
    else:
        hdr_liq = _clean_header_list(df_raw.iloc[22, 0:15].tolist())
        hdr_liq = _dedupe_cols(hdr_liq)
        data_liq = df_raw.iloc[23:31, 0:len(hdr_liq)].copy()
        data_liq.columns = hdr_liq

    return {
        "inputs_generales": ig,
        "boleta_cge": bc,
        "inputs_bodega": data_in,
        "liquidacion": data_liq,
    }

def _df_to_rl_table(df_in: pd.DataFrame, header_bg=colors.HexColor("#1f4e78"),
                    max_width=760, font_size=7) -> Table:
    styles = getSampleStyleSheet()
    data = [[Paragraph(str(c), styles["BodyText"]) for c in df_in.columns]]
    for _, row in df_in.fillna("").astype(str).iterrows():
        data.append([Paragraph(str(v), styles["BodyText"]) for v in row.tolist()])

    ncols = len(df_in.columns)
    col_w = max_width / max(1, ncols)
    col_widths = [col_w] * ncols

    tbl = Table(data, hAlign="LEFT", colWidths=col_widths, repeatRows=1)
    tbl.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), header_bg),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ("FONTSIZE", (0, 0), (-1, -1), font_size),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("TOPPADDING", (0, 0), (-1, 0), 6),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ])
    )
    return tbl

def _format_pdf_df(df_in: pd.DataFrame) -> pd.DataFrame:
    df = df_in.copy()
    for c in df.columns:
        cu = str(c).upper()
        if "HORA" in cu:
            df[c] = df[c].apply(lambda v: v.strftime("%H:%M") if hasattr(v, "strftime") else str(v))
            continue

        is_pct = "%" in cu
        is_cur = "$" in cu or "TOTAL" in cu or "IVA" in cu or "NETO" in cu
        is_kwh = "KWH" in cu

        if is_pct:
            def fmt_pct(v):
                try:
                    v = float(v)
                    if abs(v) <= 1.5:
                        v = v * 100.0
                    return f"{v:.2f}%"
                except Exception:
                    return str(v)
            df[c] = df[c].apply(fmt_pct)
        elif is_cur:
            def fmt_cur(v):
                try:
                    v = float(v)
                    return f"${v:,.0f}"
                except Exception:
                    return str(v)
            df[c] = df[c].apply(fmt_cur)
        elif is_kwh:
            def fmt_int(v):
                try:
                    return f"{float(v):,.0f}"
                except Exception:
                    return str(v)
            df[c] = df[c].apply(fmt_int)
        else:
            df[c] = df[c].apply(lambda v: str(v))
    return df

def build_electricidad_pdf(
    title: str,
    sel_months: list[str],
    sel_bodega: str,
    inputs_generales: pd.DataFrame,
    boleta_avg: pd.DataFrame,
    inputs_bodega: pd.DataFrame,
    liquidacion: pd.DataFrame,
    charts: list[dict],
) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        title=title,
        leftMargin=24,
        rightMargin=24,
        topMargin=24,
        bottomMargin=24,
    )
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(title, styles["Title"]))
    story.append(Paragraph(f"Meses: {', '.join(sel_months)} · Bodega: {sel_bodega}", styles["Normal"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("INPUTS GENERALES", styles["Heading3"]))
    story.append(_df_to_rl_table(_format_pdf_df(inputs_generales), max_width=760, font_size=8))
    story.append(Spacer(1, 10))

    story.append(Paragraph("BOLETA CGE (PROMEDIO SEGÚN MESES)", styles["Heading3"]))
    story.append(_df_to_rl_table(_format_pdf_df(boleta_avg), max_width=760, font_size=8))
    story.append(Spacer(1, 10))

    story.append(Paragraph("INPUTS POR BODEGA (REMARCADOR + HORARIO EFECTIVO)", styles["Heading3"]))
    story.append(_df_to_rl_table(_format_pdf_df(inputs_bodega), max_width=760, font_size=7))
    story.append(Spacer(1, 10))

    story.append(Paragraph("LIQUIDACIÓN POR BODEGA (ASIGNACIÓN DE COSTOS + CRITERIO HORARIO)", styles["Heading3"]))
    story.append(_df_to_rl_table(_format_pdf_df(liquidacion), max_width=760, font_size=7))
    story.append(Spacer(1, 12))

    if charts:
        import matplotlib.pyplot as plt
        story.append(Paragraph("GRÁFICO — LIQUIDACIÓN POR BODEGA", styles["Heading3"]))
        for ch in charts:
            try:
                df_plot = ch["df"].copy()
                x_col = ch["x_col"]
                title = ch.get("title", "")
                cols_costos = ch["cols_costos"]
                col_total = ch["col_total"]
                palette = ch["palette"]

                fig, ax1 = plt.subplots(figsize=(10, 4.6), dpi=150)
                bottom = None
                for c in cols_costos:
                    vals = pd.to_numeric(df_plot[c], errors="coerce").fillna(0)
                    ax1.bar(df_plot[x_col], vals, label=c, bottom=bottom, color=palette.get(c, "#94a3b8"))
                    bottom = vals if bottom is None else bottom + vals

                ax1.set_ylabel("Costo (CLP)")
                ax1.tick_params(axis="x", rotation=0)

                ax2 = ax1.twinx()
                total_vals = pd.to_numeric(df_plot[col_total], errors="coerce").fillna(0)
                ax2.plot(df_plot[x_col], total_vals, color="#111827", marker="o", linewidth=2, label="TOTAL c/IVA $")
                ax2.set_ylabel("Total c/IVA (CLP)")

                handles1, labels1 = ax1.get_legend_handles_labels()
                handles2, labels2 = ax2.get_legend_handles_labels()
                ax1.legend(handles1 + handles2, labels1 + labels2, loc="upper center",
                           bbox_to_anchor=(0.5, 1.15), ncol=3, fontsize=7, frameon=False)
                if title:
                    ax1.set_title(title)

                plt.tight_layout()
                img_buf = BytesIO()
                fig.savefig(img_buf, format="png")
                plt.close(fig)
                img_buf.seek(0)
                story.append(RLImage(img_buf, width=740, height=340))
                story.append(Spacer(1, 12))
            except Exception as e:
                raise RuntimeError(f"No fue posible renderizar el gráfico en el PDF: {e}")

    doc.build(story)
    pdf = buf.getvalue()
    buf.close()
    return pdf

# =========================
# Utilidades de formato
# =========================
def fmt_clp_largo(v: float) -> str:
    return f"${v:,.0f}"

def fmt_short(v: float) -> str:
    v = float(v)
    av = abs(v)
    if av >= 1_000_000:
        return f"${v/1_000_000:.1f}M"
    if av >= 1_000:
        return f"${v/1_000:.0f}k"
    return f"${v:,.0f}"

# =========================
# KPI base (cálculos comunes)
# =========================
CAPEX = 151_834_571

# Canon arriendo
mask_canon = (
    (df_f["CC"] == "INGRESO") &
    (
        df_f["CC1"].str.contains("arriendo", case=False, na=False) |
        df_f["Obs"].str.contains("canon", case=False, na=False)
    )
)
ingresos_canon = df_f.loc[mask_canon, "Monto"].sum()
cobertura_capex = ingresos_canon / CAPEX if CAPEX else 0

# Saldo cuenta = PAGADO + ABONOS (según signos en CSV)
total_pagado = df_f.loc[df_f["Sit"] == "PAGADO", "Monto"].sum()
mask_abono_obs = df_f["Obs"].str.contains(r"\babono_*\b", case=False, na=False)
total_abonos = df_f.loc[mask_abono_obs, "Monto"].sum()
saldo_cuenta = total_pagado + total_abonos

# Ingresos / Egresos KPIs
mask_ingreso = df_f["CC"].eq("INGRESO")
mask_egreso  = df_f["CC"].eq("EGRESO")
sit_up = df_f["Sit"]  # ya normalizado

mask_sit_pagado = sit_up.eq("PAGADO")
mask_sit_abono  = sit_up.str.startswith("ABONO")

ingresos_kpi = df_f.loc[mask_ingreso & (mask_sit_pagado | mask_sit_abono), "Monto"].sum()
egresos_kpi  = df_f.loc[mask_egreso  &  mask_sit_pagado, "Monto"].sum()

balance_kpi = saldo_cuenta  # interpretación: saldo en cuenta BCI

# Cuentas por cobrar & egresos por pagar
sit_norm = df_f["Sit"]
cc_up    = df_f["CC"]

no_pagado_total  = df_f.loc[cc_up.eq("INGRESO") & sit_norm.eq("NO PAGADO"), "Monto"].sum()
abonos_total     = df_f.loc[cc_up.eq("INGRESO") & sit_norm.str.startswith("ABONO"), "Monto"].sum()
if abonos_total == 0:
    abonos_total = df_f.loc[
        cc_up.eq("INGRESO") &
        df_f["Obs"].str.contains(r"\babono\b", case=False, na=False),
        "Monto"
    ].sum()

cuentas_por_cobrar_neto = no_pagado_total - abonos_total

total_egresos_por_pagar = df_f.loc[
    cc_up.eq("EGRESO") & sit_norm.eq("NO PAGADO"), "Monto"
].sum()

posicion_neta = cuentas_por_cobrar_neto + total_egresos_por_pagar + balance_kpi

# =========================
# Estilos HTML para KPIs
# =========================
st.markdown("""
    <style>
    .kpi-card {
        background-color: #000000;
        padding: 20px;
        border-radius: 12px;
        text-align: center;
        color: white;
        font-family: Arial, sans-serif;
        box-shadow: 0px 4px 8px rgba(0,0,0,0.4);
    }
    .kpi-title {
        font-size: 16px;
        color: #bbbbbb;
        margin-bottom: 8px;
    }
    .kpi-value {
        font-size: 28px;
        font-weight: bold;
        margin-bottom: 5px;
    }
    .kpi-sub {
        font-size: 14px;
        color: #888888;
    }
    .kpi3-card{background:#ffffff;border-radius:14px;padding:18px 20px;border:1px solid #E5E7EB;
               box-shadow:0 8px 20px rgba(2,6,23,.06);border-left:6px solid var(--accent);}
    .kpi3-title{font-size:13px;color:#111827;font-weight:700;letter-spacing:.3px;text-transform:uppercase;margin-bottom:6px;}
    .kpi3-value{font-variant-numeric:tabular-nums;font-size:42px;line-height:1.1;font-weight:800;margin:0;}
    .kpi3-sub{display:none !important;}
    </style>
""", unsafe_allow_html=True)

st.markdown("---")

# =========================
# TABS PRINCIPALES
# =========================
tab_overview, tab_riesgos, tab_canon, tab_canon_m2, tab_ing_eg, tab_electricidad = st.tabs(
    ["🏠 Visión general", "⚠️ Riesgos & cobranzas", "🏢 Canon anual / mensual", "🧩 Canon por m²", "📈 Ingresos & egresos", "⚡ Electricidad"]
)

# =========================================================
# 🏠 TAB 1: VISIÓN GENERAL
# =========================================================
with tab_overview:
    st.subheader("📊 Estado general del proyecto")

    # --- Fila 1: KPIs negros (CAPEX / Canon / Cobertura CAPEX) ---
    sp_left, kpi1, kpi2, kpi3, sp_right = st.columns([1, 3, 3, 3, 1])

    with kpi1:
        st.markdown(f"""
            <div class="kpi-card">
                <div class="kpi-title">💼 CAPEX</div>
                <div class="kpi-value">{fmt_clp_largo(CAPEX)}</div>
                <div class="kpi-sub">Inversión total</div>
            </div>
        """, unsafe_allow_html=True)

    with kpi2:
        st.markdown(f"""
            <div class="kpi-card">
                <div class="kpi-title">🏢 Ingresos Canon Arriendo</div>
                <div class="kpi-value">{fmt_clp_largo(ingresos_canon)}</div>
                <div class="kpi-sub">Acumulado</div>
            </div>
        """, unsafe_allow_html=True)

    with kpi3:
        st.markdown(f"""
            <div class="kpi-card">
                <div class="kpi-title">📊 Cobertura CAPEX</div>
                <div class="kpi-value">{cobertura_capex:.1%}</div>
                <div class="kpi-sub">Canon / CAPEX</div>
            </div>
        """, unsafe_allow_html=True)

    st.caption("Cobertura CAPEX = Ingresos canon acumulados / CAPEX total invertido.")
    st.markdown("")

    # =======================================
    # TARJETAS FINANCIERAS PRO – DISEÑO EJECUTIVO
    # =======================================
    def card_finanza(titulo, valor, color_hex):
        return f"""
        <div style="
            border-radius:16px;
            padding:14px 18px;
            border:1px solid #E5E7EB;
            background:#F9FAFB;                /* 🔥 antes blanco */
            box-shadow:0 6px 14px rgba(15,23,42,0.05);
            border-left:5px solid {color_hex};
        ">
            <div style="
                font-size:12px;
                font-weight:700;
                color:#6B7280;
                text-transform:uppercase;
                letter-spacing:0.08em;
            ">
                {titulo}
            </div>
            <div style="
                font-size:30px;                /* 🔥 antes 38px */
                font-weight:800;
                margin-top:2px;
                color:{color_hex};
                font-variant-numeric:tabular-nums;
            ">
                {valor}
            </div>
            <div style="
                font-size:11px;
                margin-top:4px;
                color:#9CA3AF;
            ">
                Indicador financiero clave
            </div>
        </div>
        """


    # ========== FILA 1 — INGRESOS / EGRESOS / CAJA ==========
    cA, cB, cC = st.columns(3)

    with cA:
        st.markdown(
            card_finanza(
                "TOTAL INGRESOS",
                fmt_clp_largo(ingresos_kpi),
                "#10B981",   # verde
            ),
            unsafe_allow_html=True,
        )

    with cB:
        st.markdown(
            card_finanza(
                "TOTAL EGRESOS",
                fmt_clp_largo(egresos_kpi),
                "#EF4444",   # rojo
            ),
            unsafe_allow_html=True,
        )

    with cC:
        bal_color = "#10B981" if balance_kpi >= 0 else "#EF4444"
        st.markdown(
            card_finanza(
                "CAJA BANCO BCI",
                fmt_clp_largo(balance_kpi),
                bal_color,
            ),
            unsafe_allow_html=True,
        )

    # ========== FILA 2 — CxC / EPP / POSICIÓN NETA ==========
    cD, cE, cF = st.columns(3)

    cxc_color = "#F59E0B" if cuentas_por_cobrar_neto > 0 else "#10B981"
    with cD:
        st.markdown(
            card_finanza(
                "CUENTAS POR COBRAR (NETO)",
                fmt_clp_largo(cuentas_por_cobrar_neto),
                cxc_color,
            ),
            unsafe_allow_html=True,
        )

    epp_color = "#EF4444" if total_egresos_por_pagar != 0 else "#10B981"
    with cE:
        st.markdown(
            card_finanza(
                "EGRESOS POR PAGAR",
                fmt_clp_largo(total_egresos_por_pagar),
                epp_color,
            ),
            unsafe_allow_html=True,
        )

    pn_color = "#10B981" if posicion_neta >= 0 else "#EF4444"
    with cF:
        st.markdown(
            card_finanza(
                "POSICIÓN NETA (CxC + EPP + BN)",
                fmt_clp_largo(posicion_neta),
                pn_color,
            ),
            unsafe_allow_html=True,
        )

    st.markdown("---")



    # =========================
    # Gráfico PRO: Ingresos por Canon de Arriendo por año + MA-3
    # =========================
    import plotly.graph_objects as go

    # =========================
    # 🏢 Ingresos por canon de arriendo — por año (MA-3)
    # =========================
    st.markdown("### 📊 Ingresos por Canon de Arriendo ")

    # Usa df_f si existen filtros aplicados; si no, usa df completo
    data_src = df_f if "df_f" in locals() else df

    # Filtro canon: CC == INGRESO y (CC1 contiene "arriendo" o Obs contiene "canon")
    mask_canon = (
        (data_src["CC"].astype(str) == "INGRESO") &
        (
            data_src["CC1"].astype(str).str.contains("arriendo", case=False, na=False) |
            data_src["Obs"].astype(str).str.contains("canon", case=False, na=False)
        )
    )

    # Agregado anual
    df_canon = (
        data_src.loc[mask_canon, ["Año", "Monto"]]
        .copy()
    )

    # Tipos
    df_canon["Año"] = pd.to_numeric(df_canon["Año"], errors="coerce")
    df_canon["Monto"] = pd.to_numeric(
        df_canon["Monto"].astype(str).str.replace(r"[^\d\.-]", "", regex=True),
        errors="coerce"
    )
    df_canon = df_canon.dropna(subset=["Año", "Monto"])

    if df_canon.empty:
        st.info("No hay datos de canon de arriendo para construir la serie anual.")
    else:
        df_canon = (
            df_canon
            .groupby("Año", as_index=False)["Monto"]
            .sum()
            .sort_values("Año")
            .rename(columns={"Monto": "Canon_anual_CLP"})
        )

        # Promedio móvil 3 años
        df_canon["MA3"] = (
            df_canon["Canon_anual_CLP"]
            .rolling(window=3, min_periods=1)
            .mean()
        )

        # ---------- KPI resumen ----------
        ultimo_anio = int(df_canon["Año"].max())
        ultimo_valor = float(
            df_canon.loc[df_canon["Año"] == ultimo_anio, "Canon_anual_CLP"].iloc[0]
        )

        anio_prev = ultimo_anio - 1
        if (df_canon["Año"] == anio_prev).any():
            valor_prev = float(
                df_canon.loc[df_canon["Año"] == anio_prev, "Canon_anual_CLP"].iloc[0]
            )
            var_yoy = (ultimo_valor - valor_prev) / valor_prev if valor_prev != 0 else 0
        else:
            valor_prev = None
            var_yoy = 0.0

        color_yoy = "#10B981" if var_yoy >= 0 else "#EF4444"

        st.markdown(
            f"""
            <div style='padding:12px 18px; border-radius:12px; background:#F9FAFB;
                 border:1px solid #E5E7EB; width: fit-content; margin-bottom:-8px;'>
                <span style='font-size:13px; color:#555;'>Último año ({ultimo_anio}):</span>
                <span style='font-size:20px; font-weight:700; color:#111;'>
                    ${ultimo_valor:,.0f}
                </span>
                <span style='font-size:13px; color:{color_yoy};'>
                    ({var_yoy:+.1%} YoY)
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ---------- GRÁFICO ----------
        fig = go.Figure()

        # Barras: canon anual
        fig.add_trace(
            go.Bar(
                x=df_canon["Año"],
                y=df_canon["Canon_anual_CLP"],
                name="Canon anual (CLP)",
                marker=dict(
                    color="rgba(37, 99, 235, 0.88)",
                    line=dict(width=1.0, color="rgba(255,255,255,0.6)"),
                ),
                hovertemplate="<b>Año %{x}</b><br>Canon: $%{y:,.0f}<extra></extra>",
            )
        )

        # Línea: MA-3 (glow + línea principal)
        fig.add_trace(
            go.Scatter(
                x=df_canon["Año"],
                y=df_canon["MA3"],
                name="Promedio móvil (MA-3)",
                mode="lines",
                line=dict(color="rgba(220,38,38,0.25)", width=8),
                hoverinfo="skip",
                showlegend=False,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=df_canon["Año"],
                y=df_canon["MA3"],
                name="Promedio móvil (MA-3)",
                mode="lines+markers",
                line=dict(color="#DC2626", width=3),
                marker=dict(color="#DC2626", size=6, line=dict(color="white", width=1)),
                hovertemplate="<b>Año %{x}</b><br>MA-3: $%{y:,.0f}<extra></extra>",
            )
        )

        # Sombreado técnico bajo la línea
        x_list = df_canon["Año"].tolist()
        y_ma = df_canon["MA3"].astype(float)
        y_lower = (y_ma * 0.97).tolist()
        y_upper = (y_ma * 1.03).tolist()

        fig.add_trace(
            go.Scatter(
                x=x_list + x_list[::-1],
                y=y_lower + y_upper[::-1],
                fill="toself",
                fillcolor="rgba(220,38,38,0.08)",
                line=dict(color="rgba(0,0,0,0)"),
                hoverinfo="skip",
                showlegend=False,
            )
        )

        fig.update_layout(
            template="plotly_white",
            height=480,
            margin=dict(l=20, r=20, t=40, b=20),
            legend=dict(
                orientation="h",
                y=1.12,
                x=0.5,
                xanchor="center",
                font=dict(size=12),
            ),
            xaxis=dict(
                title="Año",
                tickmode="linear",
                showgrid=False,
                linecolor="rgba(15,23,42,0.25)",
                tickfont=dict(size=12, color="#334155"),
            ),
            yaxis=dict(
                title="Monto (CLP)",
                tickformat=",.0f",
                gridcolor="rgba(148,163,184,0.25)",
                zeroline=False,
                ticks="outside",
                ticklen=6,
                tickfont=dict(size=12, color="#334155"),
            ),
            plot_bgcolor="#F8FAFC",
            paper_bgcolor="#F8FAFC",
            hovermode="x unified",
            hoverlabel=dict(
                bgcolor="white",
                font_size=13,
                font_color="#111",
                bordercolor="#E5E7EB",
            ),
            bargap=0.22,
        )


        st.plotly_chart(fig, use_container_width=True)

        # Descargar dataset agregado
        csv_canon = df_canon.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Descargar ingresos por canon (CSV)",
            data=csv_canon,
            file_name="ingresos_canon_por_anio.csv",
            mime="text/csv",
        )

# =========================================================
# ⚠️ TAB 2: RIESGOS & COBRANZAS
# =========================================================
with tab_riesgos:
              # ---------- Resumen por Responsable (NO PAGADO vs Abonos) ----------
    st.header("📋 Cuentas por Cobrar / Pagar")

    # --- Cálculos base ---
    df_np = df_f[df_f["Sit"] == "NO PAGADO"]
    df_abonos = df_f[df_f["Obs"].astype(str).str.contains("abono", case=False, na=False)]

    no_pagado_grouped = (
        df_np.groupby("Responsable")["Monto"]
        .agg(["sum", "count"])
        .rename(columns={"sum": "Monto NO PAGADO", "count": "Transacciones NO PAGADO"})
    )
    abonos_grouped = (
        df_abonos.groupby("Responsable")["Monto"]
        .agg(["sum", "count"])
        .rename(columns={"sum": "Monto Abonos", "count": "Cantidad Abonos"})
    )

    resumen = no_pagado_grouped.join(abonos_grouped, how="outer").fillna(0)
    resumen["Deuda"] = resumen["Monto NO PAGADO"] - resumen["Monto Abonos"]
    resumen["% Abonado"] = (
        resumen["Monto Abonos"] / resumen["Monto NO PAGADO"]
    ).replace([pd.NA, pd.NaT], 0).fillna(0)
    resumen["Progreso"] = resumen["% Abonado"].clip(lower=0, upper=1)

    def badge_pct(p):
        if p >= 1:
            return "🟢 En curso"
        if p >= 0.5:
            return "🟠 En curso"
        return "🔴 Bajo"

    resumen["Estado"] = resumen["% Abonado"].apply(badge_pct)

    # Ordenar por deuda y preparar tabla
    resumen = resumen.sort_values("Deuda", ascending=False)
    tabla = resumen.reset_index()

    cols_order = [
        "Responsable",
        "Monto NO PAGADO",
        "Monto Abonos",
        "Deuda",
        "% Abonado",
        "Transacciones NO PAGADO",
        "Cantidad Abonos",
        "Estado",
        "Progreso",  # queda al final para la barra
    ]
    tabla = tabla[cols_order]

    # ---------- KPI en formato “card” + explicación ----------
    total_deuda_neta = tabla["Deuda"].sum() if not tabla.empty else 0
    col_kpi, col_txt = st.columns([1, 2])

    deuda_color = "#EF4444" if total_deuda_neta > 0 else "#10B981"

    with col_kpi:
        st.markdown(
            f"""
            <div style="
                background-color:#ffffff;
                border-radius:14px;
                padding:14px 18px;
                border:1px solid #E5E7EB;
                box-shadow:0 8px 20px rgba(15,23,42,.06);
            ">
                <div style="
                    font-size:12px;
                    text-transform:uppercase;
                    letter-spacing:.08em;
                    color:#6B7280;
                    font-weight:600;
                ">
                    Deuda neta total
                </div>
                <div style="
                    font-size:26px;
                    font-weight:800;
                    margin-top:4px;
                    color:{deuda_color};
                    font-variant-numeric:tabular-nums;
                ">
                    ${total_deuda_neta:,.0f}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_txt:
        st.markdown(
            """
            <p style="margin-top:6px; color:#4B5563; font-size:13px;">
            La deuda neta corresponde al <b>monto NO PAGADO menos los abonos</b>,
            considerando solo los movimientos marcados como <code>NO PAGADO</code> o <code>ABONO</code>.
            El color de la tarjeta indica si la posición es deudora (rojo) o a favor (verde).
            </p>
            """,
            unsafe_allow_html=True,
        )

    # ---- Estilo visual de la tabla ----
    styler = (
        tabla.style
        .format({
            "Monto NO PAGADO": "${:,.0f}",
            "Monto Abonos": "${:,.0f}",
            "Deuda": "${:,.0f}",
            "% Abonado": "{:.1%}",
            "Transacciones NO PAGADO": "{:,.0f}",
            "Cantidad Abonos": "{:,.0f}",
            "Progreso": "{:.0%}",   # ahora se ve 94% en vez de 0.94
        })
        .hide(axis="index")
        .set_table_styles([
            {
                "selector": "thead th",
                "props": [
                    ("background-color", "#f5f6f8"),
                    ("color", "#111827"),
                    ("font-weight", "600"),
                    ("font-size", "13px"),
                    ("border-bottom", "1px solid #E5E7EB"),
                ],
            },
            {
                "selector": "tbody td",
                "props": [("font-size", "12px"), ("padding", "6px 8px")],
            },
            {
                "selector": "tbody tr:nth-child(even)",
                "props": [("background-color", "#fbfbfc")],
            },
            {
                "selector": "tbody tr:hover",
                "props": [("background-color", "#eef4ff")],
            },
        ])
        .background_gradient(subset=["Monto NO PAGADO"], cmap="Reds")
        .background_gradient(subset=["Monto Abonos"], cmap="Greens")
        .background_gradient(subset=["Deuda"], cmap="Oranges")
        .bar(subset=["Progreso"], color="#10B981")
    )

    # Negrita en la mayor deuda
    styler = styler.apply(
        lambda s: ["color: white; font-weight:700;"] + [""] * (len(s) - 1),
        axis=0,
        subset=["Deuda"],
    )

    st.dataframe(styler, use_container_width=True)

    # ---- Exportar PDF / CSV ----
    from reportlab.lib.pagesizes import A4, A3, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.units import cm

    def export_resumen_pdf(df_in: pd.DataFrame, filename: str = "resumen_no_pagado_abonos.pdf"):
        short_names = {
            "Monto NO PAGADO": "Monto NO PAG.",
            "Transacciones NO PAGADO": "Transacc. NO PAG.",
            "Cantidad Abonos": "Cant. Abonos",
            "Monto Abonos": "Monto Abonos",
            "% Abonado": "% Abonado",
        }
        df_local = df_in.rename(columns={c: short_names.get(c, c) for c in df_in.columns})

        ncols = len(df_local.columns)
        page_size = landscape(A4) if ncols <= 8 else landscape(A3)

        doc = SimpleDocTemplate(
            filename,
            pagesize=page_size,
            leftMargin=1*cm,
            rightMargin=1*cm,
            topMargin=1*cm,
            bottomMargin=1*cm,
        )

        base = ParagraphStyle(
            "base", fontSize=8.5, leading=10,
            spaceBefore=0, spaceAfter=0,
            wordWrap="CJK", splitLongWords=True,
        )
        sty_h = ParagraphStyle("head", parent=base, alignment=TA_CENTER, fontSize=9, leading=11)
        sty_l = ParagraphStyle("left", parent=base, alignment=TA_LEFT)
        sty_r = ParagraphStyle("right", parent=base, alignment=TA_RIGHT)

        story = [
            Paragraph("<b>Resumen por Responsable (NO PAGADO vs Abonos)</b>",
                      getSampleStyleSheet()["Title"]),
            Spacer(1, 0.4*cm),
        ]

        text_cols = {"Responsable", "Estado"}
        header = [Paragraph(col, sty_h) for col in df_local.columns]
        rows = []
        for _, r in df_local.iterrows():
            row = []
            for col, val in zip(df_local.columns, r):
                if pd.isna(val):
                    s = ""
                elif col in {"% Abonado"}:
                    s = f"{float(val):,.1f} %"
                elif isinstance(val, (int, float)) and col not in text_cols:
                    s = f"{val:,.0f}"
                else:
                    s = str(val)
                row.append(Paragraph(s, sty_l if col in text_cols else sty_r))
            rows.append(row)
        data = [header] + rows

        page_width = doc.width
        weights = []
        for c in df_local.columns:
            if c.lower().startswith("responsable"):
                weights.append(3.8)
            elif "Transacc" in c or "Cant." in c or c == "Estado":
                weights.append(1.2)
            else:
                weights.append(2.0)
        total_w = sum(weights)
        col_widths = [max(1.6*cm, page_width*(w/total_w)) for w in weights]

        tbl = Table(data, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
            ("BACKGROUND", (0,0), (-1,0), colors.whitesmoke),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("LEFTPADDING", (0,0), (-1,-1), 4),
            ("RIGHTPADDING", (0,0), (-1,-1), 4),
            ("TOPPADDING", (0,0), (-1,-1), 2),
            ("BOTTOMPADDING", (0,0), (-1,-1), 2),
            ("ROWBACKGROUNDS", (0,1), (-1,-1),
             [colors.Color(0.98,0.98,0.98), colors.white]),
        ]))

        story.append(tbl)
        doc.build(story)
    st.subheader("⚠️ Riesgos de cobro y concentración de montos")

        # ---------- Top 10 dinámico PRO ----------
    st.markdown("### 📈 Filtro por centro de costo / situación")

    c_top1, c_top2, c_top3, c_top4 = st.columns([2, 1, 1, 1])
    with c_top1:
        dim = st.selectbox("Dimensión", ["Obs", "CC1", "Sit", "CC"], index=1, key="dim_pro")
    with c_top2:
        order_by = st.radio(
            "Ordenar por",
            ["Total CLP", "N° Transacciones"],
            horizontal=True,
            index=0,
            key="order_by_pro",
        )
    with c_top3:
        chart_type = st.selectbox(
            "Visualización",
            ["Barras", "Treemap"],
            index=0,
            key="chart_type_pro",
        )
    with c_top4:
        top_n = st.slider(
            "Top N",
            min_value=5,
            max_value=30,
            value=16,
            step=1,
            key="topn_pro",
        )

    topN_raw = (
        df_f.groupby(dim)["Monto"]
        .agg(["sum", "count"])
        .rename(columns={"sum": "Total CLP", "count": "N° Transacciones"})
        .reset_index()
    )

    sort_col = "Total CLP" if order_by == "Total CLP" else "N° Transacciones"
    topN = topN_raw.sort_values(sort_col, ascending=False).head(top_n).copy()

    def color_by_sign_or_cc(series_values, series_dim=None):
        if series_dim == "CC":
            return series_values.map(
                {"INGRESO": "#10B981", "EGRESO": "#EF4444"}
            ).fillna("#2563EB")
        return series_values.apply(lambda v: "#10B981" if v >= 0 else "#EF4444")

    if chart_type == "Barras":
        # Recalcular por dimensión con split Ingreso/Egreso
        top_keys = topN[dim].tolist()
        df_dim = df_f[df_f[dim].isin(top_keys)].copy()
        df_dim["CC"] = df_dim["CC"].astype(str).str.strip().str.upper()

        agg_cc = (
            df_dim.groupby([dim, "CC"], as_index=False)["Monto"]
            .sum()
        )

        ingresos = agg_cc[agg_cc["CC"] == "INGRESO"].rename(columns={"Monto": "Ingresos"})
        egresos = agg_cc[agg_cc["CC"] == "EGRESO"].rename(columns={"Monto": "Egresos"})

        base_dim = pd.DataFrame({dim: top_keys})
        base_dim = base_dim.merge(ingresos[[dim, "Ingresos"]], on=dim, how="left")
        base_dim = base_dim.merge(egresos[[dim, "Egresos"]], on=dim, how="left")
        base_dim = base_dim.fillna(0)

        base_dim["Egresos_abs"] = base_dim["Egresos"].abs()
        base_dim["Neto"] = base_dim["Ingresos"] - base_dim["Egresos_abs"]

        # Orden según el criterio elegido
        if order_by == "Total CLP":
            base_dim = base_dim.merge(topN[[dim, "Total CLP"]], on=dim, how="left")
            base_dim = base_dim.sort_values("Total CLP", ascending=True)
        else:
            base_dim = base_dim.merge(topN[[dim, "N° Transacciones"]], on=dim, how="left")
            base_dim = base_dim.sort_values("N° Transacciones", ascending=True)

        fig_top = go.Figure()

        fig_top.add_trace(
            go.Scatter(
                x=base_dim[dim],
                y=base_dim["Ingresos"],
                mode="lines+markers",
                name="Ingresos",
                line=dict(color="#10B981", width=3),
                marker=dict(size=6),
                hovertemplate="<b>%{x}</b><br>Ingresos: $%{y:,.0f}<extra></extra>",
            )
        )
        fig_top.add_trace(
            go.Scatter(
                x=base_dim[dim],
                y=base_dim["Egresos_abs"],
                mode="lines+markers",
                name="Egresos",
                line=dict(color="#EF4444", width=3),
                marker=dict(size=6),
                hovertemplate="<b>%{x}</b><br>Egresos: $%{y:,.0f}<extra></extra>",
            )
        )
        fig_top.add_trace(
            go.Bar(
                x=base_dim[dim],
                y=base_dim["Neto"],
                name="Neto",
                marker_color="#2563EB",
                opacity=0.25,
                hovertemplate="<b>%{x}</b><br>Neto: $%{y:,.0f}<extra></extra>",
            )
        )

        fig_top.update_layout(
            title=dict(text=f"Top {top_n} por '{dim}' · {order_by}", x=0.02, xanchor="left"),
            xaxis_title=dim,
            yaxis_title="Monto (CLP)",
            template="plotly_white",
            margin=dict(l=20, r=20, t=60, b=20),
            legend=dict(orientation="h", y=1.02, x=0.02),
            hovermode="x unified",
        )
        fig_top.update_xaxes(showgrid=False)
        fig_top.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.06)", zeroline=False, tickformat=",.0f")

        st.plotly_chart(
            fig_top,
            use_container_width=True,
            config={
                "displaylogo": False,
                "displayModeBar": True,
                "modeBarButtonsToAdd": ["toImage"],
            },
        )
    else:
        treemap_df = topN.sort_values("Total CLP", ascending=False).copy()
        if dim == "CC":
            color_col = dim
            color_scale = None
        else:
            color_col = "Total CLP"
            color_scale = ["#EF4444", "#F59E0B", "#10B981"]

        fig_tree = px.treemap(
            treemap_df,
            path=[dim],
            values=sort_col if sort_col in treemap_df.columns else "Total CLP",
            color=color_col,
            color_continuous_scale=color_scale,
            title=f"Distribución Top {top_n} por '{dim}' · {order_by}",
        )
        if dim == "CC":
            fig_tree.update_traces(
                marker_colors=color_by_sign_or_cc(
                    treemap_df[dim], series_dim="CC"
                )
            )
        fig_tree.update_traces(
            hovertemplate="<b>%{label}</b><br>Valor: %{value:,.0f}<extra></extra>",
            textinfo="label+value",
            textfont=dict(size=12),
        )
        fig_tree.update_layout(
            margin=dict(l=0, r=0, t=60, b=0), template="plotly_white"
        )
        st.plotly_chart(
            fig_tree,
            use_container_width=True,
            config={
                "displaylogo": False,
                "displayModeBar": True,
                "modeBarButtonsToAdd": ["toImage"],
            },
        )


    st.caption("Nota: los montos son la suma de 'Monto' (ingresos positivos, egresos negativos) por categoría.")

    st.markdown("---")



    try:
        pdf_path = "resumen_no_pagado_abonos.pdf"
        export_resumen_pdf(tabla, pdf_path)
        with open(pdf_path, "rb") as f:
            st.download_button(
                "⬇️ Descargar PDF",
                data=f.read(),
                file_name=pdf_path,
                mime="application/pdf",
            )
    except Exception as e:
        st.warning(f"No se pudo generar PDF. Te dejo el CSV como alternativa. Detalle: {e}")
        st.download_button(
            "⬇️ Descargar CSV",
            data=tabla.to_csv(index=False).encode("utf-8"),
            file_name="resumen_no_pagado_abonos.csv",
            mime="text/csv",
        )

# =========================================================
# 🏢 TAB 3: CANON ANUAL / MENSUAL
# =========================================================
with tab_canon:
    st.subheader("🏢 Canon mensual por Año y por Esp")

    import plotly.graph_objects as go
    import numpy as np

    _data_src = df_f

    mask_canon_mensual = (
        (_data_src["CC"] == "INGRESO") &
        (
            _data_src["CC1"].str.contains("canon mensual", case=False, na=False) |
            _data_src["Obs"].str.contains("canon mensual", case=False, na=False)
        )
    )
    dm = _data_src.loc[mask_canon_mensual].copy()

    dm["Año"] = pd.to_numeric(dm["Año"], errors="coerce")
    dm["Monto"] = pd.to_numeric(
        dm["Monto"].astype(str).str.replace(r"[^\d\.-]", "", regex=True),
        errors="coerce"
    )

    agg = (
        dm.groupby(["Año","Esp"], as_index=False)["Monto"]
          .sum()
          .dropna(subset=["Año"])
          .sort_values(["Año","Esp"])
    )

    all_years = np.arange(int(agg["Año"].min()), int(agg["Año"].max())+1) if not agg.empty else []
    all_esps  = sorted(agg["Esp"].dropna().unique())
    grid = pd.MultiIndex.from_product([all_years, all_esps], names=["Año","Esp"])
    agg_full = (
        agg.set_index(["Año","Esp"])
           .reindex(grid, fill_value=0)
           .reset_index()
    )

    st.caption("El gráfico muestra el canon mensual total por año y por espacio (Esp).")

    if len(all_esps) == 0:
        st.info("No hay datos de 'canon mensual' para mostrar.")
    else:
        default_esps = all_esps[:7]
        sel_esps = st.multiselect("Selecciona Espacios a mostrar",
                                  all_esps, default=default_esps, key="sel_esps_canon")
        if sel_esps:
            agg_full = agg_full[agg_full["Esp"].isin(sel_esps)]

        palette = [
            "#2563EB","#10B981","#F59E0B","#EF4444","#8B5CF6",
            "#14B8A6","#F97316","#DC2626","#3B82F6","#22C55E",
            "#EAB308","#EC4899"
        ]

        fig_line = go.Figure()

        for i, esp in enumerate(sorted(agg_full["Esp"].unique())):
            df_e = agg_full[agg_full["Esp"] == esp]
            fig_line.add_trace(go.Scatter(
                x=df_e["Año"], y=df_e["Monto"],
                mode="lines+markers",
                name=f"Esp {esp}",
                line=dict(width=3, color=palette[i % len(palette)]),
                marker=dict(size=7),
                hovertemplate="<b>Año %{x}</b><br>Esp: "+str(esp)+"<br>Monto: $%{y:,.0f}<extra></extra>",
            ))

            if not df_e.empty:
                last_row = df_e.iloc[-1]
                fig_line.add_annotation(
                    x=last_row["Año"], y=last_row["Monto"],
                    text=f"Esp {esp}<br><b>{fmt_short(last_row['Monto'])}</b>",
                    showarrow=True, arrowhead=2, ax=30, ay=-30,
                    bgcolor="rgba(0,0,0,0.72)", bordercolor="rgba(0,0,0,0.72)",
                    font=dict(color="white", size=11)
                )

        visibility_all = [True] * len(fig_line.data)
        visibility_none = [False] * len(fig_line.data)
        fig_line.update_layout(
            updatemenus=[
                dict(
                    type="buttons",
                    direction="right",
                    x=1, xanchor="right", y=1.15, yanchor="top",
                    buttons=[
                        dict(label="Mostrar todo", method="update", args=[{"visible": visibility_all}]),
                        dict(label="Ocultar todo", method="update", args=[{"visible": visibility_none}]),
                    ]
                )
            ]
        )

        fig_line.update_layout(
            title=dict(text="Canon mensual por Año y Esp", x=0.02, xanchor="left"),
            xaxis_title="Año",
            yaxis_title="Monto (CLP)",
            hovermode="x unified",
            template="plotly_white",
            margin=dict(l=20, r=20, t=70, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0.02),
        )
        fig_line.update_xaxes(showgrid=False)
        fig_line.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.06)", zeroline=False, tickformat=",.0f")
        fig_line.update_layout(xaxis=dict(rangeslider=dict(visible=True)))

        st.plotly_chart(fig_line, use_container_width=True, config={
            "displaylogo": False,
            "displayModeBar": True,
            "modeBarButtonsToAdd": ["toImage","drawline","drawrect","eraseshape"]
        })

# =========================================================
# 🧩 TAB 4: CANON POR M²
# =========================================================
with tab_canon_m2:
    st.subheader("🧩 Canon por m² — Canon Mensual (por Año y Esp)")

    import numpy as np
    import plotly.graph_objects as go
    from io import BytesIO

    c1, c2 = st.columns([1,1])
    with c1:
        escala_m2 = st.radio("Escala", ["Mensual", "Diario"], horizontal=True,
                             index=0, key="escala_m2_final")
    with c2:
        uf_url = st.text_input("URL CSV UF (opcional: Año,UF_promedio)", value="", key="uf_url_m2_final",
                               placeholder="https://.../uf_promedio_anual.csv")

    _df = df_f

    canon_mask = (
        (_df["CC"] == "INGRESO") &
        (
            _df["CC1"].str.contains(r"canon\s*mensual|canon.*arriendo|arriendo.*mensual", case=False, na=False) |
            _df["Obs"].str.contains(r"canon\s*mensual|canon.*arriendo|arriendo.*mensual", case=False, na=False)
        )
    )
    dm = _df.loc[canon_mask].copy()

    dm["Año"] = pd.to_numeric(dm["Año"], errors="coerce")
    dm["Esp"] = pd.to_numeric(dm["Esp"], errors="coerce")
    dm["Monto"] = pd.to_numeric(dm["Monto"].astype(str).str.replace(r"[^\d\.-]", "", regex=True), errors="coerce")
    dm = dm.dropna(subset=["Año","Esp","Monto"])
    dm["Año"] = dm["Año"].astype(int)
    dm["Esp"] = dm["Esp"].astype(int)

    M2_MAP = {1:120, 2:72, 3:72, 4:72, 5:180, 6:130, 7:60}
    dm["m2"] = dm["Esp"].map(M2_MAP)
    dm = dm[dm["m2"].notna()]

    dm["Canon_m2_mes"] = dm["Monto"] / dm["m2"]
    dm["Canon_m2_dia"] = dm["Canon_m2_mes"] / 30.0

    agg = (
        dm.groupby(["Año","Esp"], as_index=False)[["Canon_m2_mes","Canon_m2_dia"]]
          .mean()
          .sort_values(["Año","Esp"])
          .copy()
    )

    years_all = (
        pd.to_numeric(_df["Año"], errors="coerce")
          .dropna()
          .astype(int)
          .sort_values()
          .unique()
          .tolist()
    )
    if not years_all:
        years_all = sorted(agg["Año"].unique().tolist())

    valor_col = "Canon_m2_mes" if escala_m2 == "Mensual" else "Canon_m2_dia"
    agg["valor_m2_clp"] = agg[valor_col]

    agg["UF_promedio"] = np.nan
    if uf_url.strip():
        try:
            uf_df = pd.read_csv(uf_url)
            uf_df = uf_df.rename(columns={c: c.strip() for c in uf_df.columns})
            if {"Año","UF_promedio"}.issubset(uf_df.columns):
                uf_df["Año"] = pd.to_numeric(uf_df["Año"], errors="coerce").astype("Int64")
                uf_df["UF_promedio"] = pd.to_numeric(uf_df["UF_promedio"], errors="coerce")
                agg = agg.merge(
                    uf_df.dropna(subset=["Año","UF_promedio"]).astype({"Año":"int"}),
                    on="Año", how="left"
                )
            else:
                st.warning("El CSV de UF debe tener columnas: Año,UF_promedio. Se omite UF.")
        except Exception as e:
            st.warning(f"No se pudo leer UF desde la URL: {e}")

    monedas = ["CLP"] + (["UF"] if agg["UF_promedio"].notna().any() else [])
    moneda_m2 = st.radio("Moneda", monedas, horizontal=True, index=0, key="moneda_m2_final")

    if moneda_m2 == "UF":
        agg["valor_m2"] = agg["valor_m2_clp"] / agg["UF_promedio"]
    else:
        agg["valor_m2"] = agg["valor_m2_clp"]

    todos_esps = sorted(agg["Esp"].unique().tolist())
    sel_esps = st.multiselect("Selecciona Espacios", todos_esps, default=todos_esps, key="sel_esps_m2_final")
    agg = agg[agg["Esp"].isin(sel_esps)]

    plot_df = (
        agg.pivot_table(index="Año", columns="Esp", values="valor_m2", aggfunc="mean")
           .reindex(years_all)
           .fillna(0)
    )

    if plot_df.empty:
        st.info("No hay datos para el filtro actual de 'canon mensual' o para los Esp seleccionados.")
    else:
        fig = go.Figure()
        x_years = plot_df.index.astype(int).values

        palette = [
            "#2563EB","#10B981","#F59E0B","#EF4444","#8B5CF6",
            "#14B8A6","#F97316","#DC2626","#3B82F6","#22C55E",
            "#EAB308","#EC4899","#0EA5E9","#A3E635"
        ]

        for i, esp in enumerate(plot_df.columns):
            y_series = plot_df[esp].values
            custom = np.where(y_series == 0, "⚠️ Sin registros de ‘canon mensual’", " ")
            fig.add_trace(go.Scatter(
                x=x_years, y=y_series, customdata=custom,
                mode="lines+markers",
                name=f"Esp {esp}",
                line=dict(width=3, color=palette[i % len(palette)]),
                marker=dict(size=7),
                hovertemplate="<b>Año %{x}</b><br>Esp: "+str(esp)+
                              "<br>Valor: %{y:,.2f}"+(" UF/m²" if moneda_m2=="UF" else " CLP/m²")+
                              "<br>%{customdata}<extra></extra>"
            ))

            if len(y_series) and pd.notna(y_series[-1]):
                fig.add_annotation(
                    x=int(x_years[-1]), y=y_series[-1],
                    text=f"Esp {esp}<br><b>{y_series[-1]:,.2f}{' UF/m²' if moneda_m2=='UF' else ' CLP/m²'}</b>",
                    showarrow=True, arrowhead=2, ax=30, ay=-30,
                    bgcolor="rgba(0,0,0,0.72)", bordercolor="rgba(0,0,0,0.72)",
                    font=dict(color="white", size=11)
                )

        titulo_y = "UF/m²" if moneda_m2 == "UF" else "CLP/m²"
        titulo_esc = "mensual" if escala_m2 == "Mensual" else "diario"
        fig.update_layout(
            title=dict(text=f"Canon por m² ({titulo_esc}) — {moneda_m2} · por Año y Esp", x=0.02, xanchor="left"),
            xaxis_title="Año", yaxis_title=titulo_y, template="plotly_white", hovermode="x",
            margin=dict(l=20, r=20, t=70, b=20),
            legend=dict(orientation="h", y=1.02, x=0.02),
            updatemenus=[dict(type="buttons", direction="right", x=1, xanchor="right", y=1.15, yanchor="top",
                              buttons=[dict(label="Mostrar todo", method="update", args=[{"visible":[True]*len(plot_df.columns)}]),
                                       dict(label="Ocultar todo", method="update", args=[{"visible":[False]*len(plot_df.columns)}])])]
        )

        if len(x_years):
            fig.update_xaxes(
                type="linear",
                tickmode="linear",
                tick0=int(x_years.min()),
                dtick=1,
                range=[int(x_years.min()) - 0.5, int(x_years.max()) + 0.5],
                showgrid=False
            )

        y_min = 0
        y_max = plot_df.replace(0, np.nan).max().max()
        y_max = float(y_max) * 1.1 if pd.notna(y_max) else 1.0
        fig.update_yaxes(range=[y_min, y_max], showgrid=True, gridcolor="rgba(0,0,0,0.06)", zeroline=False)

        st.plotly_chart(
            fig, use_container_width=True,
            config={"displaylogo": False, "displayModeBar": True,
                    "modeBarButtonsToAdd": ["toImage","drawline","drawrect","eraseshape"]}
        )

    # --- Tabla + Excel ---
    escala_lbl = "Mensual" if escala_m2 == "Mensual" else "Diario"
    st.markdown(f"#### 📄 Dataset agregado (Canon/m² — Año x Esp · {escala_lbl})")

    df_x = plot_df.reset_index().rename(columns={"index": "Año"}).copy()
    df_display = df_x.copy()

    def miles_punto(n):
        s = f"{n:,.0f}"
        return s.replace(",", ".")

    def uf_chileno(n):
        s = f"{n:,.2f}"
        s = s.replace(",", "§")
        s = s.replace(".", ",")
        s = s.replace("§", ".")
        return s

    if moneda_m2 == "CLP":
        for c in df_display.columns[1:]:
            df_display[c] = df_display[c].round(0).apply(lambda v: f"${miles_punto(v)}")
    else:
        for c in df_display.columns[1:]:
            df_display[c] = df_display[c].round(2).apply(uf_chileno)

    if moneda_m2 == "CLP":
        df_display = df_display.rename(
            columns={c: f"Esp {c} (CLP/m² · {escala_lbl})" for c in df_display.columns if c != "Año"}
        )
    else:
        df_display = df_display.rename(
            columns={c: f"Esp {c} (UF/m² · {escala_lbl})" for c in df_display.columns if c != "Año"}
        )

    # Tabla estilo Electricidad
    _render_table(
        df_display,
        header_bg="#1f4e78",
        header_fg="white",
        row_alt="#eef3fb",
        compact=False,
    )

    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="xlsxwriter") as writer:
        df_x.to_excel(writer, index=False, sheet_name="canon_m2")
        wb = writer.book
        ws = writer.sheets["canon_m2"]

        head_fmt = wb.add_format({"bold": True})
        ws.set_row(0, None, head_fmt)

        ws.set_column(0, 0, 10)
        if moneda_m2 == "CLP":
            numfmt = wb.add_format({"num_format": "$#,##0"})
            for j, c in enumerate(df_x.columns[1:], start=1):
                ws.write(0, j, f"Esp {c} (CLP/m²)", head_fmt)
        else:
            numfmt = wb.add_format({"num_format": '#,##0.00'})
            for j, c in enumerate(df_x.columns[1:], start=1):
                ws.write(0, j, f"Esp {c} (UF/m²)", head_fmt)

        ws.set_column(1, len(df_x.columns)-1, 14, numfmt)

    excel_buffer.seek(0)
    st.download_button(
        "⬇️ Descargar Excel (Canon/m² — Año x Esp)",
        data=excel_buffer.getvalue(),
        file_name=f"canon_m2_{'mensual' if escala_m2=='Mensual' else 'diario'}_{moneda_m2}_por_anio_y_esp.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

# =========================================================
# 📈 TAB 5: INGRESOS & EGRESOS (Mensual / Anual)
# =========================================================
with tab_ing_eg:
    st.subheader("📈 Ingresos vs Egresos — Totales por período")

    import plotly.graph_objects as go

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        periodo = st.radio("Periodo", ["Mensual", "Anual"], horizontal=True, index=0, key="periodo_ing_eg")
    with c2:
        st.caption("Se usan montos desde la columna F (Monto). Ingresos y egresos según columna CC.")
    with c3:
        pass

    _df = df_f.copy()
    _df = _df.dropna(subset=["Monto", "CC"])
    _df["CC"] = _df["CC"].astype(str).str.strip().str.upper()
    _df = _df[_df["CC"].isin(["INGRESO", "EGRESO"])]

    _df["Sit"] = _df["Sit"].astype(str).str.strip().str.upper()
    _df = _df[_df["Sit"].isin(["PAGADO", "NO PAGADO"])]

    # Usar columnas de la base: "Año" y "Mes"
    _df["Año_sel"] = pd.to_numeric(_df.get("Año"), errors="coerce")
    mes_raw = _df.get("Mes")
    mes_num = (
        mes_raw.astype(str)
        .str.extract(r"(\d{1,2})", expand=False)
    )
    _df["Mes_sel"] = pd.to_numeric(mes_num, errors="coerce")

    # Fallback si la columna Mes no trae datos
    if _df["Mes_sel"].isna().all():
        st.warning("La columna 'Mes' no tiene datos. Usando la columna 'Fecha' como respaldo.")
        _df["Fecha"] = pd.to_datetime(_df.get("Fecha"), errors="coerce")
        _df["Año_sel"] = _df["Fecha"].dt.year
        _df["Mes_sel"] = _df["Fecha"].dt.month

    _df = _df.dropna(subset=["Año_sel"])

    years = sorted(_df["Año_sel"].dropna().astype(int).unique().tolist())
    year_opts = ["Todos"] + years

    c_year, c_month = st.columns([1, 1])
    with c_year:
        sel_year = st.selectbox("Año", year_opts, index=0, key="year_ing_eg")
    with c_month:
        month_opts = ["Todos"] + list(range(1, 13))
        sel_month = st.selectbox("Mes", month_opts, index=0, key="month_ing_eg",
                                 disabled=(periodo == "Anual"))

    if sel_year != "Todos":
        _df = _df[_df["Año_sel"] == sel_year]
    if sel_month != "Todos" and periodo == "Mensual":
        _df = _df[_df["Mes_sel"] == sel_month]

    # Construir Periodo usando Año/Mes
    if periodo == "Mensual":
        _df = _df.dropna(subset=["Mes_sel"])
        _df["Periodo"] = pd.to_datetime(
            dict(year=_df["Año_sel"].astype(int), month=_df["Mes_sel"].astype(int), day=1),
            errors="coerce"
        )
        label_x = "Mes"
        x_hover = "%b %Y"
    else:
        _df["Periodo"] = pd.to_datetime(
            dict(year=_df["Año_sel"].astype(int), month=1, day=1),
            errors="coerce"
        )
        label_x = "Año"
        x_hover = "%Y"

    _df = _df.dropna(subset=["Periodo"])
    _df["Periodo"] = pd.to_datetime(_df["Periodo"], errors="coerce")
    _df = _df.dropna(subset=["Periodo"])

    agg_ie = (
        _df.groupby(["Periodo", "CC"], as_index=False)["Monto"]
           .sum()
           .sort_values("Periodo")
    )

    ingresos = agg_ie[agg_ie["CC"] == "INGRESO"].rename(columns={"Monto": "Ingresos"})
    egresos = agg_ie[agg_ie["CC"] == "EGRESO"].rename(columns={"Monto": "Egresos"})

    base = pd.DataFrame({"Periodo": sorted(agg_ie["Periodo"].dropna().unique())})
    base["Periodo"] = pd.to_datetime(base["Periodo"], errors="coerce")
    base = base.merge(ingresos[["Periodo", "Ingresos"]], on="Periodo", how="left")
    base = base.merge(egresos[["Periodo", "Egresos"]], on="Periodo", how="left")
    base = base.fillna(0)

    if base.empty:
        st.info("No hay datos suficientes para calcular ingresos y egresos por período.")
    else:
        base["Egresos_abs"] = base["Egresos"].abs()
        base["Neto"] = base["Ingresos"] - base["Egresos_abs"]

        total_ing = float(base["Ingresos"].sum())
        total_egr = float(base["Egresos_abs"].sum())
        total_neto = float(base["Neto"].sum())

        k1, k2, k3 = st.columns(3)
        with k1:
            st.markdown(
                card_finanza("TOTAL INGRESO", fmt_clp_largo(total_ing), "#10B981"),
                unsafe_allow_html=True,
            )
        with k2:
            st.markdown(
                card_finanza("TOTAL EGRESO", fmt_clp_largo(total_egr), "#EF4444"),
                unsafe_allow_html=True,
            )
        with k3:
            net_color = "#10B981" if total_neto >= 0 else "#EF4444"
            st.markdown(
                card_finanza("TOTAL NETO", fmt_clp_largo(total_neto), net_color),
                unsafe_allow_html=True,
            )

        fig_ie = go.Figure()

        fig_ie.add_trace(
            go.Scatter(
                x=base["Periodo"],
                y=base["Ingresos"],
                mode="lines+markers",
                name="Ingresos",
                line=dict(color="#10B981", width=3),
                marker=dict(size=6),
                hovertemplate=f"<b>{label_x} %{x_hover}</b><br>Ingresos: $%{{y:,.0f}}<extra></extra>",
            )
        )
        fig_ie.add_trace(
            go.Scatter(
                x=base["Periodo"],
                y=base["Egresos_abs"],
                mode="lines+markers",
                name="Egresos",
                line=dict(color="#EF4444", width=3),
                marker=dict(size=6),
                hovertemplate=f"<b>{label_x} %{x_hover}</b><br>Egresos: $%{{y:,.0f}}<extra></extra>",
            )
        )

        fig_ie.add_trace(
            go.Bar(
                x=base["Periodo"],
                y=base["Neto"],
                name="Neto",
                marker_color="#2563EB",
                opacity=0.25,
                hovertemplate=f"<b>{label_x} %{x_hover}</b><br>Neto: $%{{y:,.0f}}<extra></extra>",
            )
        )

        fig_ie.update_layout(
            title=dict(text=f"Ingresos y Egresos — {periodo}", x=0.02, xanchor="left"),
            xaxis_title=label_x,
            yaxis_title="Monto (CLP)",
            template="plotly_white",
            height=520,
            margin=dict(l=20, r=20, t=70, b=20),
            legend=dict(orientation="h", y=1.02, x=0.02),
            hovermode="x unified",
        )
        fig_ie.update_xaxes(showgrid=False)
        fig_ie.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.06)", zeroline=False, tickformat=",.0f")

        st.plotly_chart(
            fig_ie,
            use_container_width=True,
            config={"displaylogo": False, "displayModeBar": True, "modeBarButtonsToAdd": ["toImage"]},
        )

        st.caption("Egresos se muestran en valor absoluto para facilitar comparación visual.")

# =========================================================
# ⚡ TAB 6: ELECTRICIDAD (Excel por pestaña)
# =========================================================
with tab_electricidad:
    title_col, btn_col = st.columns([6, 1])
    with title_col:
        st.subheader("⚡ Electricidad — Liquidación por Bodega")
        st.caption("Vista idéntica al Excel: inputs generales, boleta CGE, inputs por bodega y liquidación.")
    with btn_col:
        st.markdown("")
        st.markdown("")
        # Placeholder for PDF button (se setea más abajo cuando tengamos los datos)
        pdf_btn_placeholder = st.empty()

    try:
        sheets = load_electricidad(ELECTRICIDAD_XLSX)
    except ImportError:
        sheets = {}
        st.error(
            "Falta la dependencia `openpyxl` para leer archivos .xlsx. "
            "Instálala en tu entorno con: `pip install openpyxl`"
        )
    except Exception as e:
        sheets = {}
        st.error(f"No se pudo cargar el Excel de electricidad: {e}")
    if not sheets:
        st.warning(f"No se encontró el archivo `{ELECTRICIDAD_XLSX}` en la carpeta del proyecto.")
        st.stop()

    # Preferir hojas tipo MES-AÑO (ej. FEB-2026)
    month_sheets = [s for s in sheets.keys() if "-" in s]
    sel_months = st.multiselect(
        "Meses",
        month_sheets or list(sheets.keys()),
        default=[month_sheets[0]] if month_sheets else list(sheets.keys())[:1],
        key="elec_months",
    )
    if not sel_months:
        st.info("Selecciona al menos un mes.")
        st.stop()

    # Selector de bodega
    first_raw = sheets[sel_months[0]]
    first_parsed = _parse_mes_sheet(first_raw)
    bodega_col = first_parsed["inputs_bodega"].columns[0]
    bodegas = (
        first_parsed["inputs_bodega"][bodega_col]
        .dropna()
        .astype(str)
        .tolist()
    )
    bodegas = [b for b in bodegas if b and b.upper() != "TOTAL"]
    sel_bodega = st.selectbox("Bodega", ["Todas"] + bodegas, index=0, key="elec_bodega")

    # Parse selected months
    parsed_by_month = {}
    for m in sel_months:
        df_raw = sheets[m]
        parsed_by_month[m] = _parse_mes_sheet(df_raw)

    # Encabezado estilo Excel
    st.markdown(
        """
        <div style="background:#1f4e78;color:white;padding:8px 12px;border-radius:6px;font-weight:700;">
        Liquidación Eléctrica por Bodega — Metodología de Ingeniería
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("")

    col_left, col_right = st.columns([1, 1])
    with col_left:
        st.markdown("**INPUTS GENERALES**")
        _render_table(first_parsed["inputs_generales"], header_bg="#1f4e78", header_fg="white", row_alt="#fbf3d6")
    with col_right:
        st.markdown("**BOLETA CGE (INPUTS DE FACTURACIÓN)**")
        # Promedio por concepto según meses seleccionados
        boletas = []
        for m, p in parsed_by_month.items():
            df_b = p["boleta_cge"].copy()
            df_b["Monto $"] = pd.to_numeric(df_b["Monto $"], errors="coerce")
            boletas.append(df_b)
        if boletas:
            boleta_all = pd.concat(boletas, ignore_index=True)
            boleta_avg = (
                boleta_all
                .groupby("Concepto", as_index=False)["Monto $"]
                .mean()
            )
            # mantener orden original de la primera hoja
            orden = first_parsed["boleta_cge"]["Concepto"].tolist()
            boleta_avg["__ord"] = boleta_avg["Concepto"].apply(
                lambda x: orden.index(x) if x in orden else 999
            )
            boleta_avg = boleta_avg.sort_values("__ord").drop(columns="__ord")
            _render_table(
                boleta_avg,
                header_bg="#1f4e78",
                header_fg="white",
                row_alt="#fbf3d6",
            )
        else:
            boleta_avg = first_parsed["boleta_cge"].copy()
            _render_table(boleta_avg, header_bg="#1f4e78", header_fg="white", row_alt="#fbf3d6")

    st.markdown("")
    st.markdown("**INPUTS POR BODEGA (REMARCADOR + HORARIO EFECTIVO)**")
    inputs_bodega = []
    for m, p in parsed_by_month.items():
        df_in = p["inputs_bodega"].copy()
        if sel_bodega != "Todas":
            df_in = df_in[df_in[bodega_col].astype(str) == sel_bodega]
        df_in.insert(0, "Mes", m)
        inputs_bodega.append(df_in)
    inputs_bodega = pd.concat(inputs_bodega, ignore_index=True) if inputs_bodega else pd.DataFrame()
    _render_table(
        inputs_bodega,
        header_bg="#1f4e78",
        header_fg="white",
        row_alt="#fff7e6",
        int_cols={"kWh post-18 (calc)", "kWh día (calc)"},
    )

    st.markdown("")
    st.markdown("**LIQUIDACIÓN POR BODEGA (ASIGNACIÓN DE COSTOS DE BOLETA + CRITERIO HORARIO)**")
    liquidacion = []
    for m, p in parsed_by_month.items():
        df_liq = p["liquidacion"].copy()
        if sel_bodega != "Todas":
            df_liq = df_liq[df_liq[df_liq.columns[0]].astype(str) == sel_bodega]
        df_liq.insert(0, "Mes", m)
        liquidacion.append(df_liq)
    liquidacion = pd.concat(liquidacion, ignore_index=True) if liquidacion else pd.DataFrame()
    _render_table(
        liquidacion,
        header_bg="#1f4e78",
        header_fg="white",
        row_alt="#eef8ee",
        int_cols={"kWh post-18"},
        cur_cols_extra={"IVA"},
    )

    # Gráfico profesional de Liquidación por Bodega
    st.markdown("### 📈 Liquidación por Bodega — Distribución de costos")
    liq_chart = liquidacion.copy()
    if not liq_chart.empty:
        liq_chart = liq_chart[liq_chart[liq_chart.columns[1]].astype(str).str.upper() != "TOTAL"]

    if liq_chart.empty:
        st.info("No hay datos suficientes para el gráfico.")
    else:
        # Columnas esperadas
        col_mes = "Mes"
        col_bodega = liq_chart.columns[1]
        cols_costos = ["$ Energía", "$ Punta", "$ Reactiva", "$ Cargos Fijos", "$ Interés"]
        col_total = "TOTAL c/IVA $"

        # Normalizar numéricos
        for c in cols_costos + [col_total]:
            if c in liq_chart.columns:
                liq_chart[c] = pd.to_numeric(liq_chart[c], errors="coerce")
            else:
                liq_chart[c] = 0

        import plotly.graph_objects as go

        palette = {
            "$ Energía": "#16a34a",    # verde mate
            "$ Punta": "#2563eb",      # azul mate
            "$ Reactiva": "#f59e0b",   # amarillo mate
            "$ Cargos Fijos": "#ef4444",# rojo mate
            "$ Interés": "#9ca3af",    # gris claro mate
        }

        def build_liq_fig(df_plot: pd.DataFrame, x_axis, x_title, height=520, show_legend=True):
            fig = go.Figure()
            for c in cols_costos:
                fig.add_trace(
                    go.Bar(
                        x=x_axis,
                        y=df_plot[c],
                        name=c,
                        marker=dict(color=palette.get(c, "#94a3b8")),
                        text=df_plot[c],
                        texttemplate="%{text:,.0f}",
                        textposition="inside",
                        hovertemplate=f"<b>%{{x}}</b><br>{c}: $%{{y:,.0f}}<extra></extra>",
                    )
                )
            if col_total in df_plot.columns:
                fig.add_trace(
                    go.Scatter(
                        x=x_axis,
                        y=df_plot[col_total],
                        name="TOTAL c/IVA $",
                        mode="lines+markers",
                        line=dict(color="#111827", width=3),
                        marker=dict(size=7, color="#111827"),
                        hovertemplate="<b>%{x}</b><br>Total c/IVA: $%{y:,.0f}<extra></extra>",
                        yaxis="y2",
                    )
                )
            fig.update_layout(
                template="plotly_white",
                barmode="stack",
                height=height,
                margin=dict(l=20, r=40, t=40, b=20),
                legend=dict(
                    orientation="h",
                    y=1.2,
                    x=0.5,
                    xanchor="center",
                    yanchor="bottom",
                    traceorder="normal",
                    font=dict(size=11),
                    entrywidth=120,
                    entrywidthmode="pixels",
                ) if show_legend else None,
                xaxis=dict(title=x_title, showgrid=False),
                yaxis=dict(title="Costo (CLP)", tickformat=",.0f", gridcolor="rgba(148,163,184,0.25)"),
                yaxis2=dict(
                    title="Total c/IVA (CLP)",
                    overlaying="y",
                    side="right",
                    tickformat=",.0f",
                    showgrid=False,
                ),
                hovermode="x unified",
            )
            return fig

        single_period = len(sel_months) == 1
        charts_for_pdf = []
        if sel_bodega == "Todas" and len(sel_months) > 1:
            bodegas_plot = liq_chart[col_bodega].dropna().astype(str).unique().tolist()
            cols = st.columns(2)
            for i, b in enumerate(bodegas_plot):
                df_b = liq_chart[liq_chart[col_bodega].astype(str) == b]
                fig = build_liq_fig(df_b, df_b[col_mes], "Mes", height=360, show_legend=True)
                with cols[i % 2]:
                    st.markdown(f"**{b}**")
                    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})
                charts_for_pdf.append({
                    "df": df_b,
                    "x_col": col_mes,
                    "title": f"{b}",
                    "cols_costos": cols_costos,
                    "col_total": col_total,
                    "palette": palette,
                })
        else:
            x_axis = liq_chart[col_bodega] if single_period else liq_chart[col_mes]
            x_title = "Bodega" if single_period else "Mes"
            fig = build_liq_fig(liq_chart, x_axis, x_title, height=520, show_legend=True)
            st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})
            charts_for_pdf.append({
                "df": liq_chart,
                "x_col": col_bodega if single_period else col_mes,
                "title": "",
                "cols_costos": cols_costos,
                "col_total": col_total,
                "palette": palette,
            })

        # PDF download button (ubicado en el header)
        try:
            pdf_bytes = build_electricidad_pdf(
                title="Informe Electricidad — Liquidación por Bodega",
                sel_months=sel_months,
                sel_bodega=sel_bodega,
                inputs_generales=first_parsed["inputs_generales"],
                boleta_avg=boleta_avg,
                inputs_bodega=inputs_bodega,
                liquidacion=liquidacion,
                charts=charts_for_pdf,
            )
            pdf_btn_placeholder.download_button(
                "⬇️ Descargar informe PDF",
                data=pdf_bytes,
                file_name="informe_electricidad.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception as e:
            pdf_btn_placeholder.error(f"No se pudo generar el PDF: {e}")
