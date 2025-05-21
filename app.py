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
import pathlib

# --- constants: tweak if you like ---
TITLE_WRAP = 60   # max characters per line for question titles
TICK_WRAP  = 20   # max characters per line for answer options
CUTOFF_TIME = datetime(day=20, month=5, hour=18, year=2025, tzinfo=ZoneInfo("Europe/Helsinki"))

from mysurvey import (
    API_URL, USERNAME, PASSWORD,
    SURVEY_ID, LASTPAGE_THRESHOLD,
    PARAMETERS,
)

try:
    from limesurveyrc2api.limesurvey import LimeSurvey
except Exception:
    try:
        from limesurveyrc2api.limesurveyrc2api.limesurvey import LimeSurvey
    except Exception:
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

# ---------------------------- DATA LAYER ----------------------------

def fetch_responses() -> pd.DataFrame:
    """Fetch raw survey responses from LimeSurvey API *without* time‑based filtering."""
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

    # allow empty dataframes – downstream functions will handle gracefully
    if df.empty:
        print('[fetch_responses] received empty dataframe')
        return df

    df['is_completed'] = df['lastpage'] >= LASTPAGE_THRESHOLD
    df['startdate'] = pd.to_datetime(df['startdate'], format="%Y-%m-%d %H:%M:%S")
    df['startdate'] = df['startdate'].dt.tz_localize(ZoneInfo("Europe/Helsinki"))

    print('Data retrieved online successfully!')
    return df

def filter_by_cutoff(df: pd.DataFrame, cutoff_time: datetime) -> pd.DataFrame:
    """Return a copy of *df* containing only rows with startdate > cutoff_time."""
    if df.empty or 'startdate' not in df.columns:
        return df
    return df.loc[df['startdate'] > cutoff_time].copy()

# Safely update cache with atomic replace via tempfile

def update_cache():
    df = fetch_responses()
    with tempfile.NamedTemporaryFile(dir=CACHE_DIR, delete=False, suffix='.pkl') as tmp:
        df.to_pickle(tmp.name)
    os.replace(tmp.name, CACHE_FILE)

# Load cached DataFrame (initializes cache if missing)

def load_cached_data() -> pd.DataFrame:
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

# ---------------------------- VISUALISATION ----------------------------

def build_graphs(df: pd.DataFrame):
    # Handle empty dataframe early
    if df.empty:
        return [html.P("Empty dataframe", className="text-center text-muted")]

    rows, current = [], []
    for code, label in PARAMETERS.items():
        if code in ("token", 'startdate') or code not in df.columns:
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
        counts[code] = counts[code].apply(lambda s: _wrap(s, TICK_WRAP))

        fig = px.bar(
            counts,
            x=code,
            y="Count",
            labels={code: '', "Count": "Count"},
            title=wrapped_title
        )

        card = dbc.Card(dbc.CardBody(dcc.Graph(figure=fig)),
                        className="mb-4 shadow-sm")
        current.append(dbc.Col(card, md=6))

        if len(current) == 2:
            rows.append(dbc.Row(current, className="mb-4"))
            current = []

    if current:
        rows.append(dbc.Row(current, className="mb-4"))
    return rows

# ---------------------------- MAIN APP ----------------------------

