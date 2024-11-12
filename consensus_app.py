import streamlit as st
import pandas as pd
import plotly.express as px
from typing import Dict
import requests
from fuzzywuzzy import fuzz
import mstarpy
import time
import matplotlib.pyplot as plt

headers = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,\
           */*;q=0.8",
           "Accept-Encoding": "gzip, deflate, sdch, br",
           "Accept-Language": "en-US,en;q=0.8,es-ES;q=0.5,es;q=0.3",
           "Cache-Control": "no-cache", "dnt": "1",
           "Pragma": "no-cache",
           "Upgrade-Insecure-Requests": "1",
           "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:93.0)\
           Gecko/20100101 Firefox/93.0"}

# Funciones de procesamiento de datos
def get_morningstar_data(page: int, headers: Dict) -> Dict:
    """Obtiene datos de la API de Morningstar para una página específica."""
    base_url = 'https://lt.morningstar.com/api/rest.svc/klr5zyak8x/security/screener'
    params = {
        'page': str(page),
        'pageSize': '50',
        'sortOrder': 'ReturnM120 desc',
        'outputType': 'json',
        'version': '1',
        'languageId': 'es-ES',
        'currencyId': 'EUR',
        'universeIds': 'FOESP$$ALL',
        'securityDataPoints': 'SecId|LegalName|CategoryName|ReturnM120',
        'filters': '',
        'term': '',
        'subUniverseId': ''
    }
    query = '&'.join(f'{k}={v}' for k, v in params.items())
    url = f'{base_url}?{query}'

    response = requests.get(url, headers=headers)
    return response.json()

def filter_similar_funds(funds_df: pd.DataFrame, similarity_threshold: int = 85) -> pd.DataFrame:
    """Filtra fondos con nombres similares."""
    funds_to_keep = []
    funds = funds_df['Fund'].tolist()

    for i, fund1 in enumerate(funds):
        keep = True
        for j, fund2 in enumerate(funds[:i]):
            if fuzz.ratio(fund1, fund2) > similarity_threshold:
                keep = False
                break
        if keep:
            funds_to_keep.append(fund1)

    return funds_df[funds_df['Fund'].isin(funds_to_keep)]

def process_stock_appearances(df: pd.DataFrame, min_appearances: int = 4) -> pd.DataFrame:
    """Procesa y cuenta las apariciones de acciones."""
    stocks = [stock for stocks in df['Stocks'] if stocks for stock in stocks]
    stock_counts = pd.Series(stocks).value_counts().to_frame('Appearances')

    if 'GOOG' in stock_counts.index:
        stock_counts = stock_counts.drop('GOOG')

    return stock_counts[stock_counts['Appearances'] >= min_appearances]

def get_funds(headers: Dict) -> pd.DataFrame:
    """Obtiene y procesa datos de fondos de Morningstar."""
    fund_data = []

    for page in range(1, 3):
        try:
            funds_json = get_morningstar_data(page, headers)

            for row in funds_json.get('rows', []):
                if 'RV' not in row.get('CategoryName', ''):
                    continue

                try:
                    fund = mstarpy.Funds(term=row['SecId'])
                    holdings_df = fund.holdings(holdingType="equity")
                    us_stocks = holdings_df[
                        holdings_df['country'] == 'United States'
                    ].head(10)['ticker'].tolist()

                    if us_stocks:
                        fund_data.append({
                            'Id': row['SecId'],
                            'Fund': row['LegalName'],
                            'Return10A': row['ReturnM120'],
                            'Stocks': us_stocks
                        })
                except Exception as e:
                    st.warning(f"Error processing fund {row.get('SecId')}: {str(e)}")
                    continue

        except Exception as e:
            st.warning(f"Error fetching page {page}: {str(e)}")
            continue

    if not fund_data:
        return pd.DataFrame()

    df_funds = pd.DataFrame(fund_data)
    df_funds = filter_similar_funds(df_funds)
    return process_stock_appearances(df_funds)

# Configuración de la página
st.set_page_config(
    page_title="Análisis de Fondos Morningstar",
    page_icon="📈",
    layout="wide"
)

# Título y descripción
st.title("📊 CONSENSUS")
st.markdown("""
Esta aplicación analiza las posiciones principales de los mejores fondos de inversión para rankear
las acciones en las que más invierten.            
""")

# Valores fijos (eliminamos el sidebar)
MIN_APPEARANCES = 6
SIMILARITY_THRESHOLD = 85

# Modifica la función load_data para incluir headers
@st.cache_data(ttl=3600)  # Cache por 1 hora
def load_data(min_appearances: int, similarity_threshold: int, headers: Dict) -> pd.DataFrame:
    with st.spinner('Cargando datos de Morningstar...'):
        try:
            df = get_funds(headers)  # Pasa los headers a get_funds
            if df.empty:
                st.error("No se pudieron obtener datos. Por favor, intenta más tarde.")
                return pd.DataFrame()
            return df
        except Exception as e:
            st.error(f"Error al cargar los datos: {str(e)}")
            return pd.DataFrame()

# Modify the display part to avoid using background_gradient
if st.button("Cargar/Actualizar Datos"):
    # Limpiar caché
    st.cache_data.clear()
    
    # Cargar datos
    df_stocks = load_data(MIN_APPEARANCES, SIMILARITY_THRESHOLD, headers)
    
    if not df_stocks.empty:
        # Modificar el layout para dar más espacio a la visualización
        col1, col2 = st.columns([1, 2])  # Proporción 1:2 para las columnas
        
        with col1:
            st.subheader("📋 Tabla de Resultados")
            # Ajustar el estilo de la tabla
            st.dataframe(
                df_stocks,
                use_container_width=True,
                column_config={
                    "Appearances": st.column_config.NumberColumn(
                        "Apariciones",
                        width=40,
                        format="%d"
                    ),
                    "__index__": st.column_config.TextColumn(
                        "Símbolo",
                        width="medium"
                    )
                },
                height=400  # Ajustar altura de la tabla
            )
        
        with col2:
            st.subheader("📊 Visualización")
            fig = px.bar(
                df_stocks,
                x=df_stocks.index,
                y='Appearances',
                title='Frecuencia de Aparición de Acciones',
                labels={'Appearances': 'Número de Apariciones', 'index': 'Símbolo'},
                color='Appearances',
                color_continuous_scale='blues'
            )
            fig.update_layout(
                xaxis_tickangle=-45,
                showlegend=False,
                height=500,
                width=1200,  # Hacer el gráfico más ancho
                margin=dict(l=20, r=20, t=40, b=20)  # Ajustar márgenes
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # Métricas principales
        st.subheader("📈 Métricas Principales")
        metrics_col1, metrics_col2, metrics_col3 = st.columns(3)
        
        with metrics_col1:
            st.metric(
                "Total de Acciones Analizadas",
                len(df_stocks)
            )
        
        with metrics_col2:
            st.metric(
                "Apariciones Máximas",
                df_stocks['Appearances'].max()
            )
        
        with metrics_col3:
            st.metric(
                "Apariciones Promedio",
                round(df_stocks['Appearances'].mean(), 2)
            )
        
        # Exportar datos
        st.download_button(
            label="📥 Descargar Datos",
            data=df_stocks.to_csv(index=True),
            file_name="stock_analysis.csv",
            mime="text/csv"
        )

# Agregar información adicional al final
# Modificar la sección final para incluir información del autor
st.markdown("""
---
### 👨‍💻 Autor
**Jaume Antolí Plaza**

[![Twitter](https://img.shields.io/twitter/follow/jantolip?style=social)](https://twitter.com/jantolip)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Conectar-blue?style=social&logo=linkedin)](https://linkedin.com/in/jaume-antoli-plaza)

### 📊 Metodología
- Los datos se obtienen de los fondos de inversión de renta variable con mejor rentabilidad a 10 años
- Solo se consideran las 10 principales posiciones de cada fondo
- Se filtran fondos similares para evitar duplicidad
- Solo se muestran acciones estadounidenses

### 🎯 Cómo Interpretar los Resultados
- Un mayor número de apariciones indica que más fondos exitosos confían en esa acción
- Los resultados son una foto fija del momento actual
- La presencia en múltiples fondos puede indicar consenso pero no garantiza rendimiento futuro

### ⚠️ Aviso Legal
Esta aplicación es solo para fines informativos y educativos. No constituye asesoramiento financiero, recomendación de inversión ni oferta de compra o venta de valores. Los datos mostrados se obtienen de fuentes públicas y su precisión no está garantizada. Las decisiones de inversión deben tomarse tras realizar un análisis propio o consultar con un asesor financiero profesional. El autor no se hace responsable de las decisiones tomadas basándose en esta información.

### 🔄 Versión
- v1.0.0 (Noviembre 2024)
            
""")
