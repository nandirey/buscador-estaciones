import streamlit as st
import pandas as pd
import numpy as np
import os
import folium
from streamlit_folium import st_folium
import requests
import polyline

# Configuración de la página
st.set_page_config(
    page_title="Buscador de Estaciones SISCONVE", 
    layout="wide", 
    page_icon="⛽",
    initial_sidebar_state="expanded"
)

# CSS para mejor visibilidad (colores más suaves)
st.markdown("""
<style>
    /* Sidebar con mejor contraste */
    [data-testid="stSidebar"] {
        background-color: #e8eaef !important;
    }
    
    [data-testid="stSidebar"] * {
        color: #1a1a1a !important;
    }
    
    /* Títulos en sidebar */
    [data-testid="stSidebar"] h1, 
    [data-testid="stSidebar"] h2, 
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] .stHeader {
        color: #1a1a1a !important;
        font-weight: 600 !important;
    }
    
    /* Selectores - fondo blanco, texto negro */
    .stSelectbox div[data-baseweb="select"] > div {
        background-color: white !important;
        border: 1px solid #cccccc !important;
    }
    
    .stSelectbox div[data-baseweb="select"] div {
        color: #1a1a1a !important;
    }
    
    /* Opciones del dropdown */
    div[data-baseweb="select"] ul {
        background-color: white !important;
    }
    
    div[data-baseweb="select"] li {
        color: #1a1a1a !important;
        background-color: white !important;
    }
    
    div[data-baseweb="select"] li:hover {
        background-color: #e0e0e0 !important;
    }
    
    /* Inputs numéricos */
    .stNumberInput input {
        background-color: white !important;
        color: #1a1a1a !important;
        border: 1px solid #cccccc !important;
    }
    
    /* Botón GPS personalizado */
    .gps-button {
        background: linear-gradient(135deg, #2c3e50 0%, #1a252f 100%) !important;
        color: white !important;
        border: none !important;
        padding: 12px !important;
        font-size: 16px !important;
        font-weight: bold !important;
        border-radius: 8px !important;
        cursor: pointer !important;
        width: 100% !important;
        margin-bottom: 20px !important;
        transition: all 0.3s ease !important;
    }
    .gps-button:hover {
        background: linear-gradient(135deg, #34495e 0%, #2c3e50 100%) !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2) !important;
    }
    
    /* Botón GPS en móvil */
    @media (max-width: 768px) {
        .gps-button {
            padding: 14px !important;
            font-size: 18px !important;
        }
    }
    
    /* Checkboxes */
    .stCheckbox label span {
        color: #1a1a1a !important;
    }
    
    /* Radio buttons */
    .stRadio label span {
        color: #1a1a1a !important;
    }
    
    /* Slider */
    .stSlider label {
        color: #1a1a1a !important;
    }
    
    /* Separadores */
    hr {
        border-color: #cccccc !important;
    }
</style>
""", unsafe_allow_html=True)

# Título
st.title("⛽ Buscador de Estaciones de Combustible más Cercanas")
st.write("Introduce tu ubicación actual para encontrar las estaciones de servicio más cercanas dentro de la red SISCONVE.")
st.markdown("---")

# Inicialización de Session State
if 'lat_input' not in st.session_state:
    st.session_state['lat_input'] = -34.9011
if 'lon_input' not in st.session_state:
    st.session_state['lon_input'] = -56.1645
if 'map_zoom' not in st.session_state:
    st.session_state['map_zoom'] = 12

# Funciones auxiliares
def haversine_vectorized(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2.0)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2.0)**2
    c = 2 * np.arcsin(np.sqrt(a))
    r = 6371.0
    return c * r

@st.cache_data(ttl=3600, show_spinner=False)
def get_osrm_route(origin_lat, origin_lon, dest_lat, dest_lon):
    try:
        url = f"http://router.project-osrm.org/route/v1/driving/{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
        params = {"overview": "full", "geometries": "polyline", "steps": "false"}
        response = requests.get(url, params=params, timeout=7)
        if response.status_code == 200:
            data = response.json()
            if data['code'] == 'Ok' and data['routes']:
                route = data['routes'][0]
                distancia_km = route['distance'] / 1000.0
                duracion_min = route['duration'] / 60.0
                geometria = route['geometry']
                return distancia_km, duracion_min, geometria
        return None, None, None
    except Exception:
        return None, None, None

