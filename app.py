import streamlit as st
import pandas as pd
import numpy as np
import os
import folium
from streamlit_folium import st_folium
import requests
import polyline
from streamlit_js_eval import streamlit_js_eval

# 1. Configuración de la Página y Estilos Avanzados
st.set_page_config(
    page_title="SISCONVE | Buscador de Estaciones", 
    layout="wide", 
    page_icon="⛽",
    initial_sidebar_state="expanded"
)

# Inyección de CSS corregido (Sidebar intacto, Canvas legible)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    /* === AREA DEL CANVAS PRINCIPAL (CORREGIDA) === */
    .main .block-container {
        font-family: 'Inter', sans-serif !important;
        color: #0f172a !important; /* Fuerza texto oscuro en todo el canvas */
    }
    
    /* Forzar títulos legibles en el canvas */
    .main h1, .main h2, .main h3, .main h4, .main p, .main span {
        color: #0f172a !important;
    }
    
    /* Métricas del Canvas: Fondo claro con excelente contraste */
    .main .stMetric {
        background-color: #f8fafc !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 12px !important;
        padding: 16px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
        border-top: 4px solid #f97316 !important;
    }
    .main .stMetric label {
        color: #64748b !important; /* Etiqueta gris oscuro corporativo */
        font-weight: 600 !important;
        text-transform: uppercase;
        font-size: 11px !important;
    }
    .main .stMetric .stMetricValue div {
        color: #0f172a !important; /* Número principal negro/azul oscuro */
        font-weight: 700 !important;
        font-size: 22px !important;
    }
    
    /* Tarjetas Expandibles del Canvas legibles */
    .main .stExpander {
        background-color: #ffffff !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 10px !important;
        margin-bottom: 12px !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.02) !important;
    }
    .main .streamlit-expanderHeader {
        color: #1e293b !important; /* Texto del encabezado de tarjeta visible */
        font-weight: 600 !important;
        font-size: 14px !important;
    }
    .main .streamlit-expanderContent * {
        color: #334155 !important; /* Contenido interno de la tarjeta visible */
    }
    
    /* Bloque informativo de recomendación */
    .main .stAlert {
        background-color: #fff7ed !important;
        border: 1px solid #ffedd5 !important;
    }
    .main .stAlert div {
        color: #c2410c !important;
    }
    
    /* Badges de Combustibles en el Canvas */
    .fuel-badge-on {
        background-color: #dcfce7 !important;
        color: #166534 !important;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 12px;
        font-weight: 600;
        text-align: center;
        border: 1px solid #bbf7d0;
    }
    .fuel-badge-off {
        background-color: #f1f5f9 !important;
        color: #94a3b8 !important;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 12px;
        font-weight: 500;
        text-align: center;
        border: 1px solid #e2e8f0;
    }
    
    /* Enlaces de navegación */
    .main a {
        color: #f97316 !important;
        font-weight: 600;
        text-decoration: none;
    }
    .main a:hover {
        text-decoration: underline;
    }

    /* === SIDEBAR (INTACTO COMO TE GUSTABA) === */
    [data-testid="stSidebar"] {
        background-color: #1e293b !important;
    }
    [data-testid="stSidebar"] * {
        color: #f8fafc !important;
    }
    [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
        color: #f97316 !important;
        font-weight: 600 !important;
        margin-bottom: 5px;
    }
    [data-testid="stSidebar"] input, [data-testid="stSidebar"] select {
        color: #0f172a !important;
        font-weight: 500;
    }
    .stButton button[kind="primary"] {
        background-color: #f97316 !important;
        color: white !important;
        border: none !important;
        font-weight: 600 !important;
        padding: 0.5rem 1rem !important;
        border-radius: 8px !important;
    }
    .stButton button[kind="primary"]:hover {
        background-color: #ea580c !important;
    }
