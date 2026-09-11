"""
Peta Sebaran TB RO — Streamlit App
-----------------------------------
Tampilan mengikuti design system dashboard TB (font IBM Plex, tema teal,
kartu KPI, legend chip, tooltip HTML). Warna & ukuran titik pada peta
tetap mengikuti ANGKA ASLI dari variabel yang dipilih (tanpa dikelaskan
/ dibinning) — sesuai kebutuhan awal.

Cara menjalankan:
    pip install streamlit pandas plotly pydeck
    streamlit run app_peta_tb_ro.py

Letakkan folder .streamlit/config.toml sejajar dengan file ini supaya
tema warna teal (bukan merah default Streamlit) ikut terpakai.

Sumber data (urutan prioritas):
    1. File yang di-upload manual lewat sidebar.
    2. File lokal "tb_ro_clean.csv" di folder yang sama.
"""

import numpy as np
import pandas as pd
import plotly.express as px
import pydeck as pdk
import streamlit as st

# ============================================================
# CONFIG
# ============================================================

st.set_page_config(page_title="TB RO Facilities Dashboard", layout="wide")

DEFAULT_CSV = "tb_ro_clean.csv"

NUMERIC_COLS = [
    "Fq Res RSP 2020-2025",
    "Jumlah Terduga",
    "Terduga Sesuai Standar",
    "Notifikasi TBC",
    "TBC SO",
    "TBC RO",
    "*Est. Fq Res 2025",
    "*Est. Fq Res 2025 (%)",
]

# Point radius range (meter) — proporsional terhadap nilai ASLI variabel terpilih
MIN_RADIUS = 8000
MAX_RADIUS = 50000

# ============================================================
# DESIGN: COLOR TOKENS, TYPOGRAPHY, CSS  (mengikuti referensi)
# ============================================================

INK = "#16232E"
PAPER = "#F6F7F4"
SURFACE = "#FFFFFF"
LINE = "#DCE2DE"
TEAL = "#0B5E63"
SLATE = "#3A5A78"