def validar_coordenadas_uruguay(lat, lon):
    return (-35.5 <= lat <= -30.0) and (-58.5 <= lon <= -53.0)

def generar_enlace_google_maps(origin_lat, origin_lon, dest_lat, dest_lon):
    return f"https://www.google.com/maps/dir/{origin_lat},{origin_lon}/{dest_lat},{dest_lon}"

def sugerir_mejor_estacion(df_resultados):
    if df_resultados.empty:
        return None
    df_temp = df_resultados.copy()
    max_dist = df_temp['Distancia (km)'].max()
    if max_dist == 0:
        max_dist = 1
    df_temp['score'] = (
        (1 - (df_temp['Distancia (km)'] / max_dist)) * 0.6 +
        (df_temp['Premium 30-S_bool'].astype(int) + df_temp['Super 30-S_bool'].astype(int)) / 2 * 0.4
    )
    mejor = df_temp.loc[df_temp['score'].idxmax()]
    return mejor

@st.cache_data
def load_data():
    if not os.path.exists('ESTACIONES_SISCONVE_LIMPIO.csv'):
        st.error("❌ No se encontró el archivo de datos.")
        st.stop()
    try:
        df = pd.read_csv('ESTACIONES_SISCONVE_LIMPIO.csv', sep=';')
        combustibles = ['Super 30-S', 'Premium 30-S', 'Gasoil 50-S', 'Gasoil 10-S']
        for c in combustibles:
            df[c + '_bool'] = df[c].fillna('NO').astype(str).str.upper().str.strip() == 'SI'
        return df
    except Exception as e:
        st.error(f"❌ Error al cargar datos: {e}")
        st.stop()

ciudades_uruguay = {
    "Seleccionar ciudad...": None,
    "Montevideo": (-34.9011, -56.1645),
    "Punta del Este": (-34.9475, -54.9338),
    "Colonia del Sacramento": (-34.4714, -57.8442),
    "Salto": (-31.3833, -57.9667),
    "Paysandú": (-32.3214, -58.0756),
    "Rivera": (-30.9053, -55.5506),
    "Maldonado": (-34.9000, -54.9500),
    "Tacuarembó": (-31.7333, -55.9833),
    "Mercedes": (-33.2500, -58.0333),
    "Minas": (-34.3833, -55.2333),
    "San José de Mayo": (-34.3333, -56.7167),
    "Durazno": (-33.3833, -56.5167),
    "Florida": (-34.1000, -56.2167),
    "Treinta y Tres": (-33.2333, -54.3833),
    "Rocha": (-34.4833, -54.3333),
    "Artigas": (-30.4000, -56.4667),
    "Canelones": (-34.5167, -56.2833),
    "San Carlos": (-34.8000, -54.9167),
    "Carmelo": (-34.0000, -58.2833),
    "Fray Bentos": (-33.1333, -58.3000)
}

df_estaciones = load_data()

# ==================== BARRA LATERAL ====================
st.sidebar.header("📍 Tu Ubicación Actual")

# Botón GPS con streamlit_js_eval (la forma correcta para Streamlit)
try:
    from streamlit_js_eval import streamlit_js_eval, get_geolocation
    
    if st.sidebar.button("📍 Usar mi ubicación actual (GPS)", type="primary", use_container_width=True):
        with st.spinner("Obteniendo ubicación por GPS..."):
            location = get_geolocation()
            if location and location.get('coords'):
                lat = location['coords']['latitude']
                lon = location['coords']['longitude']
                accuracy = location['coords']['accuracy']
                st.session_state['lat_input'] = lat
                st.session_state['lon_input'] = lon
                st.sidebar.success(f"✅ Ubicación obtenida!\nLat: {lat:.6f}\nLon: {lon:.6f}\nPrecisión: ±{accuracy:.0f}m")
                st.rerun()
            else:
                st.sidebar.error("❌ No se pudo obtener la ubicación. Verifica los permisos del navegador.")
