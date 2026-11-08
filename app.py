import calendar
from datetime import date
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import streamlit as st

STATION = '8722670'
API = 'https://api.tidesandcurrents.noaa.gov/api/prod/datagetter'
YEAR = 2026


def noaa_get(params):
    with requests.Session() as session:
        retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
        session.mount('https://', HTTPAdapter(max_retries=retry))
        return session.get(API, params=params, timeout=(10, 45))

st.set_page_config(page_title='Highland Beach Tides 2026', layout='wide')
st.title('Highland Beach | 2026 Tide Explorer')
st.caption('NOAA Lake Worth Pier (8722670) · Astronomical predictions, not measured water levels · Feet relative to MLLW')

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_predictions(year, interval):
    # Monthly requests keep API responses manageable and permit clean retries.
    frames = []
    for month in range(1, 13):
        last = calendar.monthrange(year, month)[1]
        params = dict(begin_date=f'{year}{month:02d}01', end_date=f'{year}{month:02d}{last:02d}',
                      station=STATION, product='predictions', datum='MLLW', units='english',
                      time_zone='gmt', interval=interval, format='json', application='highland_tides_streamlit')
        try:
            response = noaa_get(params)
            response.raise_for_status()
            payload = response.json()
            if 'error' in payload:
                raise ValueError(str(payload['error']))
            records = payload.get('predictions', [])
            if not records:
                raise ValueError('NOAA returned no predictions')
            frame = pd.DataFrame(records)
            frame['utc'] = pd.to_datetime(frame['t'], utc=True)
            frame['height_ft'] = pd.to_numeric(frame['v'], errors='coerce')
            frames.append(frame)
        except (requests.RequestException, ValueError, KeyError) as exc:
            raise RuntimeError(f'NOAA request failed for {year}-{month:02d}, interval {interval}: {exc}') from exc
    df = pd.concat(frames, ignore_index=True).dropna(subset=['height_ft'])
    df = df.drop_duplicates('utc').sort_values('utc')
    df['local'] = df['utc'].dt.tz_convert('America/New_York')
    df['date'] = df['local'].dt.date
    df['month'] = df['local'].dt.strftime('%b')
    return df

with st.spinner('Retrieving NOAA predictions for 2026…'):
    try:
        hourly = fetch_predictions(YEAR, 'h')
        hilo = fetch_predictions(YEAR, 'hilo')
    except RuntimeError as exc:
        st.error(str(exc))
        st.info('Check NOAA API availability and confirm the station supports hourly predictions.')
        st.stop()

# Keep only local calendar year. GMT requests include neighboring local dates at the edges;
# retrieve boundary dates separately if needed for complete local-year coverage.
@st.cache_data(ttl=86400)
def fetch_boundary(year, interval):
    params = dict(begin_date=f'{year-1}1231', end_date=f'{year+1}0101', station=STATION,
                  product='predictions', datum='MLLW', units='english', time_zone='gmt',
                  interval=interval, format='json', application='highland_tides_streamlit')
    # The API disallows multi-year hourly ranges, so request each boundary day.
    out = []
    for day in (f'{year-1}1231', f'{year+1}0101'):
        p = {**params, 'begin_date': day, 'end_date': day}
        try:
            r = noaa_get(p)
            r.raise_for_status()
            data = r.json()
            if 'error' in data:
                raise ValueError(str(data['error']))
            frame = pd.DataFrame(data['predictions'])
            frame['utc'] = pd.to_datetime(frame['t'], utc=True)
            frame['height_ft'] = pd.to_numeric(frame['v'])
            out.append(frame)
        except (requests.RequestException, ValueError, KeyError) as exc:
            raise RuntimeError(f'Boundary prediction request failed for {day}: {exc}') from exc
    df = pd.concat(out, ignore_index=True)
    df['local'] = df['utc'].dt.tz_convert('America/New_York')
    df['date'] = df['local'].dt.date
    df['month'] = df['local'].dt.strftime('%b')
    return df

try:
    hourly = pd.concat([hourly, fetch_boundary(YEAR, 'h')], ignore_index=True)
    hilo = pd.concat([hilo, fetch_boundary(YEAR, 'hilo')], ignore_index=True)
except RuntimeError as exc:
    st.error(str(exc))
    st.stop()

hourly = hourly[hourly['local'].dt.year.eq(YEAR)].drop_duplicates('utc').sort_values('utc').copy()
hilo = hilo[hilo['local'].dt.year.eq(YEAR)].drop_duplicates('utc').sort_values('utc').copy()
expected_grid = pd.date_range(f'{YEAR}-01-01', f'{YEAR+1}-01-01', tz='America/New_York', inclusive='left', freq='h').tz_convert('UTC')
if not pd.DatetimeIndex(hourly['utc']).equals(expected_grid):
    st.error('NOAA returned an incomplete or irregular hourly series. Please reload before interpreting totals.')
    st.stop()