# Skala warna kontinu (dari referensi) — dipakai sebagai GRADIEN, bukan kelas,
# supaya tetap merepresentasikan angka asli secara halus (interpolasi).
SEVERITY_SCALE = ["#F2D680", "#E8A33D", "#C1642F", "#93321F", "#7A1F1B"]
SEVERITY_RGB = [
    tuple(int(h.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    for h in SEVERITY_SCALE
]

CUSTOM_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@500;600&display=swap');

html, body, [class*="css"] {{
    font-family: 'IBM Plex Sans', sans-serif;
    color: {INK};
}}
.stApp {{ background-color: {PAPER}; }}

h1 {{
    font-family: 'IBM Plex Sans', sans-serif;
    font-weight: 600;
    font-size: 2rem;
    letter-spacing: -0.01em;
    color: {INK};
    border-top: 4px solid {TEAL};
    padding-top: 0.6rem;
    margin-bottom: 0.15rem;
}}
h2, h3 {{ font-family: 'IBM Plex Sans', sans-serif; font-weight: 600; color: {INK}; }}

section[data-testid="stSidebar"] {{
    background-color: {SURFACE};
    border-right: 1px solid {LINE};
}}

hr {{ border-top: 1px solid {LINE}; }}

.stButton>button {{
    border-radius: 4px;
    font-weight: 500;
    border: 1px solid {LINE};
}}

div[data-baseweb="tag"] {{
    background-color: {TEAL} !important;
    border-radius: 4px !important;
}}

.legend-row {{ display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center; margin: 0.4rem 0 1rem 0; }}
.legend-chip {{
    display: flex; align-items: center; gap: 0.35rem;
    font-size: 0.78rem; color: {INK}CC;
    border: 1px solid {LINE}; padding: 0.2rem 0.55rem;
    background-color: {SURFACE};
    font-family: 'IBM Plex Mono', monospace;
}}
.legend-gradient-bar {{
    width: 220px; height: 12px; border: 1px solid {LINE};
    background: linear-gradient(to right, {", ".join(SEVERITY_SCALE)});
}}
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def render_gradient_legend(label, vmin, vmax):
    st.markdown(
        f"""<div class="legend-row">
                <div class="legend-chip">{label}</div>
                <div class="legend-chip">{vmin:,.2f}</div>
                <div class="legend-gradient-bar"></div>
                <div class="legend-chip">{vmax:,.2f}</div>
            </div>""",
        unsafe_allow_html=True,
    )


def render_size_legend(label):
    st.markdown(
        f"""<div class="legend-row">
                <div class="legend-chip">
                    <span style="width:8px;height:8px;border-radius:50%;
                                 background:{INK}55;border:1px solid {INK}99;
                                 display:inline-block;"></span>
                    {label} rendah
                </div>
                <div class="legend-chip">
                    <span style="width:16px;height:16px;border-radius:50%;
                                 background:{INK}55;border:1px solid {INK}99;
                                 display:inline-block;"></span>
                    {label} tinggi
                </div>
            </div>""",
        unsafe_allow_html=True,
    )


def value_to_color(v, vmin, vmax):
    """Interpolasi kontinu sepanjang SEVERITY_SCALE berdasarkan nilai asli
    (bukan kelas/bin) — 0 = warna pertama, 1 = warna terakhir."""
    if vmax == vmin:
        t = 0.0
    else:
        t = (v - vmin) / (vmax - vmin)
    t = min(max(t, 0.0), 1.0)

    n = len(SEVERITY_RGB) - 1
    pos = t * n
    i = int(np.floor(pos))
    i = min(i, n - 1)
    frac = pos - i

    c0 = SEVERITY_RGB[i]
    c1 = SEVERITY_RGB[i + 1]
    r = c0[0] + (c1[0] - c0[0]) * frac
    g = c0[1] + (c1[1] - c0[1]) * frac
    b = c0[2] + (c1[2] - c0[2]) * frac
    return [int(r), int(g), int(b), 200]

MIN_RADIUS = 3000
MAX_RADIUS = 5000
# ============================================================
# LOAD DATA
# ============================================================

@st.cache_data
def load_data(path_or_buffer):
    df = pd.read_csv(path_or_buffer)
    df.columns = [c.strip() for c in df.columns]

    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.replace(",", "", regex=False)
                .str.replace("%", "", regex=False)
                .str.strip()
            )
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["Lat"] = pd.to_numeric(df["Lat"], errors="coerce")
    df["Long"] = pd.to_numeric(df["Long"], errors="coerce")
    df = df.dropna(subset=["Lat", "Long"])
    return df


def load_data_with_fallback(uploaded_file):
    if uploaded_file is not None:
        return load_data(uploaded_file), "manual upload"
    try:
        return load_data(DEFAULT_CSV), "local file"
    except FileNotFoundError:
        return None, None


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header("Data Source")
uploaded = st.sidebar.file_uploader("Upload CSV (opsional)", type=["csv"])
df, sumber = load_data_with_fallback(uploaded)

if df is None:
    st.error(
        "Data tidak ditemukan. Upload file CSV lewat sidebar, atau pastikan "
        f"file `{DEFAULT_CSV}` ada di folder yang sama dengan app ini."
    )
    st.stop()

st.sidebar.caption(f"Data dimuat dari: **{sumber}**")

st.sidebar.header("Filter")
facility_options = sorted(df["Data 2025"].dropna().unique().tolist())
selected_facilities = st.sidebar.multiselect(
    "Fasilitas", facility_options, default=[]
)

st.sidebar.header("Variabel")
metric = st.sidebar.selectbox(
    "Variabel untuk peta & grafik",
    NUMERIC_COLS,
    index=NUMERIC_COLS.index("TBC RO"),
)

fdf = df.copy()
if selected_facilities:
    fdf = fdf[fdf["Data 2025"].isin(selected_facilities)]

if fdf.empty:
    st.error("Tidak ada data untuk ditampilkan dengan filter saat ini.")
    st.stop()

# ============================================================
# HEADER
# ============================================================

st.title("Peta Sebaran TB RO Fasilitas Kesehatan")
st.caption("Sebaran lokasi fasilitas & intensitas indikator TB berdasarkan angka asli (tanpa pengelasan)")

st.divider()

# ============================================================
# MAP
# ============================================================

st.subheader(f"Peta Sebaran — {metric}")
st.caption("Warna & ukuran titik mengikuti nilai asli variabel yang dipilih di sidebar (gradien kontinu, bukan kelas)")

map_df = fdf.dropna(subset=["Lat", "Long", metric]).copy()

if map_df.empty:
    st.info("Tidak ada data untuk ditampilkan pada peta dengan filter saat ini.")
else:
    vals = map_df[metric]
    vmin, vmax = float(vals.min()), float(vals.max())
    vrange = (vmax - vmin) or 1.0

    map_df["color"] = vals.apply(lambda v: value_to_color(v, vmin, vmax))
    map_df["radius"] = MIN_RADIUS + (vals - vmin) / vrange * (MAX_RADIUS - MIN_RADIUS)

    render_gradient_legend(metric, vmin, vmax)
    render_size_legend(metric)

    view_state = pdk.ViewState(
        latitude=map_df["Lat"].mean(),
        longitude=map_df["Long"].mean(),
        zoom=5,
        pitch=0,
    )

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_df,
        get_position="[Long, Lat]",
        get_radius="radius",
        get_fill_color="color",
        pickable=True,
        stroked=True,
        get_line_color=[22, 35, 46],
        get_line_width=1,
        auto_highlight=True,
    )

    tooltip = {
        "html": f"""
        <div style="font-family:'IBM Plex Sans',Arial,sans-serif;
                    min-width:240px; max-width:300px; line-height:1.5;">
            <div style="font-size:15px; font-weight:600; margin-bottom:6px;
                        border-bottom:2px solid {TEAL}; padding-bottom:6px;">
                {{Data 2025}}
            </div>
            <table style="width:100%; border-collapse:collapse; font-size:12px;
                           font-family:'IBM Plex Mono',monospace;">
                <tr><td style="color:#5b6b73;">Jumlah Terduga</td>
                    <td style="text-align:right; font-weight:600;">{{Jumlah Terduga}}</td></tr>
                <tr><td style="color:#5b6b73;">Terduga Sesuai Standar</td>
                    <td style="text-align:right; font-weight:600;">{{Terduga Sesuai Standar}}</td></tr>
                <tr><td style="color:#5b6b73;">Notifikasi TBC</td>
                    <td style="text-align:right; font-weight:600;">{{Notifikasi TBC}}</td></tr>
                <tr><td style="color:#5b6b73;">TBC SO</td>
                    <td style="text-align:right; font-weight:600;">{{TBC SO}}</td></tr>
                <tr><td style="color:#5b6b73;">TBC RO</td>
                    <td style="text-align:right; font-weight:600;">{{TBC RO}}</td></tr>
                <tr style="border-top:1px solid {LINE};">
                    <td style="color:#5b6b73;">Est. Fq Res 2025 (%)</td>
                    <td style="text-align:right; font-weight:600;">{{*Est. Fq Res 2025 (%)}}</td></tr>
            </table>
        </div>
        """,
        "style": {
            "backgroundColor": SURFACE,
            "color": INK,
            "border": f"1px solid {LINE}",
            "borderRadius": "2px",
            "padding": "10px",
            "fontSize": "12px",
            "maxWidth": "300px",
            "whiteSpace": "normal",
        },
    }

    st.pydeck_chart(
        pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip, map_style="road"),
        use_container_width=True,
        height=700,
    )

st.divider()

# ============================================================
# BAR CHART PEMBANDING
# ============================================================

st.subheader(f"Perbandingan Antar Fasilitas — {metric}")

bar_df = fdf.dropna(subset=[metric]).sort_values(metric, ascending=False)

fig = px.bar(
    bar_df,
    x="Data 2025",
    y=metric,
    color=metric,
    color_continuous_scale=SEVERITY_SCALE,
    text=metric,
)
fig.update_layout(
    xaxis_title="",
    yaxis_title=metric,
    xaxis_tickangle=-30,
    plot_bgcolor=SURFACE,
    paper_bgcolor=SURFACE,
    font=dict(family="IBM Plex Sans", color=INK),
)
fig.update_traces(texttemplate="%{text:,.2f}", textposition="outside")
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ============================================================
# DATA LENGKAP
# ============================================================

st.subheader("Data Lengkap")
st.dataframe(fdf, use_container_width=True, hide_index=True)

csv = fdf.to_csv(index=False).encode("utf-8")
st.download_button("Download data terfilter (CSV)", csv, "tb_ro_filtered.csv", "text/csv")