except ImportError:
    # Fallback: botón HTML si no está instalado streamlit_js_eval
    st.sidebar.markdown("""
    <div style="text-align: center;">
        <p style="color: #ff6b6b; font-size: 12px;">
            ⚠️ Para usar GPS, instala: pip install streamlit-js-eval
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Botón de ayuda
    if st.sidebar.button("ℹ️ Cómo activar el GPS", use_container_width=True):
        st.sidebar.info("""
        **Para usar el GPS en tu móvil:**
        1. Acepta los permisos de ubicación cuando el navegador lo solicite
        2. Si usas iPhone, ve a Configuración > Privacidad > Localización
        3. Asegúrate de que Chrome o Safari tengan permisos de ubicación
        """)

st.sidebar.markdown("---")

ciudad_seleccionada = st.sidebar.selectbox("O selecciona una ciudad:", list(ciudades_uruguay.keys()))
if ciudad_seleccionada != "Seleccionar ciudad..." and ciudades_uruguay[ciudad_seleccionada]:
    st.session_state['lat_input'], st.session_state['lon_input'] = ciudades_uruguay[ciudad_seleccionada]

lat_usuario = st.sidebar.number_input("Latitud:", format="%.6f", key="lat_input")
lon_usuario = st.sidebar.number_input("Longitud:", format="%.6f", key="lon_input")

if not validar_coordenadas_uruguay(lat_usuario, lon_usuario):
    st.sidebar.warning("⚠️ Coordenadas fuera de Uruguay")

st.sidebar.markdown("---")
st.sidebar.header("🔍 Filtros de Combustible")
filtro_super = st.sidebar.checkbox("Requiere Súper 30-S", value=False)
filtro_premium = st.sidebar.checkbox("Requiere Premium 30-S", value=False)
filtro_gasoil50 = st.sidebar.checkbox("Requiere Gasoil 50-S", value=False)
filtro_gasoil10 = st.sidebar.checkbox("Requiere Gasoil 10-S", value=False)

st.sidebar.markdown("---")
st.sidebar.header("🎯 Filtros Avanzados")
departamentos = ['Todos'] + sorted(df_estaciones['Departamento'].unique().tolist())
filtro_departamento = st.sidebar.selectbox("Departamento:", departamentos)
rango_distancia = st.sidebar.slider("Radio de búsqueda máximo (km):", min_value=5, max_value=200, value=100, step=5)
ordenar_por = st.sidebar.selectbox("Ordenar por:", ["Distancia (más cercana)", "Distancia (más lejana)", "Nombre (A-Z)"])

st.sidebar.markdown("---")
st.sidebar.header("🔢 Resultados")
top_k = st.sidebar.slider("Número de estaciones:", min_value=1, max_value=20, value=5)
mostrar_en_metros = st.sidebar.checkbox("Mostrar en metros", value=False)

st.sidebar.header("🗺️ Configuración del Mapa")
st.session_state['map_zoom'] = st.sidebar.slider("Zoom del mapa:", min_value=5, max_value=18, value=12)

st.sidebar.header("🚗 Tipo de Distancia")
tipo_distancia = st.sidebar.radio(
    "¿Cómo calcular la distancia?",
    options=["Distancia por carretera (OSRM)", "Distancia en línea recta (Haversine)"]
)
usar_osrm = (tipo_distancia == "Distancia por carretera (OSRM)")

# ==================== PROCESAMIENTO PRINCIPAL ====================
mascara = pd.Series(True, index=df_estaciones.index)
if filtro_super: mascara &= df_estaciones['Super 30-S_bool']
if filtro_premium: mascara &= df_estaciones['Premium 30-S_bool']
if filtro_gasoil50: mascara &= df_estaciones['Gasoil 50-S_bool']
if filtro_gasoil10: mascara &= df_estaciones['Gasoil 10-S_bool']
if filtro_departamento != 'Todos':
    mascara &= df_estaciones['Departamento'] == filtro_departamento

df_filtrado = df_estaciones[mascara].copy()

if df_filtrado.empty:
    st.warning("⚠️ No se encontraron estaciones con los filtros seleccionados.")
    st.stop()

with st.spinner("Calculando distancias óptimas..."):
    df_filtrado['Distancia_haversine'] = haversine_vectorized(
        lat_usuario, lon_usuario, df_filtrado['Latitud'].values, df_filtrado['Longitud'].values
    )
    df_filtrado = df_filtrado[df_filtrado['Distancia_haversine'] <= rango_distancia]
    if df_filtrado.empty:
        st.warning(f"⚠️ No hay estaciones en un radio de {rango_distancia} km.")
        st.stop()
    df_candidatos = df_filtrado.sort_values('Distancia_haversine').head(top_k * 3).copy()
    
    if usar_osrm:
        distancias_reales = []
        duraciones = []
        rutas_geometria = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        for idx, (_, estacion) in enumerate(df_candidatos.iterrows()):
            status_text.text(f"Consultando ruta {idx+1}/{len(df_candidatos)}...")
            dist_real, duracion, geometria = get_osrm_route(
                lat_usuario, lon_usuario, estacion['Latitud'], estacion['Longitud']
            )
            if dist_real is not None:
                distancias_reales.append(dist_real)
                duraciones.append(duracion)
                rutas_geometria.append(geometria)
            else:
                distancias_reales.append(estacion['Distancia_haversine'])
                duraciones.append(None)
                rutas_geometria.append(None)
            progress_bar.progress((idx + 1) / len(df_candidatos))
        progress_bar.empty()
        status_text.empty()
        df_candidatos['Distancia (km)'] = distancias_reales
        df_candidatos['Duracion_min'] = duraciones
        df_candidatos['Ruta_geometria'] = rutas_geometria
        df_resultados = df_candidatos.sort_values('Distancia (km)').head(top_k).copy()
    else:
        df_resultados = df_candidatos.head(top_k).copy()
        df_resultados['Distancia (km)'] = df_resultados['Distancia_haversine']
    
    if ordenar_por == "Distancia (más cercana)":
        df_resultados = df_resultados.sort_values('Distancia (km)')
    elif ordenar_por == "Distancia (más lejana)":
        df_resultados = df_resultados.sort_values('Distancia (km)', ascending=False)
    elif ordenar_por == "Nombre (A-Z)":
        df_resultados = df_resultados.sort_values('Concesionario')

# ==================== PANEL DE ESTADÍSTICAS ====================
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("📍 Estaciones encontradas", len(df_resultados), f"Radio {df_resultados['Distancia (km)'].max():.1f} km")
with col2:
    estacion_mas_cercana = df_resultados.iloc[0]
    st.metric("🚗 Estación más cercana", estacion_mas_cercana['Concesionario'][:20], f"{estacion_mas_cercana['Distancia (km)']:.1f} km")
with col3:
    con_super = df_resultados['Super 30-S_bool'].sum()
    st.metric("⛽ Con Súper 30-S", f"{con_super}/{len(df_resultados)}")
with col4:
    con_premium = df_resultados['Premium 30-S_bool'].sum()
    st.metric("✨ Con Premium 30-S", f"{con_premium}/{len(df_resultados)}")

st.markdown("---")

# ==================== SUGERENCIA ====================
mejor_estacion = sugerir_mejor_estacion(df_resultados)
if mejor_estacion is not None:
    st.success(f"💡 **Sugerencia:** {mejor_estacion['Concesionario']} es la mejor opción (distancia + combustibles premium)")

# ==================== RESULTADOS ====================
col_mapa, col_lista = st.columns([1, 1])

with col_lista:
    tipo_texto = "por ruta" if usar_osrm else "en línea recta"
    st.subheader(f"📋 Estaciones más cercanas ({tipo_texto})")
    
    for idx, fila in df_resultados.iterrows():
        distancia_texto = f"{fila['Distancia (km)'] * 1000:.0f} m" if (mostrar_en_metros and fila['Distancia (km)'] < 1) else f"{fila['Distancia (km)']:.2f} km"
        
        with st.expander(f"📍 {fila['Concesionario']} — {distancia_texto}"):
            st.write(f"**Dirección:** {fila['Direccion']}")
            st.write(f"**Ubicación:** {fila['Localidad']}, {fila['Departamento']}")
            st.write(f"**Teléfono:** {fila['Teléfono'] if pd.notna(fila['Teléfono']) else 'No disponible'}")
            
            if usar_osrm and 'Duracion_min' in fila and fila['Duracion_min']:
                st.write(f"**⏱️ Tiempo estimado:** {fila['Duracion_min']:.0f} minutos")
            
            col_comb1, col_comb2, col_comb3, col_comb4 = st.columns(4)
            col_comb1.write("✅ Súper" if fila['Super 30-S_bool'] else "❌ Súper")
            col_comb2.write("✅ Premium" if fila['Premium 30-S_bool'] else "❌ Premium")
            col_comb3.write("✅ Gasoil 50" if fila['Gasoil 50-S_bool'] else "❌ Gasoil 50")
            col_comb4.write("✅ Gasoil 10" if fila['Gasoil 10-S_bool'] else "❌ Gasoil 10")
            
            google_link = generar_enlace_google_maps(lat_usuario, lon_usuario, fila['Latitud'], fila['Longitud'])
            st.markdown(f"[🗺️ Ver ruta en Google Maps]({google_link})")

with col_mapa:
    st.subheader("🗺️ Mapa")
    try:
        mapa = folium.Map(location=[lat_usuario, lon_usuario], zoom_start=st.session_state['map_zoom'], control_scale=True)
        folium.Marker([lat_usuario, lon_usuario], popup='<b>📍 Tu ubicación</b>', icon=folium.Icon(color='blue')).add_to(mapa)
        
        for _, estacion in df_resultados.iterrows():
            color = 'green' if (estacion['Super 30-S_bool'] and estacion['Premium 30-S_bool']) else ('orange' if estacion['Super 30-S_bool'] else 'red')
            folium.Marker(
                [estacion['Latitud'], estacion['Longitud']], 
                popup=f"<b>{estacion['Concesionario']}</b><br>{estacion['Distancia (km)']:.1f} km",
                icon=folium.Icon(color=color)
            ).add_to(mapa)
        
        st_folium(mapa, use_container_width=True, height=450, returned_objects=[])
    except Exception as e:
        st.error(f"Error en mapa: {str(e)}")

# ==================== TABLA ====================
st.subheader("📊 Detalle de estaciones")
df_display = df_resultados[['Concesionario', 'Departamento', 'Localidad', 'Direccion', 'Distancia (km)', 'Super 30-S', 'Premium 30-S', 'Gasoil 50-S', 'Gasoil 10-S', 'Teléfono']].copy()
if mostrar_en_metros:
    df_display['Distancia'] = df_display['Distancia (km)'].apply(lambda x: f"{x*1000:.0f} m" if x < 1 else f"{x:.2f} km")
    df_display.drop('Distancia (km)', axis=1, inplace=True)
st.dataframe(df_display, use_container_width=True, hide_index=True)

# ==================== EXPORTACIÓN ====================
csv_data = df_resultados[['Concesionario', 'Departamento', 'Localidad', 'Direccion', 'Teléfono', 'Distancia (km)', 'Super 30-S', 'Premium 30-S', 'Gasoil 50-S', 'Gasoil 10-S']].copy()
csv_data['Distancia (km)'] = csv_data['Distancia (km)'].round(2)
st.download_button("📥 Descargar CSV", data=csv_data.to_csv(index=False, sep=';'), file_name=f"estaciones_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv", mime="text/csv")

st.markdown("---")
st.caption("📍 **GPS:** Haz clic en 'Usar mi ubicación actual' y permite el acceso a la ubicación")