# app.py
import requests, pandas as pd, numpy as np
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="Áreas protegidas — Explorador interactivo", layout="wide")

# ----------------------------
# Parámetros del servicio
# ----------------------------
URL = "https://geoquito.quito.gob.ec/server/rest/services/web_reference_dmot/plan_de_uso_y_gestion_del_suelo_2024/MapServer/2/query"
WHERE = "nam IS NOT NULL AND superf_ha IS NOT NULL"
OUT_FIELDS = "nam,superf_ha,map,ror,rom,own"

st.title("Sistema Nacional de Áreas Protegidas (SNAP)")
st.caption("Superficie Total (ha) — Fuente: FeatureServer DMQ")

# ----------------------------
# Configuración (sidebar)
# ----------------------------
modo_agregacion = st.sidebar.radio(
    "¿Dónde agregamos?",
    ["Servidor (recomendado)", "Cliente (como tu Dash)"],
    help="Servidor: usa outStatistics (rápido y menos tráfico). Cliente: descarga y agrupa en pandas."
)
st.sidebar.info("Si la capa cambia mucho, pulsa 'Actualizar' abajo.")

@st.cache_data(ttl=600, show_spinner=False)
def fetch_agg_servidor():
    """Agrupa en el servidor: groupByFieldsForStatistics + outStatistics"""
    params = {
        "f": "json",
        "where": WHERE,
        "groupByFieldsForStatistics": "nam",
        "outFields": "nam",
        "outStatistics": '[{"statisticType":"sum","onStatisticField":"superf_ha","outStatisticFieldName":"superf_ha"}]',
        "returnGeometry": "false"
    }
    j = requests.get(URL, params=params).json()
    rows = [f["attributes"] for f in j.get("features", [])]
    df = pd.DataFrame(rows).rename(columns={"superf_ha": "superf_ha"})
    # Traer atributos (map, ror, rom, own) por primer no-nulo (requiere otra query simple):
    if not df.empty:
        # Descargamos un subconjunto con atributos para poder llenar el panel:
        params2 = {
            "f": "json",
            "where": WHERE,
            "outFields": OUT_FIELDS,
            "returnGeometry": "false",
            "resultRecordCount": 2000,
            "resultOffset": 0
        }
        feats = []
        while True:
            j2 = requests.get(URL, params=params2).json()
            fs = j2.get("features", [])
            feats.extend(fs)
            if len(fs) < params2["resultRecordCount"]:
                break
            params2["resultOffset"] += params2["resultRecordCount"]
        df_full = pd.DataFrame([f["attributes"] for f in feats]) if feats else pd.DataFrame(columns=OUT_FIELDS.split(","))
        # Primer no-nulo por campo
        def first_nonnull(s):
            for v in s:
                if pd.notna(v) and str(v).strip() != "":
                    return v
            return None
        if not df_full.empty:
            attrs = (df_full.groupby("nam", as_index=False)
                           .agg(map=("map", first_nonnull),
                                ror=("ror", first_nonnull),
                                rom=("rom", first_nonnull),
                                own=("own", first_nonnull)))
            df = df.merge(attrs, on="nam", how="left")
    return df

@st.cache_data(ttl=600, show_spinner=False)
def fetch_agg_cliente():
    """Descarga registros y agrega en pandas (tu flujo original)"""
    rows = []
    params = {
        "where": WHERE,
        "outFields": OUT_FIELDS,
        "returnGeometry": "false",
        "f": "json",
        "resultRecordCount": 2000,
        "resultOffset": 0
    }
    while True:
        j = requests.get(URL, params=params).json()
        feats = j.get("features", [])
        rows.extend([f["attributes"] for f in feats])
        if len(feats) < params["resultRecordCount"]:
            break
        params["resultOffset"] += params["resultRecordCount"]
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # Limpieza y agregación
    def first_nonnull(s):
        for v in s:
            if pd.notna(v) and str(v).strip() != "":
                return v
        return None
    agg = (df.groupby("nam", as_index=False)
             .agg(superf_ha=("superf_ha", "sum"),
                  map=("map", first_nonnull),
                  ror=("ror", first_nonnull),
                  rom=("rom", first_nonnull),
                  own=("own", first_nonnull)))
    return agg