</style>
""", unsafe_allow_html=True)

# Inicialización controlada de variables de estado
if 'lat_input' not in st.session_state:
    st.session_state['lat_input'] = -34.9011
if 'lon_input' not in st.session_state:
    st.session_state['lon_input'] = -56.1645
if 'trigger_gps' not in st.session_state:
    st.session_state['trigger_gps'] = False

# ==================== FUNCIONES NATIVAS OPTIMIZADAS ====================
def haversine_vectorized(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2.0)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2.0)**2
    c = 2 * np.arcsin(np.sqrt(a))
    return c * 6371.0

@st.cache_data(ttl=3600, show_spinner=False)
def get_osrm_route(origin_lat, origin_lon, dest_lat, dest_lon):
    try:
        url = f"http://router.project-osrm.org/route/v1/driving/{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
        params = {"overview": "full", "geometries": "polyline", "steps": "false"}
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data['code'] == 'Ok' and data['routes']:
                route = data['routes'][0]
                return route['distance'] / 1000.0, route['duration'] / 60.0, route['geometry']
        return None, None, None
    except Exception:
        return None, None, None

def validar_coordenadas_uruguay(lat, lon):
    return (-35.5 <= lat <= -30.0) and (-58.5 <= lon <= -53.0)

def sugerir_mejor_estacion(df_resultados):
    if df_resultados.empty: return None
    df_temp = df_resultados.copy()
    max_dist = df_temp['Distancia (km)'].max() or 1
    df_temp['score'] = ((1 - (df_temp['Distancia (km)'] / max_dist)) * 0.6 +
                        (df_temp['Premium 30-S_bool'].astype(int) + df_temp['Super 30-S_bool'].astype(int)) / 2 * 0.4)
    return df_temp.loc[df_temp['score'].idxmax()]

@st.cache_data
def load_data():
    if not os.path.exists('ESTACIONES_SISCONVE_LIMPIO.csv'):
        st.error("❌ Archivo 'ESTACIONES_SISCONVE_LIMPIO.csv' no encontrado.")
        st.stop()
    df = pd.read_csv('ESTACIONES_SISCONVE_LIMPIO.csv', sep=';')
    for c in ['Super 30-S', 'Premium 30-S', 'Gasoil 50-S', 'Gasoil 10-S']:
        df[c + '_bool'] = df[c].fillna('NO').astype(str).str.upper().str.strip() == 'SI'
    return df

ciudades_coords = {
    "Montevideo": (-34.9011, -56.1645),
    "Punta del Este": (-34.9475, -54.9338),
    "Colonia del Sacramento": (-34.4714, -57.8442),
    "Salto": (-31.3833, -57.9667),
    "Paysandú": (-32.3214, -58.0756),
    "Rivera": (-30.9053, -55.5506),
    "Maldonado": (-34.9000, -54.9500),
    "Tacuarembó": (-31.7333, -55.9833),
    "Fray Bentos": (-33.1333, -58.3000)
}

df_estaciones = load_data()

# ==================== LÓGICA GPS NATIVA ASÍNCRONA ====================
if st.sidebar.button("📍 Localizarme automáticamente (GPS)", type="primary", use_container_width=True):
    st.session_state['trigger_gps'] = True

if st.session_state['trigger_gps']:
    pos_gps = streamlit_js_eval(
        js_expressions="new Promise((r) => navigator.geolocation.getCurrentPosition((p) => r({lat:p.coords.latitude, lon:p.coords.longitude}), () => r(null), {enableHighAccuracy:true}))",
        key="gps_execution_node"
    )
    if pos_gps:
        st.session_state['lat_input'] = pos_gps['lat']
        st.session_state['lon_input'] = pos_gps['lon']
        st.session_state['trigger_gps'] = False
        st.rerun()

# Selector de ciudad rápida
ciudad_sel = st.sidebar.selectbox("Fijar posición por ciudad:", ["Seleccionar ciudad..."] + list(ciudades_coords.keys()))
if ciudad_sel != "Seleccionar ciudad...":
    st.session_state['lat_input'], st.session_state['lon_input'] = ciudades_coords[ciudad_sel]

# Entradas manuales vinculadas al Session State
lat_usuario = st.sidebar.number_input("Latitud de origen:", format="%.6f", key="lat_input")
lon_usuario = st.sidebar.number_input("Longitud de origen:", format="%.6f", key="lon_input")

if not validar_coordenadas_uruguay(lat_usuario, lon_usuario):
    st.sidebar.warning("⚠️ Coordenadas ubicadas fuera de Uruguay.")

# Filtros comerciales de búsqueda
st.sidebar.markdown("---")
st.sidebar.subheader("🔍 Filtros de Combustible")
filtro_super = st.sidebar.checkbox("Súper 30-S")
filtro_premium = st.sidebar.checkbox("Premium 30-S")
filtro_gasoil50 = st.sidebar.checkbox("Gasoil 50-S")
filtro_gasoil10 = st.sidebar.checkbox("Gasoil 10-S")

st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ Restricciones de Ruta")
filtro_depto = st.sidebar.selectbox("Departamento específico:", ['Todos'] + sorted(df_estaciones['Departamento'].unique().tolist()))
rango_distancia = st.sidebar.slider("Radio máximo de búsqueda (km):", 5, 250, 120)
top_k = st.sidebar.slider("Estaciones a mostrar:", 1, 15, 5)

tipo_distancia = st.sidebar.radio("Criterio de cálculo:", ["Distancia por carretera (OSRM)", "Distancia en línea recta (Haversine)"])
usar_osrm = (tipo_distancia == "Distancia por carretera (OSRM)")

# ==================== CÓMPUTO Y FILTRADO ====================
mascara = pd.Series(True, index=df_estaciones.index)
if filtro_super: mascara &= df_estaciones['Super 30-S_bool']
if filtro_premium: mascara &= df_estaciones['Premium 30-S_bool']
if filtro_gasoil50: mascara &= df_estaciones['Gasoil 50-S_bool']
if filtro_gasoil10: mascara &= df_estaciones['Gasoil 10-S_bool']
if filtro_depto != 'Todos': mascara &= df_estaciones['Departamento'] == filtro_depto

df_filtrado = df_estaciones[mascara].copy()

if df_filtrado.empty:
    st.warning("⚠️ No existen estaciones que cumplan con los criterios de combustible seleccionados.")
    st.stop()

# Pre-filtrado espacial rápido usando Haversine vectorizado
df_filtrado['Distancia_haversine'] = haversine_vectorized(lat_usuario, lon_usuario, df_filtrado['Latitud'].values, df_filtrado['Longitud'].values)
df_filtrado = df_filtrado[df_filtrado['Distancia_haversine'] <= rango_distancia]

if df_filtrado.empty:
    st.warning(f"⚠️ No se encontraron estaciones de servicio dentro del radio de {rango_distancia} km.")
    st.stop()

df_candidatos = df_filtrado.sort_values('Distancia_haversine').head(top_k * 2).copy()

with st.spinner("Calculando distancias óptimas..."):
    if usar_osrm:
        dist_reales, mins_reales, geometries = [], [], []
        for _, est in df_candidatos.iterrows():
            d_r, m_r, geom = get_osrm_route(lat_usuario, lon_usuario, est['Latitud'], est['Longitud'])
            dist_reales.append(d_r if d_r is not None else est['Distancia_haversine'])
            mins_reales.append(m_r)
            geometries.append(geom)
        df_candidatos['Distancia (km)'] = dist_reales
        df_candidatos['Duracion_min'] = mins_reales
        df_candidatos['Ruta_geometria'] = geometries
        df_resultados = df_candidatos.sort_values('Distancia (km)').head(top_k).copy()
    else:
        df_resultados = df_candidatos.head(top_k).copy()
        df_resultados['Distancia (km)'] = df_resultados['Distancia_haversine']
        df_resultados['Duracion_min'] = None

# ==================== RENDERIZADO DE INTERFAZ GRÁFICA ====================
st.title("⛽ Buscador de Estaciones de Combustible")
st.write("Resultados optimizados basados en tu punto de origen.")
st.markdown("---")

# Indicadores principales (Métricas corregidas en contraste)
c1, c2, c3, c4 = st.columns(4)
c1.metric("📍 Cobertura", f"{len(df_resultados)} Estaciones", f"Máx: {df_resultados['Distancia (km)'].max():.1f} km")
c2.metric("🚗 Más Cercana", df_resultados.iloc[0]['Concesionario'][:18], f"{df_resultados.iloc[0]['Distancia (km)']:.2f} km")
c3.metric("⛽ Disponibilidad Súper", f"{df_resultados['Super 30-S_bool'].sum()} disp.")
c4.metric("✨ Disponibilidad Premium", f"{df_resultados['Premium 30-S_bool'].sum()} disp.")

# Panel Principal (Distribución Asimétrica 60/40 para priorizar mapa)
st.markdown("---")
col_mapa, col_lista = st.columns([3, 2])

with col_lista:
    st.subheader("📋 Opciones de Abastecimiento")
    mejor = sugerir_mejor_estacion(df_resultados)
    if mejor is not None:
        st.info(f"🏆 **Recomendación:** Opción óptima por cercanía y servicios: **{mejor['Concesionario']}**")
        
    for idx, fila in df_resultados.iterrows():
        titulo_card = f"📍 {fila['Concesionario']} — {fila['Distancia (km)']:.2f} km"
        if 'Duracion_min' in fila and fila['Duracion_min']:
            titulo_card += f" ({fila['Duracion_min']:.0f} min)"
            
        with st.expander(titulo_card, expanded=(idx == 0)):
            st.markdown(f"**📍 Dirección:** {fila['Direccion']}, {fila['Localidad']} ({fila['Departamento']})")
            if pd.notna(fila['Teléfono']):
                st.markdown(f"**📞 Teléfono:** {int(fila['Teléfono']) if str(fila['Teléfono']).replace('.0','').isdigit() else fila['Teléfono']}")
            
            # Matriz visual de combustibles disponibles (Badges limpios corregidos)
            st.markdown("<div style='margin-bottom: 8px; font-weight:600;'>Combustibles en Planta:</div>", unsafe_allow_html=True)
            b1, b2, b3, b4 = st.columns(4)
            b1.markdown(f"<div class='{'fuel-badge-on' if fila['Super 30-S_bool'] else 'fuel-badge-off'}'>Súper</div>", unsafe_allow_html=True)
            b2.markdown(f"<div class='{'fuel-badge-on' if fila['Premium 30-S_bool'] else 'fuel-badge-off'}'>Premium</div>", unsafe_allow_html=True)
            b3.markdown(f"<div class='{'fuel-badge-on' if fila['Gasoil 50-S_bool'] else 'fuel-badge-off'}'>Gasoil 50</div>", unsafe_allow_html=True)
            b4.markdown(f"<div class='{'fuel-badge-on' if fila['Gasoil 10-S_bool'] else 'fuel-badge-off'}'>Gasoil 10</div>", unsafe_allow_html=True)
            
            # Enlaces externos de navegación directa
            st.markdown(f"<div style='margin-top:16px;'><a href='https://www.google.com/maps/dir/?api=1&origin={lat_usuario},{lon_usuario}&destination={fila['Latitud']},{fila['Longitud']}&travelmode=driving' target='_blank'>🗺️ Iniciar Navegación en Google Maps</a></div>", unsafe_allow_html=True)

with col_mapa:
    st.subheader("🗺️ Rutas de Acceso")
    mapa = folium.Map(location=[lat_usuario, lon_usuario], control_scale=True, tiles="OpenStreetMap")
    
    # Origen
    folium.Marker([lat_usuario, lon_usuario], popup='<b>📍 Tu ubicación</b>', icon=folium.Icon(color='blue', icon='user', prefix='fa')).add_to(mapa)
    puntos_en_mapa = [[lat_usuario, lon_usuario]]
    
    for _, est in df_resultados.iterrows():
        color_marker = 'green' if (est['Super 30-S_bool'] and est['Premium 30-S_bool']) else ('orange' if est['Super 30-S_bool'] else 'red')
        popup_txt = f"<b>{est['Concesionario']}</b><br>Distancia: {est['Distancia (km)']:.2f} km"
        
        folium.Marker(
            [est['Latitud'], est['Longitud']], 
            popup=folium.Popup(popup_txt, max_width=250), 
            icon=folium.Icon(color=color_marker, icon='gas-pump', prefix='fa')
        ).add_to(mapa)
        puntos_en_mapa.append([est['Latitud'], est['Longitud']])
        
        # Trazado de ruta real decodificada desde OSRM
        if usar_osrm and 'Ruta_geometria' in est and est['Ruta_geometria']:
            try:
                coords = polyline.decode(est['Ruta_geometria'])
                if coords:
                    folium.PolyLine(coords, color='#f97316', weight=4, opacity=0.75).add_to(mapa)
            except Exception:
                pass
                
    mapa.fit_bounds(puntos_en_mapa, padding=(30, 30))
    st_folium(mapa, use_container_width=True, height=480, returned_objects=[])

# ==================== CUADRO DE DATOS Y EXPORTACIÓN ====================
st.subheader("📊 Matriz Comparativa Completa")
df_table = df_resultados[['Concesionario', 'Departamento', 'Localidad', 'Direccion', 'Distancia (km)', 'Super 30-S', 'Premium 30-S', 'Gasoil 50-S', 'Gasoil 10-S']].copy()
st.dataframe(df_table, use_container_width=True, hide_index=True)

st.download_button(
    "📥 Exportar Reporte de Proximidad (CSV)", 
    data=df_resultados[['Concesionario','Direccion','Distancia (km)','Super 30-S','Premium 30-S','Gasoil 50-S','Gasoil 10-S']].to_csv(index=False, sep=';', decimal=','), 
    file_name="proximidad_estaciones.csv", 
    mime="text/csv"
)