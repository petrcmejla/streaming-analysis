import os
import json
import pandas as pd
import numpy as np
from datetime import datetime

# ==========================================
#                 NASTAVENÍ
# ==========================================

DATA_FOLDER = "./data"
OUTPUT_HTML = "output.html"

GUILTY_SKIP_MS = 10000
VALID_PLAY_MS = 30000
GEM_HISTORIC_MINS = 15
GEM_RECENT_MINS = 5

def load_data(folder_path):
    print("Načítaní dat")
    all_data = []
    if not os.path.exists(folder_path):
        print(f"Error: Folder '{folder_path}' does not exist")
        return None

    for file in os.listdir(folder_path):
        if file.endswith(".json"):
            try:
                with open(os.path.join(folder_path, file), 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        all_data.extend(data)
            except Exception as e:
                print(f"Chyba u souboru {file}: {e}")
                
    if not all_data:
        return None

    df = pd.DataFrame(all_data)
    df['ts'] = pd.to_datetime(df['ts'])
    
    try:
        df['ts'] = df['ts'].dt.tz_convert('Europe/Prague')
    except Exception:
        pass

    df['rok'] = df['ts'].dt.year
    df['minuty'] = df['ms_played'] / 60000.0
    
    if 'episode_name' in df.columns:
        df = df[df['episode_name'].isnull()]
    df = df.dropna(subset=['master_metadata_track_name', 'master_metadata_album_artist_name'])
    
    return df

def analyze_anomalies(df):
    print("Analýza dat")
    tracks = df['master_metadata_track_name'].values
    streaks = {}
    current_streak = 1
    
    for i in range(1, len(tracks)):
        if tracks[i] == tracks[i-1]:
            current_streak += 1
        else:
            prev_track = tracks[i-1]
            if current_streak > 3:
                if prev_track not in streaks or current_streak > streaks[prev_track]:
                    streaks[prev_track] = current_streak
            current_streak = 1
            
    top_binge = sorted(streaks.items(), key=lambda x: x[1], reverse=True)[:5]

    skips_df = df[df['ms_played'] < GUILTY_SKIP_MS]
    top_skips = skips_df['master_metadata_track_name'].value_counts().head(5).reset_index()
    top_skips.columns = ['track', 'skips']

    max_rok = df['rok'].max()
    pivot_roky = df.pivot_table(
        index=['master_metadata_track_name', 'master_metadata_album_artist_name'], 
        columns='rok', values='minuty', aggfunc='sum'
    ).fillna(0)
    
    klenoty = []
    for idx, row in pivot_roky.iterrows():
        track, artist = idx
        nedavno = row.get(max_rok, 0) + row.get(max_rok - 1, 0)
        stare_roky = [r for r in row.index if r < max_rok - 1]
        if not stare_roky: continue
        
        nej_rok = max(stare_roky, key=lambda r: row[r])
        peak = row[nej_rok]
        
        if peak >= GEM_HISTORIC_MINS and nedavno <= GEM_RECENT_MINS:
            klenoty.append({
                'track': track, 'artist': artist, 
                'peak_year': nej_rok, 'peak_mins': int(peak)
            })
    klenoty = sorted(klenoty, key=lambda x: x['peak_mins'], reverse=True)[:20]

    df['hour'] = df['ts'].dt.hour
    night_df = df[df['hour'].isin([0, 1, 2, 3, 4])]
    night_hours = int(night_df['minuty'].sum() / 60)
    if not night_df.empty:
        night_top = night_df.groupby(['master_metadata_track_name', 'master_metadata_album_artist_name'])['minuty'].sum().idxmax()
    else:
        night_top = ("N/A", "N/A")

    track_stats = df.groupby(['master_metadata_track_name', 'master_metadata_album_artist_name']).agg(
        total_clicks=('ms_played', 'count'),
        valid_plays=('ms_played', lambda x: (x > VALID_PLAY_MS).sum()),
        total_mins=('minuty', 'sum')
    ).reset_index()
    
    srdcovky = track_stats[track_stats['valid_plays'] > 20].copy()
    srdcovky['completion_rate'] = (srdcovky['valid_plays'] / srdcovky['total_clicks'] * 100).round(1)
    srdcovky = srdcovky.sort_values(by='completion_rate', ascending=False).head(20)

    top10_overall = track_stats.sort_values(by='total_mins', ascending=False).head(10)['master_metadata_track_name'].tolist()
    lifecycle = []
    for track in top10_overall:
        t_df = df[df['master_metadata_track_name'] == track]
        first = t_df['ts'].min().strftime('%d.%m.%Y')
        last = t_df['ts'].max().strftime('%d.%m.%Y')
        top_y = t_df.groupby('rok')['minuty'].sum().idxmax()
        total_m = int(t_df['minuty'].sum())
        lifecycle.append({'track': track, 'first': first, 'last': last, 'top_year': top_y, 'mins': total_m})

    return {
        'binge': top_binge,
        'skips': top_skips.to_dict('records'),
        'gems': klenoty,
        'night_hours': night_hours,
        'night_track': night_top,
        'true_favorites': srdcovky.to_dict('records'),
        'lifecycle': lifecycle
    }

def calculate_metrics(df):
    print("Počítání ukazatelů")
    valid = df[df['ms_played'] > VALID_PLAY_MS]
    
    yoy = df.groupby('rok')['minuty'].sum().round(0).to_dict()
    hourly = df.groupby(df['ts'].dt.hour)['minuty'].sum().reindex(range(24), fill_value=0).tolist()
    daily = df.groupby(df['ts'].dt.dayofweek)['minuty'].sum().reindex(range(7), fill_value=0).tolist()
    
    top_tracks = valid.groupby(['master_metadata_track_name', 'master_metadata_album_artist_name'])['minuty'].sum().reset_index().sort_values(by='minuty', ascending=False).head(100).to_dict('records')
    top_artists = valid.groupby('master_metadata_album_artist_name')['minuty'].sum().reset_index().sort_values(by='minuty', ascending=False).head(100).to_dict('records')

    return {
        'total_hours': int(df['minuty'].sum() / 60),
        'unique_tracks': df['master_metadata_track_name'].nunique(),
        'unique_artists': df['master_metadata_album_artist_name'].nunique(),
        'valid_plays': len(valid),
        'yoy_labels': list(yoy.keys()),
        'yoy_data': list(yoy.values()),
        'hourly': hourly,
        'daily': daily,
        'top_tracks': top_tracks,
        'top_artists': top_artists
    }

def generate_html(metrics, anomalies, output_path):
    print("Generování výsledku")
    def make_rows(data_list, cols_template):
        return "".join([cols_template.format(**{**item, 'idx': i+1}) for i, item in enumerate(data_list)])

    html_binge = "".join([f"<tr><td><strong>{t.replace('<','')}</strong></td><td class='accent-text'>{c}x v kuse</td></tr>" for t, c in anomalies['binge']])
    html_skips = "".join([f"<tr><td><strong>{r['track'].replace('<','')}</strong></td><td class='text-red'>{r['skips']}x</td></tr>" for r in anomalies['skips']])
    
    html_gems = "".join([f"<tr><td><strong>{g['track']}</strong><br><span class='text-muted'>{g['artist']}</span></td><td>{g['peak_year']}</td><td class='accent-text'>{g['peak_mins']} min</td></tr>" for g in anomalies['gems']])
    
    html_true_favs = "".join([f"<tr><td><strong>{f['master_metadata_track_name']}</strong></td><td>{f['valid_plays']} / {f['total_clicks']}</td><td><div class='progress-bar'><div class='progress-fill' style='width: {f['completion_rate']}%;'></div></div><span class='accent-text ml-2'>{f['completion_rate']}%</span></td></tr>" for f in anomalies['true_favorites']])
    
    html_lifecycle = "".join([f"<tr><td><strong>{l['track']}</strong></td><td class='accent-text'>{l['top_year']}</td><td>{l['first']}</td><td>{l['last']}</td></tr>" for l in anomalies['lifecycle']])

    html_top_tracks = "".join([f"<tr><td>{i+1}</td><td><strong>{t['master_metadata_track_name']}</strong><br><span class='text-muted'>{t['master_metadata_album_artist_name']}</span></td><td>{int(t['minuty'])} min</td></tr>" for i, t in enumerate(metrics['top_tracks'])])
    
    html_top_artists = "".join([f"<tr><td>{i+1}</td><td><strong>{a['master_metadata_album_artist_name']}</strong></td><td>{int(a['minuty'])} min</td></tr>" for i, a in enumerate(metrics['top_artists'])])

    template = f"""<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Analýza dat ze Spotify</title>
    <style>
        :root {{
            --bg-primary: #000000;
            --bg-secondary: #0A0A0A;
            --bg-card: #121212;
            --text-primary: #FFFFFF;
            --text-secondary: #A6A6A6;
            --accent: #276EF1; /* Tech Blue */
            --danger: #E11900;
            --border: #222222;
            --font-family: 'Helvetica Neue', Inter, system-ui, sans-serif;
        }}

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            background-color: var(--bg-primary);
            color: var(--text-primary);
            font-family: var(--font-family);
            padding: 40px 20px;
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
        }}

        .container {{ max-width: 1200px; margin: 0 auto; }}

        .header {{
            margin-bottom: 40px;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--border);
        }}
        .header h1 {{ font-size: 3rem; font-weight: 700; letter-spacing: -1px; }}
        .header p {{ color: var(--text-secondary); font-size: 1.1rem; margin-top: 10px; }}

        .grid-4 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 24px; margin-bottom: 40px; }}
        .grid-2 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(450px, 1fr)); gap: 24px; margin-bottom: 40px; }}
        .grid-3 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 24px; margin-bottom: 40px; }}

        .card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            padding: 30px;
            transition: border-color 0.3s ease;
        }}
        .card:hover {{ border-color: #444; }}
        
        .kpi-title {{ font-size: 0.8rem; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 10px; }}
        .kpi-val {{ font-size: 3rem; font-weight: 700; letter-spacing: -1px; }}
        
        .card h3 {{ font-size: 1.25rem; font-weight: 600; margin-bottom: 20px; border-bottom: 1px solid var(--border); padding-bottom: 10px; }}

        table {{ width: 100%; border-collapse: collapse; font-size: 0.95rem; }}
        th, td {{ padding: 14px 10px; text-align: left; border-bottom: 1px solid var(--border); }}
        th {{ color: var(--text-secondary); font-weight: 500; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1px; }}
        tr:last-child td {{ border-bottom: none; }}
        tr:hover {{ background-color: var(--bg-secondary); }}

        .accent-text {{ color: var(--accent); font-weight: 600; }}
        .text-red {{ color: var(--danger); font-weight: 600; }}
        .text-muted {{ color: var(--text-secondary); font-size: 0.85rem; display: block; margin-top: 4px; }}
        
        .chart-wrapper {{ height: 280px; width: 100%; position: relative; }}
        
        .progress-bar {{ width: 100px; height: 6px; background: var(--border); display: inline-block; vertical-align: middle; }}
        .progress-fill {{ height: 100%; background: var(--accent); }}
        
        .card-anomaly {{ border-top: 4px solid var(--accent); }}
        .card-danger {{ border-top: 4px solid var(--danger); }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <p>Analýza poslechových dat ze Spotify za celou dobu existence účtu</p>
        </div>

        <div class="grid-4">
            <div class="card">
                <div class="kpi-title">Počet hodin</div>
                <div class="kpi-val accent-text">{metrics['total_hours']:,}</div>
            </div>
            <div class="card">
                <div class="kpi-title">Počet skladeb</div>
                <div class="kpi-val">{metrics['unique_tracks']:,}</div>
            </div>
            <div class="card">
                <div class="kpi-title">Počet umělců</div>
                <div class="kpi-val">{metrics['unique_artists']:,}</div>
            </div>
            <div class="card">
                <div class="kpi-title">Počet přehrátí (>30s)</div>
                <div class="kpi-val" style="color: var(--text-secondary);">{metrics['valid_plays']:,}</div>
            </div>
        </div>

        <div class="grid-2">
            <div class="card">
                <h3>Počet poslechů za jednotlivé roky</h3>
                <div class="chart-wrapper"><canvas id="yoyChart"></canvas></div>
            </div>
            <div class="card">
                <h3>Denní rytmus</h3>
                <div class="chart-wrapper"><canvas id="hourChart"></canvas></div>
            </div>
        </div>

        <div class="grid-3">
            <div class="card card-anomaly">
                <h3>Nejposlouchanější skladba v noci</h3>
                <p style="color: var(--text-secondary); font-size: 0.95rem; margin-bottom: 15px;">
                    Počet odposlouchaných hodin mezi 00:00 - 05:00.
                </p>
                <div class="kpi-val">{anomalies['night_hours']} <span style="font-size: 1rem; font-weight: normal; color: var(--text-secondary);">hod.</span></div>
                <p style="margin-top: 20px; font-size: 0.9rem;">Vaše noční hymna:<br>
                <strong class="accent-text">{anomalies['night_track'][0]}</strong><br>
                <span class="text-muted">{anomalies['night_track'][1]}</span></p>
            </div>

            <div class="card card-danger">
                <h3>Rychle přeskočení</h3>
                <p style="color: var(--text-secondary); font-size: 0.85rem; margin-bottom: 10px;">Skladby přeskočeny během prvních 10s</p>
                <table>
                    {html_skips}
                </table>
            </div>

            <div class="card card-anomaly">
                <h3>Streak poslechů</h3>
                <p style="color: var(--text-secondary); font-size: 0.85rem; margin-bottom: 10px;">Skladby přehrané nejvíc dnů po sobě</p>
                <table>
                    {html_binge}
                </table>
            </div>
        </div>

        <div class="grid-2">
            <div class="card">
                <h3>Nejoblíbenější skladby</h3>
                <p style="color: var(--text-secondary); font-size: 0.85rem; margin-bottom: 10px;">Největší poměr mezi doposlouchání skladby po jejím přehrání</p>
                <table>
                    <thead><tr><th>Skladba</th><th>Dokončení / Přehrání</th><th>Doposlouchání v %</th></tr></thead>
                    <tbody>{html_true_favs}</tbody>
                </table>
            </div>
            
            <div class="card">
                <h3>Zapomenuté oblíbené skladby</h3>
                <p style="color: var(--text-secondary); font-size: 0.85rem; margin-bottom: 10px;">Oblíbené skladby, na které jste zapomněli</p>
                <table>
                    <thead><tr><th>Skladba / Umělec</th><th>Rok poslechu</th><th>Naposloucháno minut</th></tr></thead>
                    <tbody>{html_gems}</tbody>
                </table>
            </div>
        </div>

        <div class="card" style="margin-bottom: 40px;">
            <h3>Životní cyklus skladeb (Top 10)</h3>
            <table>
                <thead><tr><th>Skladba</th><th>Vrcholný rok skladby</th><th>První přehrání</th><th>Naposled přehráno</th></tr></thead>
                <tbody>{html_lifecycle}</tbody>
            </table>
        </div>

        <div class="grid-2">
            <div class="card">
                <h3>Top 100 skladeb za celou dobu</h3>
                <table>
                    <thead><tr><th>#</th><th>Skladba</th><th>Strávený čas</th></tr></thead>
                    <tbody>{html_top_tracks}</tbody>
                </table>
            </div>
            <div class="card">
                <h3>Top 100 Umělců</h3>
                <table>
                    <thead><tr><th>#</th><th>Umělec</th><th>Strávený čas</th></tr></thead>
                    <tbody>{html_top_artists}</tbody>
                </table>
            </div>
        </div>
    </div>

    <script src="chart.umd.min.js"></script>
    <script>
        const chartOptions = {{
            responsive: true, maintainAspectRatio: false,
            plugins: {{ legend: {{ display: false }} }},
            scales: {{
                x: {{ grid: {{ color: '#222', drawBorder: false }}, ticks: {{ color: '#A6A6A6', font: {{ family: 'Arial' }} }} }},
                y: {{ grid: {{ color: '#222', drawBorder: false }}, ticks: {{ color: '#A6A6A6', font: {{ family: 'Arial' }} }} }}
            }}
        }};

        new Chart(document.getElementById('yoyChart'), {{
            type: 'line',
            data: {{
                labels: {metrics['yoy_labels']},
                datasets: [{{ 
                    data: {metrics['yoy_data']}, 
                    borderColor: '#276EF1', 
                    borderWidth: 3,
                    backgroundColor: 'rgba(39, 110, 241, 0.1)', 
                    fill: true, tension: 0.4, pointRadius: 4, pointBackgroundColor: '#fff' 
                }}]
            }},
            options: chartOptions
        }});

        new Chart(document.getElementById('hourChart'), {{
            type: 'bar',
            data: {{
                labels: Array.from({{length: 24}}, (_, i) => i + ':00'),
                datasets: [{{ 
                    data: {metrics['hourly']}, 
                    backgroundColor: '#A6A6A6', 
                    hoverBackgroundColor: '#FFFFFF',
                    borderRadius: 2 
                }}]
            }},
            options: chartOptions
        }});
    </script>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(template)
    print(f"Hotovo! Výsledek naleznete zde: {os.path.abspath(output_path)}")

if __name__ == "__main__":
    df = load_data(DATA_FOLDER)
    if df is not None:
        anomalies = analyze_anomalies(df)
        metrics = calculate_metrics(df)
        generate_html(metrics, anomalies, OUTPUT_HTML)