threshold = st.sidebar.number_input('Threshold (feet above MLLW)', value=3.0, step=0.25)
direction = st.sidebar.radio('Threshold direction', ['At or above', 'At or below'])
condition = hourly['height_ft'].ge(threshold) if direction == 'At or above' else hourly['height_ft'].le(threshold)
hourly['threshold_met'] = condition

c1, c2, c3, c4 = st.columns(4)
c1.metric('Hourly predictions', f'{len(hourly):,}')
c2.metric('Maximum', f"{hourly['height_ft'].max():.2f} ft")
c3.metric('Minimum', f"{hourly['height_ft'].min():.2f} ft")
c4.metric('Hourly samples meeting threshold', f'{int(condition.sum()):,}')

tab_annual, tab_daily, tab_threshold = st.tabs(['Annual', 'Daily', 'Threshold analysis'])
with tab_annual:
    st.subheader('Full-year predicted water levels')
    fig = px.line(hourly, x='local', y='height_ft', labels={'local':'Local time (Eastern)', 'height_ft':'Height (ft, MLLW)'})
    fig.update_layout(height=460, hovermode='x unified')
    st.plotly_chart(fig, width='stretch')
    monthly = hourly.groupby(hourly['local'].dt.month).agg(min_ft=('height_ft','min'), mean_ft=('height_ft','mean'), max_ft=('height_ft','max')).reset_index(names='month_number')
    monthly['month'] = monthly['month_number'].map(lambda m: calendar.month_abbr[m])
    st.subheader('Monthly summary')
    st.dataframe(monthly[['month','min_ft','mean_ft','max_ft']].round(2), hide_index=True, width='stretch')

with tab_daily:
    chosen = st.date_input('Select a date', value=min(max(date.today(), date(YEAR,1,1)), date(YEAR,12,31)), min_value=date(2026,1,1), max_value=date(2026,12,31))
    daily = hourly[hourly['date'].eq(chosen)]
    events = hilo[hilo['date'].eq(chosen)].copy()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=daily['local'], y=daily['height_ft'], mode='lines+markers', name='Hourly prediction'))
    if not events.empty:
        events['event'] = events['type'].map({'H':'High', 'L':'Low'}).fillna('Tide') if 'type' in events else 'Tide'
        fig.add_trace(go.Scatter(x=events['local'], y=events['height_ft'], mode='markers', marker={'size':11}, name='Predicted high/low', text=events['event'], hovertemplate='%{text}: %{y:.2f} ft<br>%{x}<extra></extra>'))
    fig.update_layout(xaxis_title='Local time (Eastern)', yaxis_title='Height (ft, MLLW)', height=450)
    st.plotly_chart(fig, width='stretch')
    if not events.empty:
        events['Time (Eastern)'] = events['local'].dt.strftime('%I:%M %p %Z')
        st.dataframe(events[['Time (Eastern)', 'event', 'height_ft']].rename(columns={'event':'Event', 'height_ft':'Height (ft MLLW)'}), hide_index=True, width='stretch')

with tab_threshold:
    st.subheader('Hourly samples meeting your threshold')
    st.caption('Counts are hourly sampled predictions, not continuous exceedance duration. Weather-driven flooding is not modeled.')
    by_month = hourly.groupby(hourly['local'].dt.month).agg(hours=('threshold_met','sum'), sampled_hours=('threshold_met','size')).reset_index(names='month_number')
    by_month['month'] = by_month['month_number'].map(lambda m: calendar.month_abbr[m])
    fig = px.bar(by_month, x='month', y='hours', labels={'month':'Month', 'hours':'Hourly samples meeting threshold'})
    st.plotly_chart(fig, width='stretch')
    st.dataframe(by_month[['month','hours','sampled_hours']], hide_index=True, width='stretch')
    matching = hourly[hourly['threshold_met']].copy()
    st.download_button('Download threshold-matching hours (CSV)', matching[['local','height_ft']].to_csv(index=False).encode(), 'threshold_hours_2026.csv', 'text/csv')

st.download_button('Download all 2026 hourly predictions (CSV)', hourly[['utc','local','height_ft']].to_csv(index=False).encode(), 'highland_beach_hourly_tides_2026.csv', 'text/csv')
st.caption('Source: NOAA CO-OPS predictions API. MLLW is a tidal datum, not ground elevation or NAVD88. Predictions exclude wind, pressure, waves, and surge. The station is a proxy for Highland Beach, not a measurement on the beach itself.')
