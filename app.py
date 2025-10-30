import requests, pandas as pd
import streamlit as st
import plotly.express as px
from plotly.colors import sample_colorscale

# ----------------------------
# Config de página
# ----------------------------
st.set_page_config(page_title="SNAP — Explorador Interactivo", layout="wide")

# ----------------------------
# Parámetros del servicio
# ----------------------------
URL = "https://geoquito.quito.gob.ec/server/rest/services/web_reference_dmot/plan_de_uso_y_gestion_del_suelo_2024/MapServer/2/query"
WHERE = "nam IS NOT NULL AND superf_ha IS NOT NULL"
OUT_FIELDS = "nam,superf_ha,map,ror,rom,own"

# ----------------------------
# Helpers
# ----------------------------
@st.cache_data(ttl=600, show_spinner=False)
def fetch_agg_servidor():
    """Agrega en el servidor: groupBy + sum(superf_ha) y trae primeros atributos no-nulos."""
    # 1) Agregación en el servidor
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
    df = pd.DataFrame(rows)

    # 2) Traer atributos para panel (primer no-nulo)
    def first_nonnull(s):
        for v in s:
            if pd.notna(v) and str(v).strip() != "":
                return v
        return None

    # Descarga paginada sólo con campos de interés
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

    if feats:
        df_full = pd.DataFrame([f["attributes"] for f in feats])
        attrs = (df_full.groupby("nam", as_index=False)
                       .agg(map=("map", first_nonnull),
                            ror=("ror", first_nonnull),
                            rom=("rom", first_nonnull),
                            own=("own", first_nonnull)))
        df = df.merge(attrs, on="nam", how="left")

    # limpieza y orden
    if not df.empty:
        df["superf_ha"] = pd.to_numeric(df["superf_ha"], errors="coerce").fillna(0)
        # Orden descendente: mayor a menor (usaremos esta secuencia para el eje Y)
        df = df.sort_values("superf_ha", ascending=False).reset_index(drop=True)
    return df