# Botón para refrescar cache si lo necesitas
col_a, col_b = st.columns([1, 3])
with col_a:
    if st.button("🔄 Actualizar datos"):
        fetch_agg_servidor.clear()
        fetch_agg_cliente.clear()
        st.experimental_rerun()

# Obtener datos
if modo_agregacion.startswith("Servidor"):
    agg = fetch_agg_servidor()
else:
    agg = fetch_agg_cliente()

if agg.empty or "nam" not in agg or "superf_ha" not in agg:
    st.error("No se obtuvieron datos. Verifica el servicio o los campos.")
    st.stop()

# Paleta fija por categoría (idéntica a tu Dash)
agg_for_colors = agg.sort_values("superf_ha", ascending=True).reset_index(drop=True)
greens = px.colors.sequential.Greens[-len(agg_for_colors):] if len(agg_for_colors) > 0 else []
color_map = {nam: col for nam, col in zip(agg_for_colors["nam"], greens)}

# Orden (mayor arriba en el gráfico invertido)
agg = agg.sort_values("superf_ha", ascending=False).reset_index(drop=True)

# UI principal: select y dos columnas (gráfico | panel)
selected_name = st.selectbox(
    "Selecciona un área protegida:",
    options=agg["nam"].tolist(),
    index=None,
    placeholder="Escribe y selecciona un área…",
)

COLOR_BORDER_SEL = "rgba(0,0,0,0.45)"
OPACITY_SEL = 1.0
OPACITY_OTH = 0.65

left, right = st.columns([7, 3], gap="large")

with left:
    dff_plot = agg.sort_values("superf_ha", ascending=True).reset_index(drop=True)
    base_colors = [color_map.get(n, "#7CB342") for n in dff_plot["nam"]]  # fallback verde

    if selected_name:
        opacities  = [OPACITY_SEL if n == selected_name else OPACITY_OTH for n in dff_plot["nam"]]
        line_colors = [COLOR_BORDER_SEL if n == selected_name else "rgba(0,0,0,0.25)" for n in dff_plot["nam"]]
        line_widths = [1.6 if n == selected_name else 0.8 for n in dff_plot["nam"]]
    else:
        opacities = [OPACITY_SEL] * len(dff_plot)
        line_colors = ["rgba(0,0,0,0.25)"] * len(dff_plot)
        line_widths = [0.8] * len(dff_plot)

    fig = px.bar(
        dff_plot,
        x="superf_ha", y="nam",
        labels={"nam": "Área protegida (nam)", "superf_ha": "Área (ha)"},
        orientation="h"
    )
    fig.update_traces(
        marker_color=base_colors,
        marker_line_color=line_colors,
        marker_line_width=line_widths,
        hovertemplate="<b>%{y}</b><br>Área: %{x:,.2f} ha<extra></extra>",
        text=[f"{v:.1f} ha" for v in dff_plot["superf_ha"]],
        textposition="outside",
        textfont=dict(color="#155D27", size=11)
    )
    # opacidad individual (Plotly aplica a trace completo; usamos marker.opacity por array)
    fig.data[0].marker.update(opacity=opacities)

    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=700,
        showlegend=False,
        plot_bgcolor="white",
        transition=dict(duration=500, easing="cubic-in-out")
    )
    fig.update_xaxes(
        title_text="Superficie (hectáreas)",
        gridcolor="rgba(0,0,0,0.08)",
        showline=True, linewidth=1, linecolor="rgba(0,0,0,0.4)"
    )
    fig.update_yaxes(
        title_text="Nombre del área protegida",
        autorange="reversed",
        gridcolor="rgba(0,0,0,0.05)",
        showline=True, linewidth=1, linecolor="rgba(0,0,0,0.4)"
    )
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.markdown("### Detalle")
    if selected_name:
        sel = agg.loc[agg["nam"] == selected_name].iloc[0]
        values = [sel.get("map"), sel.get("ror"), sel.get("rom"), sel.get("own")]
        values = [str(v) for v in values if pd.notna(v) and str(v).strip() != ""]
        if not values:
            values = ["(sin información disponible)"]
        st.markdown(f"**{selected_name}**")
        for v in values:
            st.markdown(
                f"<div style='padding:6px 10px;background:rgba(46,125,50,0.06);"
                f"border-radius:8px;margin-bottom:6px;text-align:center'>{v}</div>",
                unsafe_allow_html=True
            )
    else:
        st.info("Selecciona un área para ver sus datos")

