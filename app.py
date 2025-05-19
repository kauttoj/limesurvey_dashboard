import base64
import json
import os
import time
import threading
import tempfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import dash
from dash import html, dcc
from dash.dependencies import Input, Output, State
import plotly.express as px
import dash_bootstrap_components as dbc
import requests
import textwrap
import tempfile
import pathlib

# --- constants: tweak if you like ---
TITLE_WRAP = 60   # max characters per line for question titles
TICK_WRAP  = 20   # max characters per line for answer options

from mysurvey import (
    API_URL, USERNAME, PASSWORD,
    SURVEY_ID, LASTPAGE_THRESHOLD,
    PARAMETERS,
)

try:
    from limesurveyrc2api.limesurvey import LimeSurvey
except:
    try:
        from limesurveyrc2api.limesurveyrc2api.limesurvey import LimeSurvey
    except:
        from limesurveyrc2api.limesurveyrc2api import LimeSurveyRemoteControl2API as LimeSurvey

# Path to cache file
CACHE_DIR = pathlib.Path(tempfile.gettempdir())
CACHE_FILE = CACHE_DIR / 'survey_cache.pkl'
DATA_TIMESTAMP = None

def _wrap(text: str, width: int) -> str:
    """Return text with <br>-separated line breaks, without splitting words."""
    return '<br>'.join(textwrap.wrap(str(text),
                                     width=width,
                                     break_long_words=False,
                                     replace_whitespace=False))

# Generic fetcher: returns DataFrame for any survey per config
def fetch_responses():
    client = LimeSurvey(url=API_URL, username=USERNAME)
    client.open(password=PASSWORD)
    payload = {
        "method": "export_responses",
        "params": [
            client.session_key,
            SURVEY_ID,
            "json",
            None,
            "all",
            "code",
            "long"
        ],
        "id": 1
    }
    resp = requests.post(API_URL, json=payload, headers={"content-type": "application/json"})
    resp.raise_for_status()
    raw_b64 = resp.json().get("result")

    # 4. Decode Base64 and parse JSON into Python list of dicts
    decoded = base64.b64decode(raw_b64)
    data = json.loads(decoded)

    client.close()
    df = pd.DataFrame(data['responses'])

    assert len(df) > 0,"Loaded dataframe is empty!"

    df['is_completed'] = df['lastpage'] >= LASTPAGE_THRESHOLD

    print('Data retrieved online succesfully!')

    return df

# Safely update cache with atomic replace via tempfile
def update_cache():
    df = fetch_responses()
    with tempfile.NamedTemporaryFile(dir=CACHE_DIR, delete=False, suffix='.pkl') as tmp:
        df.to_pickle(tmp.name)
    os.replace(tmp.name, CACHE_FILE)

# Load cached DataFrame (initializes cache if missing)
def load_cached_data():
    global DATA_TIMESTAMP
    if not os.path.exists(CACHE_FILE):
        update_cache()
    mod_ts = os.path.getmtime(CACHE_FILE)
    mod_dt = datetime.fromtimestamp(mod_ts, ZoneInfo('Europe/Helsinki'))
    DATA_TIMESTAMP = (f"{mod_dt.day}.{mod_dt.month}.{mod_dt.year} at "
                f"{mod_dt.hour:02d}:{mod_dt.minute:02d}:{mod_dt.second:02d} (Finnish time)")
    return pd.read_pickle(CACHE_FILE)

# Background polling thread: update cache every 15 minutes
def poll_cache():
    while True:
        time.sleep(15 * 60)
        try:
            update_cache()
        except Exception as e:
            print(f"[poll_cache] failed: {e}")

# Build graphs from DataFrame using PARAMETERS mapping
# --- replace your current build_graphs() with this version ---
def build_graphs(df):
    rows, current = [], []
    for code, label in PARAMETERS.items():
        if code == "token" or code not in df.columns:
            continue

        counts = (
            df[code]
            .value_counts()
            .sort_index()
            .reset_index(name="Count")  # <-- assigns the second column’s name
            .rename(columns={"index": code})  # <-- changes only the first column
        )

        # wrap long question text and answer options
        wrapped_title = _wrap(label, TITLE_WRAP)
        counts[code]  = counts[code].apply(lambda s: _wrap(s, TICK_WRAP))

        fig = px.bar(
            counts,
            x=code,
            y="Count",
            labels={code: '', "Count": "Count"},
            title=wrapped_title
        )

        # NEW: rotate tick labels −30° to avoid overlap
        fig.update_xaxes(tickangle=10)

        card = dbc.Card(dbc.CardBody(dcc.Graph(figure=fig)),
                        className="mb-4 shadow-sm")
        current.append(dbc.Col(card, md=6))

        if len(current) == 2:
            rows.append(dbc.Row(current, className="mb-4"))
            current = []

    if current:
        rows.append(dbc.Row(current, className="mb-4"))
    return rows

# Main app
def main():
    # Initial cache and polling
    update_cache()
    threading.Thread(target=poll_cache, daemon=True).start()

    app = dash.Dash(__name__, external_stylesheets=[dbc.themes.FLATLY])
    app.title = "LimeSurvey dashboard"

    # Layout: header, timestamp & refresh button row, graphs container, hidden Interval & Store
    app.layout = dbc.Container([
        html.H1("Haaga-Helia LimeSurvey Dashboard", className='text-center my-4'),
        dbc.Row([
            dbc.Col(html.P(id='intro-text', className='mb-3 text-muted'), width=10),
            dbc.Col(dbc.Button("Force refresh", id='refresh-button', color='primary'),
                    width=2, className='d-flex justify-content-end align-items-center')
        ], className='mb-2'),
        html.Hr(),
        html.Div(id='graphs-container'),
        dcc.Interval(id='interval-component', interval=15*60*1000, n_intervals=0),
        dcc.Store(id='last-refresh-store', data=(datetime.now(ZoneInfo('Europe/Helsinki')) - timedelta(hours=1)).isoformat())
    ], fluid=True)

    @app.callback(
        [Output('intro-text', 'children'), Output('graphs-container', 'children'), Output('last-refresh-store', 'data')],
        [Input('interval-component', 'n_intervals'), Input('refresh-button', 'n_clicks')],
        [State('last-refresh-store', 'data')]
    )
    def update_dashboard(n_intervals, n_clicks, last_refresh):
        now = datetime.now(ZoneInfo('Europe/Helsinki'))
        last = datetime.fromisoformat(last_refresh)
        triggered = dash.callback_context.triggered[0]['prop_id']
        if 'refresh-button' in triggered:
            if (now - last).total_seconds() >= 60:
                update_cache()
                last = now
        # Load from cache and rebuild
        df = load_cached_data()
        total = len(df)
        n_tokens = len([x for x in list(df['token'].unique()) if x is not None])
        completed = df['is_completed'].sum()
        partial = total - completed
        intro = (f"This dashboard shows live results for selected survey variables. Currently {n_tokens} unique tokens with total {partial} PARTIAL and {completed} FULL responses. Data updated {DATA_TIMESTAMP}.")
        graphs = build_graphs(df)
        return intro, graphs, last.isoformat()

    return app

app = main()
server = app.server

if __name__ == '__main__':
    app.run(debug=False, port=8080,dev_tools_hot_reload=False,use_reloader=False,host="0.0.0.0")