# ----------------------------
# UI: encabezado “impactante”
# ----------------------------
st.markdown(
    """
    <div style="padding: 10px 16px; border-radius: 14px;
                background: linear-gradient(90deg, #f6f7fb 0%, #ffffff 60%);
                border: 1px solid rgba(0,0,0,0.06);
                box-shadow: 0 8px 22px rgba(0,0,0,0.06);">
      <div style="display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap;">
        <div style="font-weight:800; font-size:22px; color:#27367c;">
          Sistema Nacional de Áreas Protegidas (SNAP)
        </div>
        <div style="opacity:.75; font-size:14px;">
          Superficie total (ha)
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True
)

# ----------------------------
# Datos
# ----------------------------
agg = fetch_agg_servidor()
if agg.empty or "nam" not in agg or "superf_ha" not in agg:
    st.error("No se obtuvieron datos. Verifica el servicio o los campos.")
    st.stop()

# KPIs
total_ha = agg["superf_ha"].sum()
n_areas = len(agg)

k1, k2, _ = st.columns([1, 1, 6])
with k1:
    st.metric("Superficie total", f"{total_ha:,.0f} ha")
with k2:
    st.metric("Áreas protegidas", f"{n_areas:,}")

# Selector
selected_name = st.selectbox(
    "Selecciona un área protegida:",
    options=agg["nam"].tolist(),
    index=None,
    placeholder="Escribe y selecciona un área…",
)

# ----------------------------
# Gráfico
# ----------------------------
left, right = st.columns([7, 3], gap="large")

with left:
    # --- ORDEN ---
    # Queremos la mayor arriba. Definimos explícitamente el orden de categorías:
    y_order_top_first = agg["nam"].tolist()  # ya viene mayor→menor por el sort previo

    # Para construir colores verdes de claro (menor) a oscuro (mayor):
    # Creamos posiciones equiespaciadas y las mapeamos a la escala "Greens".
    n = len(agg)
    positions = [i/(n-1) if n > 1 else 1.0 for i in range(n)]
    # Como y_order_top_first es mayor→menor, queremos más oscuro al inicio (arriba).
    # sample_colorscale asigna positions en orden; usamos directamente:
    base_colors_desc = sample_colorscale("Greens", positions)  # pos=0 -> más claro, pos=1 -> más oscuro
    # Invertimos para que la primera (mayor) sea la más oscura:
    base_colors_desc = base_colors_desc[::-1]

    # Opacidad y línea según selección
    if selected_name:
        opacities  = [1.0 if n_ == selected_name else 0.55 for n_ in y_order_top_first]
        line_colors = ["rgba(0,0,0,0.55)" if n_ == selected_name else "rgba(0,0,0,0.25)" for n_ in y_order_top_first]
        line_widths = [1.8 if n_ == selected_name else 0.8 for n_ in y_order_top_first]
    else:
        opacities = [0.85] * len(y_order_top_first)
        line_colors = ["rgba(0,0,0,0.25)"] * len(y_order_top_first)
        line_widths = [0.8] * len(y_order_top_first)

    # Plotly requiere un DataFrame ordenado como se graficará
    dff_plot = agg.copy()  # mayor→menor

    fig = px.bar(
        dff_plot,
        x="superf_ha",
        y="nam",
        orientation="h",
        labels={"nam": "Área protegida", "superf_ha": "Superficie (ha)"},
    )

    # Barras más delgadas: mayor separación
    fig.update_layout(
        template="plotly_white",
        height=min(900, max(420, 24 * len(dff_plot) + 140)),
        margin=dict(l=10, r=10, t=8, b=10),
        showlegend=False,
        bargap=0.35,
    )

    # Aplicar colores, bordes y etiquetas
    fig.update_traces(
        marker_color=base_colors_desc,
        marker_line_color=line_colors,
        marker_line_width=line_widths,
        hovertemplate="<b>%{y}</b><br>Área: %{x:,.2f} ha<extra></extra>",
        text=[f"{v:,.1f} ha" for v in dff_plot["superf_ha"]],
        textposition="outside",
        textfont=dict(color="rgba(21,93,39,0.9)", size=11)  # verdoso
    )
    # Opacidad por barra
    fig.data[0].marker.update(opacity=opacities)

    # --- Forzar orden para que la mayor quede ARRIBA ---
    # Usamos 'array' + 'categoryarray' en el eje Y con la lista mayor→menor.
    fig.update_yaxes(
        title_text="Área protegida",
        categoryorder="array",
        categoryarray=y_order_top_first,  # este orden se respeta
        autorange="reversed",             # con array, reversed pone la primera categoría ARRIBA
        gridcolor="rgba(0,0,0,0.04)",
        showline=True, linewidth=1, linecolor="rgba(0,0,0,0.35)",
    )
    fig.update_xaxes(
        title_text="Superficie (ha)",
        gridcolor="rgba(0,0,0,0.07)",
        zeroline=False,
        showline=True, linewidth=1, linecolor="rgba(0,0,0,0.35)"
    )

    # Evitar corte de labels
    fig.update_layout(xaxis=dict(constrain="domain"))
    fig.update_traces(cliponaxis=False)

    st.plotly_chart(fig, use_container_width=True)

with right:
    st.markdown("### Detalle")
    if selected_name:
        sel = agg.loc[agg["nam"] == selected_name].iloc[0]
        values = [sel.get("map"), sel.get("ror"), sel.get("rom"), sel.get("own")]
        values = [str(v) for v in values if pd.notna(v) and str(v).strip() != ""]
        if not values:
            values = ["(sin información disponible)"]
        st.markdown(
            """
            <div style="background:white;border:1px solid rgba(0,0,0,0.08);border-radius:12px;
                        box-shadow:0 6px 18px rgba(0,0,0,0.06);padding:14px;">
              <div style="font-weight:800;color:#155D27;margin-bottom:8px;text-align:center;">{name}</div>
              {chips}
            </div>
            """.format(
                name=selected_name,
                chips="".join(
                    f"<div style='padding:8px 10px;background:rgba(21,93,39,0.08);"
                    f"border-radius:8px;margin-bottom:6px;text-align:center'>{v}</div>"
                    for v in values
                )
            ),
            unsafe_allow_html=True
        )
    else:
        st.info("Selecciona un área para ver sus datos")