def main():
    # Initial cache and polling
    update_cache()
    threading.Thread(target=poll_cache, daemon=True).start()

    app = dash.Dash(__name__, external_stylesheets=[dbc.themes.FLATLY])
    app.title = "LimeSurvey dashboard"

    # Layout: header, intro row, control row, graphs container, hidden Interval & Store
    app.layout = dbc.Container([
        html.H1("Haaga-Helia LimeSurvey Dashboard", className='text-center my-4'),

        # --- Row 1: intro text only ---
        dbc.Row(
            html.P(id='intro-text', className='mb-3 text-muted'),
            className='mb-2'
        ),

        # --- Row 2: force refresh & cut‑off controls side‑by‑side ---
        dbc.Row([
            dbc.Col(
                dbc.Button("Update database", id='refresh-button', color='primary', className='w-100'),
                xs=12, md='auto', className='mb-2'
            ),
            dbc.Col(
                html.Div([
                    html.Span("Show data after:", className="me-2 fw-bold"),
                    dcc.DatePickerSingle(id='cutoff-date-picker', date=CUTOFF_TIME.date(),display_format="DD.MM.YYYY",className='me-2'),
                    dcc.Input(id='cutoff-time-input', type='text', value=CUTOFF_TIME.strftime("%H:%M"),debounce=True, style={'width':'90px'}),
                    # NEW: completed-only checkbox
                    dbc.Checklist(
                        id="completed-only-checkbox",
                        options=[{"label": "Completed only", "value": 1}],
                        value=[],
                        inline=True,
                        className="ms-2 mb-0"
                    )
                ], className='d-flex align-items-center flex-wrap'),
                xs=12, md='auto', className='mb-2'
            )
        ], className='mb-2 gy-2 align-items-center'),

        html.Hr(),
        html.Div(id='graphs-container'),
        dcc.Interval(id='interval-component', interval=15 * 60 * 1000, n_intervals=0),
        dcc.Store(id='last-refresh-store',
                  data=(datetime.now(ZoneInfo('Europe/Helsinki')) - timedelta(hours=1)).isoformat())
    ], fluid=True)

    # ---------------- CALLBACKS ----------------

    @app.callback(
        [Output('intro-text', 'children'),
         Output('graphs-container', 'children'),
         Output('last-refresh-store', 'data')],
        [Input('interval-component', 'n_intervals'),
         Input('refresh-button', 'n_clicks'),
         Input('cutoff-date-picker', 'date'),
         Input('cutoff-time-input', 'value'),
         Input("completed-only-checkbox", 'value')
         ],
        [State('last-refresh-store', 'data')]
    )
    def update_dashboard(n_intervals, n_clicks, cutoff_date, cutoff_time,completed_only,last_refresh):
        """Update intro text, graphs, and refresh store.

        Accepts cutoff selectors; updates global CUTOFF_TIME; handles empty dataframes gracefully."""
        global CUTOFF_TIME

        # --- parse cutoff selector ---
        try:
            if cutoff_date is not None:
                date_part = datetime.fromisoformat(cutoff_date).date()
            else:
                date_part = CUTOFF_TIME.date()
        except Exception:
            date_part = CUTOFF_TIME.date()

        try:
            hours, minutes = map(int, (cutoff_time or "").split(':'))
        except Exception:
            hours, minutes = CUTOFF_TIME.hour, CUTOFF_TIME.minute

        CUTOFF_TIME = datetime(year=date_part.year, month=date_part.month, day=date_part.day,
                               hour=hours, minute=minutes, tzinfo=ZoneInfo('Europe/Helsinki'))

        # --------------------------------------------------------
        now = datetime.now(ZoneInfo('Europe/Helsinki'))
        last = datetime.fromisoformat(last_refresh)
        triggered = dash.callback_context.triggered[0]['prop_id'] if dash.callback_context.triggered else ''
        if 'refresh-button' in triggered:
            if (now - last).total_seconds() >= 60:
                update_cache()
                last = now
        # Load from cache and *then* apply cut‑off filter
        df_all = load_cached_data()
        df = filter_by_cutoff(df_all, CUTOFF_TIME)
        if len(completed_only)>0 and completed_only[0]:
            df = df.loc[df['is_completed']]

        # Gracefully handle empty dataframe
        if df.empty or 'token' not in df.columns:
            intro = ("Empty dataframe – no responses satisfy the current criteria.")
            graphs = [html.P("Empty dataframe", className="text-center text-muted")]
            return intro, graphs, last.isoformat()

        # Compute metrics on filtered data
        total = len(df)
        n_tokens = len([x for x in list(df['token'].unique()) if x is not None])
        completed = df['is_completed'].sum()
        partial = total - completed
        intro = (f"This dashboard shows live results for selected survey variables. "
                 f"Currently {n_tokens} unique tokens with total {partial} PARTIAL and {completed} FULL responses. "
                 f"Data updated {DATA_TIMESTAMP}. Showing responses after {CUTOFF_TIME.strftime('%d.%m.%Y %H:%M') }.")
        graphs = build_graphs(df)
        return intro, graphs, last.isoformat()

    return app

app = main()
server = app.server

if __name__ == '__main__':
    #app.run(debug=False, port=8080, dev_tools_hot_reload=False, use_reloader=False)
    app.run(debug=False, port=8080, dev_tools_hot_reload=False, use_reloader=False, host="0.0.0.0")
