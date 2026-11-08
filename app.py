import calendar
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
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


st.markdown("""<style>
.stApp {background:#071725;color:#e5eff5}
[data-testid="stHeader"] {background:rgba(7,23,37,.94)}
.block-container {max-width:1200px;padding-top:2rem}
h1,h2,h3,p,label,[data-testid="stMetricValue"],[data-testid="stMetricLabel"] {color:#e5eff5!important}
[data-testid="stCaptionContainer"] p {color:#98b1c2!important}
[data-testid="stSidebar"] {background:#102638}
[data-testid="stMetric"] {background:#102638;border:1px solid #244256;border-radius:16px;padding:16px}
.stTabs [data-baseweb="tab-list"] {gap:20px;border-bottom:1px solid #244256}
.stTabs [data-baseweb="tab"] {color:#a9c2d1;font-weight:600}
.stTabs [aria-selected="true"] {color:#53e0ca!important}
.hero {padding:26px;border-radius:24px;background:radial-gradient(ellipse at 85% 20%,#176579 0%,#10354a 40%,#0c2437 75%);border:1px solid #2a5266;margin:8px 0 24px}
.eyebrow {font-size:11px;letter-spacing:2px;color:#6de1d1;font-weight:700;text-transform:uppercase}
.hero h1 {font-size:clamp(30px,6vw,46px);letter-spacing:-1.5px;margin:8px 0 0;padding:0}
.hero p {color:#b2cbd8!important;margin:10px 0 0;font-size:14px}
.events,.week {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:16px 0 24px}
.event,.daycard {padding:16px;background:#102638;border:1px solid #244256;border-radius:16px}
.event .label,.daycard .label {font-size:12px;color:#9db8ca;letter-spacing:.4px}
.event .level {font-size:26px;font-weight:700;color:#66e1d0;margin:6px 0}
.event .time {font-size:13px;color:#d5e6ef}
.week {grid-template-columns:repeat(7,minmax(110px,1fr));overflow-x:auto;padding-bottom:8px}
.daycard {padding:12px}.daycard strong {display:block;margin:8px 0;color:#edf7fb}.daycard small {color:#a8c2d1}
@media(max-width:640px){.block-container{padding:1rem}.hero{padding:20px}.events{grid-template-columns:repeat(2,minmax(0,1fr))}.stTabs [data-baseweb="tab-list"]{gap:10px}.stTabs [data-baseweb="tab"]{font-size:13px}}
</style>""", unsafe_allow_html=True)
st.markdown('<div class="hero"><div class="eyebrow">Atlantic coast · Florida · 2026</div><h1>Highland Beach</h1><p>Your coastal tide outlook. Find the highs, the lows, and the hours in between.</p><p>Lake Worth Pier · NOAA 8722670 · Feet above MLLW</p></div>',unsafe_allow_html=True)

TEAL='#53e0ca'; GOLD='#ffcc76'; BLUE='#338ccb'
def polish(fig, height=370):
    fig.update_layout(template='plotly_dark',paper_bgcolor='#071725',plot_bgcolor='#0c2132',font=dict(color='#bfd3e0',size=12),height=height,margin=dict(l=10,r=12,t=35,b=30),hovermode='x unified',legend=dict(orientation='h',y=1.13,x=0),dragmode=False)
    fig.update_xaxes(gridcolor='#20384a',zeroline=False)
    fig.update_yaxes(gridcolor='#20384a',zerolinecolor='#416077')
    return fig

def chart(fig):
    st.plotly_chart(fig,width='stretch',config={'displayModeBar':False,'scrollZoom':False})

threshold = st.sidebar.number_input('Threshold (feet above MLLW)', value=3.0, step=0.25)
direction = st.sidebar.radio('Threshold direction', ['At or above', 'At or below'])
st.sidebar.caption('Astronomical predictions only. Wind, waves, pressure and storm surge are not included.')
condition = hourly['height_ft'].ge(threshold) if direction == 'At or above' else hourly['height_ft'].le(threshold)
hourly['threshold_met'] = condition

