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

# CSS completo para corregir todos los problemas de visibilidad
st.markdown("""
<style>
    /* ===== SIDEBAR ===== */
    [data-testid="stSidebar"] {
        background-color: #e8eaef !important;
    }
    
    [data-testid="stSidebar"] * {
        color: #000000 !important;
    }
    
    [data-testid="stSidebar"] .stSelectbox label,
    [data-testid="stSidebar"] .stNumberInput label,
    [data-testid="stSidebar"] .stSlider label,
    [data-testid="stSidebar"] .stCheckbox label,
    [data-testid="stSidebar"] .stRadio label,
    [data-testid="stSidebar"] .stHeader,
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] .stMarkdown {
        color: #000000 !important;
    }
    
    /* ===== SELECTORES (DROPDOWNS) ===== */
    /* El campo del select */
    [data-baseweb="select"] div {
        background-color: white !important;
        border-color: #cccccc !important;
    }
    
    [data-baseweb="select"] div div {
        color: black !important;
    }
    
    /* Las opciones del dropdown */
    div[data-baseweb="select"] ul {
        background-color: white !important;
    }
    
    div[data-baseweb="select"] li {
        color: black !important;
        background-color: white !important;
    }
    
    div[data-baseweb="select"] li:hover {
        background-color: #e0e0e0 !important;
    }
    
    /* Texto dentro del select */
    .stSelectbox [data-testid="stMarkdown"] {
        color: black !important;
    }
    
    /* ===== INPUTS NUMÉRICOS ===== */
    .stNumberInput input {
        background-color: white !important;
        color: black !important;
        border: 1px solid #cccccc !important;
    }
    
    /* Botones + y - del number input */
    .stNumberInput button {
        background-color: #e0e0e0 !important;
        color: black !important;
        border: 1px solid #cccccc !important;
    }
    
    .stNumberInput button:hover {
        background-color: #d0d0d0 !important;
    }
    
    /* ===== SLIDER ===== */
    .stSlider label {
        color: black !important;
    }
    
    /* ===== CHECKBOX ===== */
    .stCheckbox label span {
        color: black !important;
    }
    
    /* ===== RADIO BUTTONS ===== */
    .stRadio label span {
        color: black !important;
    }
    
    /* ===== BOTONES ===== */
    .stButton button {
        background-color: #e0e0e0 !important;
        color: black !important;
        border: 1px solid #cccccc !important;
    }
    
    .stButton button:hover {
        background-color: #d0d0d0 !important;
    }
    
    .stButton button[kind="primary"] {
        background-color: #1976D2 !important;
        color: white !important;
    }
    
    .stButton button[kind="primary"]:hover {
        background-color: #1565C0 !important;
    }
    
    /* ===== WIDGETS EN GENERAL ===== */
    .stSelectbox, .stNumberInput, .stDateInput, .stTextInput {
        color: black !important;
    }
    
    /* ===== TEXTOS EN SIDEBAR ===== */
    .sidebar-content, .css-1d391kg, .css-163ttbj, .eczjsme3 {
        color: black !important;
    }
    
    /* ===== MARCADORES DE AYUDA ===== */
    .stSelectbox .st-ae {
        color: black !important;
    }
    
    /* ===== TOOLTIPS ===== */
    .stTooltipIcon svg {
        fill: black !important;
    }
    
    /* ===== SEPARADORES ===== */
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

def get_gps_location():
    try:
        from streamlit_js_eval import streamlit_js_eval
        location = streamlit_js_eval(
            js_expressions="""
            new Promise((resolve) => {
                if (!navigator.geolocation) { resolve(null); return; }
                navigator.geolocation.getCurrentPosition(
                    (position) => {
                        resolve({
                            lat: position.coords.latitude,
                            lon: position.coords.longitude,
                            accuracy: position.coords.accuracy
                        });
                    },
                    (error) => { resolve(null); },
                    { enableHighAccuracy: true, timeout: 8000, maximumAge: 0 }
                );
            })
            """,
            key="gps_location"
        )
        return location
    except Exception:
        return None

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

if st.sidebar.button("📍 Usar mi ubicación actual (GPS)", type="primary", use_container_width=True):
    with st.spinner("Obteniendo ubicación por GPS..."):
        gps_location = get_gps_location()
        if gps_location and gps_location.get('lat') and gps_location.get('lon'):
            st.session_state['lat_input'] = gps_location['lat']
            st.session_state['lon_input'] = gps_location['lon']
            st.sidebar.success(f"✅ Ubicación obtenida! Precisión: ±{gps_location.get('accuracy', 0):.0f}m")
            st.rerun()
        else:
            st.sidebar.error("❌ No se pudo obtener la ubicación.")

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
st.markdown("---")
col_stats1, col_stats2, col_stats3, col_stats4 = st.columns(4)
with col_stats1:
    st.metric(label="📍 Estaciones encontradas", value=len(df_resultados), delta=f"Radio {df_resultados['Distancia (km)'].max():.1f} km")
with col_stats2:
    estacion_mas_cercana = df_resultados.iloc[0]
    st.metric(label="🚗 Estación más cercana", value=estacion_mas_cercana['Concesionario'][:25], delta=f"{estacion_mas_cercana['Distancia (km)']:.1f} km")
with col_stats3:
    con_super = df_resultados['Super 30-S_bool'].sum()
    st.metric(label="⛽ Con Súper 30-S", value=f"{con_super}/{len(df_resultados)}")
with col_stats4:
    con_premium = df_resultados['Premium 30-S_bool'].sum()
    st.metric(label="✨ Con Premium 30-S", value=f"{con_premium}/{len(df_resultados)}")
st.markdown("---")

# ==================== SUGERENCIA INTELIGENTE ====================
mejor_estacion = sugerir_mejor_estacion(df_resultados)
if mejor_estacion is not None:
    st.success(f"💡 **Sugerencia inteligente:** {mejor_estacion['Concesionario']} es la mejor opción considerando distancia y disponibilidad de combustibles premium.")

# ==================== COMPARACIÓN DE ESTACIONES ====================
if len(df_resultados) > 1:
    st.subheader("🔄 Comparar Estaciones")
    estaciones_a_comparar = st.multiselect("Selecciona hasta 3 estaciones para comparar:", options=df_resultados['Concesionario'].tolist(), max_selections=3)
    if estaciones_a_comparar:
        df_comparacion = df_resultados[df_resultados['Concesionario'].isin(estaciones_a_comparar)]
        comparacion_data = []
        for _, estacion in df_comparacion.iterrows():
            comparacion_data.append({
                'Nombre': estacion['Concesionario'][:30],
                'Distancia': f"{estacion['Distancia (km)']:.1f} km",
                'Súper 30-S': '✅' if estacion['Super 30-S_bool'] else '❌',
                'Premium 30-S': '✅' if estacion['Premium 30-S_bool'] else '❌',
                'Gasoil 50-S': '✅' if estacion['Gasoil 50-S_bool'] else '❌',
                'Gasoil 10-S': '✅' if estacion['Gasoil 10-S_bool'] else '❌',
            })
        st.table(pd.DataFrame(comparacion_data))

# ==================== INTERFAZ PRINCIPAL DE RESULTADOS ====================
col1, col2 = st.columns([1, 1])

with col1:
    tipo_texto = "por ruta" if usar_osrm else "en línea recta"
    st.subheader(f"🔝 Las {len(df_resultados)} estaciones más cercanas ({tipo_texto})")
    for idx, fila in df_resultados.iterrows():
        if mostrar_en_metros and fila['Distancia (km)'] < 1:
            distancia_texto = f"{fila['Distancia (km)'] * 1000:.0f} metros"
        else:
            distancia_texto = f"{fila['Distancia (km)']:.2f} km"
        with st.expander(f"📍 {fila['Concesionario']} — {distancia_texto}", expanded=(idx==0)):
            col_a, col_b = st.columns([2, 1])
            with col_a:
                st.markdown(f"**📬 Dirección:** {fila['Direccion']}")
                st.markdown(f"**📍 Ubicación:** {fila['Localidad']}, {fila['Departamento']}")
                st.markdown(f"**📞 Teléfono:** {fila['Teléfono'] if pd.notna(fila['Teléfono']) else 'No disponible'}")
                if usar_osrm and 'Duracion_min' in fila and fila['Duracion_min']:
                    st.markdown(f"**⏱️ Tiempo estimado:** {fila['Duracion_min']:.0f} minutos")
                if usar_osrm and 'Distancia_haversine' in fila:
                    diff = abs(fila['Distancia (km)'] - fila['Distancia_haversine'])
                    if diff > 1:
                        st.caption(f"ℹ️ Desvío por calles: La ruta real es {diff:.1f} km más larga que la línea recta.")
            with col_b:
                distancia_relativa = (fila['Distancia (km)'] / df_resultados['Distancia (km)'].max()) * 100
                st.progress(1 - (distancia_relativa/100), text=f"🚗 Distancia relativa")
            st.markdown("**⛽ Combustibles disponibles:**")
            col_f1, col_f2, col_f3, col_f4 = st.columns(4)
            col_f1.markdown("✅ **Súper**" if fila['Super 30-S_bool'] else "❌ Súper")
            col_f2.markdown("✅ **Premium**" if fila['Premium 30-S_bool'] else "❌ Premium")
            col_f3.markdown("✅ **Gasoil 50**" if fila['Gasoil 50-S_bool'] else "❌ Gasoil 50")
            col_f4.markdown("✅ **Gasoil 10**" if fila['Gasoil 10-S_bool'] else "❌ Gasoil 10")
            st.markdown("---")
            col_link1, col_link2 = st.columns(2)
            with col_link1:
                google_maps_link = generar_enlace_google_maps(lat_usuario, lon_usuario, fila['Latitud'], fila['Longitud'])
                st.markdown(f"[🗺️ Abrir ruta en Google Maps]({google_maps_link})")
            with col_link2:
                waze_link = f"https://waze.com/ul?ll={fila['Latitud']},{fila['Longitud']}&navigate=yes"
                st.markdown(f"[🧭 Abrir ruta en Waze]({waze_link})")

with col2:
    st.subheader("🗺️ Mapa de Ubicación")
    try:
        mapa = folium.Map(location=[lat_usuario, lon_usuario], zoom_start=st.session_state.get('map_zoom', 12), control_scale=True)
        folium.Marker([lat_usuario, lon_usuario], popup='<b>📍 Tu ubicación</b>', icon=folium.Icon(color='blue', icon='info-sign')).add_to(mapa)
        coordenadas_puntos = [[lat_usuario, lon_usuario]]
        for _, estacion in df_resultados.iterrows():
            color = 'green' if (estacion['Super 30-S_bool'] and estacion['Premium 30-S_bool']) else ('orange' if estacion['Super 30-S_bool'] else 'red')
            popup_html = f"""
            <div style='font-family: sans-serif; font-size: 12px;'>
                <b>{estacion['Concesionario']}</b><br>
                <b>🚗 Distancia:</b> {estacion['Distancia (km)']:.1f} km<br>
                🏢 {estacion['Direccion'][:50]}
            </div>
            """
            folium.Marker([estacion['Latitud'], estacion['Longitud']], popup=folium.Popup(popup_html, max_width=250), icon=folium.Icon(color=color, icon='glyphicon glyphicon-dashboard')).add_to(mapa)
            coordenadas_puntos.append([estacion['Latitud'], estacion['Longitud']])
            if usar_osrm and 'Ruta_geometria' in estacion and estacion['Ruta_geometria']:
                try:
                    coords = polyline.decode(estacion['Ruta_geometria'])
                    if coords and len(coords) > 1:
                        folium.PolyLine(coords, color='#2196F3', weight=3, opacity=0.6).add_to(mapa)
                except:
                    pass
        if len(coordenadas_puntos) > 1:
            lats = [p[0] for p in coordenadas_puntos]
            lons = [p[1] for p in coordenadas_puntos]
            mapa.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]], padding=(30, 30))
        st_folium(mapa, use_container_width=True, height=500, returned_objects=[])
    except Exception as e:
        st.error(f"Error al cargar el mapa: {str(e)}")

# ==================== TABLA DETALLADA ====================
st.subheader("📊 Tabla Comparativa Detallada")
df_display = df_resultados[['Concesionario', 'Departamento', 'Localidad', 'Direccion', 'Distancia (km)', 'Super 30-S', 'Premium 30-S', 'Gasoil 50-S', 'Gasoil 10-S', 'Teléfono']].copy()
if usar_osrm and 'Distancia_haversine' in df_resultados.columns:
    df_display['Distancia Lineal (km)'] = df_resultados['Distancia_haversine'].round(2)
if usar_osrm and 'Duracion_min' in df_resultados.columns:
    df_display['Tiempo (min)'] = df_resultados['Duracion_min'].round(0).fillna(0).astype(int)
if mostrar_en_metros:
    df_display['Distancia'] = df_display['Distancia (km)'].apply(lambda x: f"{x*1000:.0f} m" if x < 1 else f"{x:.2f} km")
    df_display.drop('Distancia (km)', axis=1, inplace=True)
st.dataframe(df_display, use_container_width=True, hide_index=True)

# ==================== EXPORTACIÓN ====================
st.subheader("💾 Exportar Resultados")
csv_data = df_resultados[['Concesionario', 'Departamento', 'Localidad', 'Direccion', 'Teléfono', 'Distancia (km)', 'Super 30-S', 'Premium 30-S', 'Gasoil 50-S', 'Gasoil 10-S']].copy()
csv_data['Distancia (km)'] = csv_data['Distancia (km)'].round(2)
st.download_button(label="📥 Descargar Reporte Completo (CSV)", data=csv_data.to_csv(index=False, sep=';', decimal=','), file_name=f"estaciones_sisconve_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv", mime="text/csv")

# ==================== FOOTER ====================
st.markdown("---")
st.caption("✨ **Características:** GPS nativo | Enrutamiento OSRM | Comparación de estaciones | Sugerencia inteligente | Mapas interactivos")

with st.expander("ℹ️ Información del Sistema"):
    st.write(f"**Total de estaciones en base de datos:** {len(df_estaciones)}")
    st.write(f"**Departamentos con cobertura:** {df_estaciones['Departamento'].nunique()}")
    st.write(f"**Estaciones con Súper 30-S:** {df_estaciones['Super 30-S_bool'].sum()}")
    st.write(f"**Estaciones con Premium 30-S:** {df_estaciones['Premium 30-S_bool'].sum()}")