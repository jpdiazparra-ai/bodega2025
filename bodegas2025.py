import streamlit as st
import pandas as pd
import plotly.express as px
import base64
from pathlib import Path

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
tab_overview, tab_riesgos, tab_canon, tab_canon_m2, tab_ing_eg = st.tabs(
    ["🏠 Visión general", "⚠️ Riesgos & cobranzas", "🏢 Canon anual / mensual", "🧩 Canon por m²", "📈 Ingresos & egresos"]
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
    st.markdown("#### 📄 Dataset agregado (Canon/m² — Año x Esp)")

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
        df_display = df_display.rename(columns={c: f"Esp {c} (CLP/m²)" for c in df_display.columns if c != "Año"})
    else:
        df_display = df_display.rename(columns={c: f"Esp {c} (UF/m²)" for c in df_display.columns if c != "Año"})

    st.dataframe(df_display, hide_index=True, use_container_width=True)

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