forecast, annual, thresholds = st.tabs(['Tide forecast', 'Annual outlook', 'Threshold analysis'])
with forecast:
    today = datetime.now(ZoneInfo('America/New_York')).date()
    chosen = st.date_input('Select a date', value=min(max(today,date(YEAR,1,1)),date(YEAR,12,31)),min_value=date(YEAR,1,1),max_value=date(YEAR,12,31))
    daily = hourly[hourly['date'].eq(chosen)]
    events = hilo[hilo['date'].eq(chosen)].copy()
    events['event'] = events['type'].map({'H':'High tide','L':'Low tide'})
    st.subheader(chosen.strftime('%A, %B %d'))
    st.caption('Eastern time · Hourly predictions with NOAA high/low events')
    cards=''.join(f'<div class="event"><div class="label">{"↗" if r.type=="H" else "↘"} {r.event.upper()}</div><div class="level">{r.height_ft:.2f}<span style="font-size:14px"> ft</span></div><div class="time">{r.local.strftime("%I:%M %p %Z")}</div></div>' for r in events.itertuples())
    st.markdown('<div class="events">'+cards+'</div>',unsafe_allow_html=True)
    fig=go.Figure(go.Scatter(x=daily['local'],y=daily['height_ft'],mode='lines+markers',line=dict(color=TEAL,width=3),marker=dict(size=4),fill='tozeroy',fillcolor='rgba(83,224,202,.13)',name='Hourly prediction',hovertemplate='%{y:.2f} ft<extra></extra>'))
    for kind,color,symbol in [('H',GOLD,'triangle-up'),('L',TEAL,'triangle-down')]:
        ev=events[events['type'].eq(kind)]
        fig.add_trace(go.Scatter(x=ev['local'],y=ev['height_ft'],mode='markers',marker=dict(size=12,color=color,symbol=symbol,line=dict(color='#071725',width=2)),name='High tide' if kind=='H' else 'Low tide',hovertemplate='%{y:.2f} ft<extra></extra>'))
    fig.add_hline(y=threshold,line_dash='dot',line_color=GOLD,annotation_text=f'Threshold {threshold:g} ft',annotation_position='top left')
    polish(fig);fig.update_xaxes(tickformat='%I %p',title=None);fig.update_yaxes(title='Feet · MLLW')
    chart(fig)
    st.subheader('Seven-day outlook')
    st.caption('Highest and lowest predicted tide events each day. Swipe the cards sideways on your phone.')
    cards=[]
    for offset in range(7):
        day=chosen+timedelta(days=offset)
        if day.year!=YEAR: break
        e=hilo[hilo['date'].eq(day)]
        cards.append(f'<div class="daycard"><div class="label">{day.strftime("%a %d")}</div><strong>↑ {e.height_ft.max():.2f} ft</strong><small>↓ {e.height_ft.min():.2f} ft</small></div>')
    st.markdown('<div class="week">'+''.join(cards)+'</div>',unsafe_allow_html=True)
    week=hourly[(hourly['date']>=chosen)&(hourly['date']<chosen+timedelta(days=7))].copy()
    week['clock']=week['local'].dt.strftime('%H:%M %Z')
    week['day']=week['local'].dt.strftime('%a %b %d')
    # Distinct UTC offsets preserve the repeated hour on the fall DST day.
    heat=week.pivot(index='clock',columns='day',values='height_ft').reindex(columns=week['day'].drop_duplicates())
    fig=go.Figure(go.Heatmap(z=heat.values,x=heat.columns,y=heat.index,colorscale=[[0,'#183b64'],[.4,'#237ba0'],[.7,'#53d1bb'],[1,'#ffcc76']],colorbar=dict(title='ft',thickness=9),hovertemplate='%{x}<br>%{y}<br>%{z:.2f} ft<extra></extra>'))
    polish(fig,450);fig.update_yaxes(autorange='reversed',dtick=3);chart(fig)
    with st.expander('Daily tide table'):
        events['Time (Eastern)']=events['local'].dt.strftime('%I:%M %p %Z')
        st.dataframe(events[['Time (Eastern)','event','height_ft']].rename(columns={'event':'Event','height_ft':'Height (ft MLLW)'}),hide_index=True,width='stretch')

with annual:
    st.subheader('A year at a glance')
    c1,c2,c3,c4=st.columns(4)
    c1.metric('Hourly predictions',f'{len(hourly):,}')
    c2.metric('Maximum',f"{hourly.height_ft.max():.2f} ft")
    c3.metric('Minimum',f"{hourly.height_ft.min():.2f} ft")
    c4.metric('Hourly samples meeting threshold',f'{int(condition.sum()):,}')
    envelope=hourly.groupby('date').height_ft.agg(['min','max','mean']).reset_index()
    fig=go.Figure()
    fig.add_trace(go.Scatter(x=envelope.date,y=envelope['min'],line=dict(color=BLUE,width=1),name='Daily sampled minimum'))
    fig.add_trace(go.Scatter(x=envelope.date,y=envelope['max'],line=dict(color=TEAL,width=1),fill='tonexty',fillcolor='rgba(83,224,202,.18)',name='Daily sampled maximum'))
    fig.add_trace(go.Scatter(x=envelope.date,y=envelope['mean'],line=dict(color=GOLD,width=2),name='Daily mean'))
    polish(fig);fig.update_yaxes(title='Feet · MLLW');chart(fig)
    st.caption('Shaded band: daily range of hourly samples. High/low event predictions may extend beyond this band.')
    monthly=hourly.groupby(hourly.local.dt.month).agg(min_ft=('height_ft','min'),mean_ft=('height_ft','mean'),max_ft=('height_ft','max')).reset_index(names='month_number')
    monthly['month']=monthly.month_number.map(lambda m:calendar.month_abbr[m])
    with st.expander('Monthly summary'):
        st.dataframe(monthly[['month','min_ft','mean_ft','max_ft']].round(2),hide_index=True,width='stretch')
    with st.expander('Explore every hourly prediction'):
        fig=px.line(hourly,x='local',y='height_ft',color_discrete_sequence=[TEAL]);polish(fig);fig.update_yaxes(title='Feet · MLLW');chart(fig)

with thresholds:
    st.subheader('Find your water-level window')
    st.caption('Use the sidebar to choose a threshold and direction. Counts are hourly samples, not continuous duration or a flood forecast.')
    a,b=st.columns(2)
    a.metric('Matching samples',f'{int(condition.sum()):,}')
    b.metric('Share of the year',f'{condition.mean():.1%}')
    by_month=hourly.groupby(hourly.local.dt.month).agg(hours=('threshold_met','sum'),sampled_hours=('threshold_met','size')).reset_index(names='month_number')
    by_month['month']=by_month.month_number.map(lambda m:calendar.month_abbr[m])
    fig=px.bar(by_month,x='month',y='hours',color='hours',color_continuous_scale=[BLUE,TEAL,GOLD],labels={'month':'','hours':'Matching hourly samples'})
    polish(fig);fig.update_layout(coloraxis_showscale=False);chart(fig)
    st.dataframe(by_month[['month','hours','sampled_hours']],hide_index=True,width='stretch')
    matching=hourly[hourly.threshold_met]
    st.download_button('Download matching samples',matching[['local','height_ft']].to_csv(index=False).encode(),'threshold_hours_2026.csv','text/csv')

st.divider()
st.download_button('Download all 2026 predictions',hourly[['utc','local','height_ft']].to_csv(index=False).encode(),'highland_beach_hourly_tides_2026.csv','text/csv')
st.caption('NOAA CO-OPS · Lake Worth Pier is a proxy for Highland Beach. Astronomical predictions, not measured conditions. MLLW is a tidal datum, not ground elevation or NAVD88. Wind, waves and storm surge are excluded.')
