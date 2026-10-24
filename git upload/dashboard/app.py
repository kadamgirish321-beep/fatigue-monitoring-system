from flask import Flask, render_template_string
import mysql.connector
from datetime import datetime

app = Flask(__name__)

def get_data():
    db = mysql.connector.connect(
        host="localhost",
        user="root",
        password="root",
        database="fatigue_db"
    )
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM readings ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    cursor.close()
    db.close()
    return row

HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>User Fatigue Dashboard</title>
  <!-- Bootstrap 5 -->
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <!-- Bootstrap Icons -->
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css" rel="stylesheet">
  <!-- Auto refresh every second -->
  <meta http-equiv="refresh" content="1" />
  <style>
    :root{
      --bg:#0b1220;
      --card:#121a2b;
      --muted:#97a3b6;
      --ok:#22c55e;
      --warn:#f59e0b;
      --bad:#ef4444;
      --accent:#60a5fa;
    }
    body{
      background: radial-gradient(1200px 600px at 80% -10%, rgba(96,165,250,.18), transparent 60%),
                  radial-gradient(1000px 500px at -10% 10%, rgba(99,102,241,.15), transparent 60%),
                  var(--bg);
      color: #e5e7eb;
    }
    .navbar{
      background: linear-gradient(180deg, rgba(255,255,255,.06), rgba(255,255,255,.0));
      border-bottom: 1px solid rgba(255,255,255,.08);
      backdrop-filter: blur(6px);
    }
    .card{
      background: linear-gradient(180deg, rgba(255,255,255,.04), rgba(255,255,255,.02));
      border: 1px solid rgba(255,255,255,.08);
      color: #e5e7eb;
      box-shadow: 0 10px 30px rgba(0,0,0,.35);
    }
    .card:hover{
      border-color: rgba(96,165,250,.35);
    }
    .muted{ color: var(--muted); }
    .badge-status{
      font-weight: 600;
      letter-spacing:.3px;
      padding:.5rem .75rem;
      border:1px solid transparent;
    }
    .badge-ok{ background: rgba(34,197,94,.15); color:#86efac; border-color: rgba(34,197,94,.35);}
    .badge-warn{ background: rgba(245,158,11,.15); color:#fcd34d; border-color: rgba(245,158,11,.35);}
    .badge-bad{ background: rgba(239,68,68,.15); color:#fecaca; border-color: rgba(239,68,68,.35);}
    .metric{
      font-size: clamp(1.4rem, 2.5vw, 2rem);
      font-weight: 700;
    }
    .metric-label{
      font-size:.9rem;
      color: var(--muted);
    }
    .glow{
      text-shadow: 0 0 20px rgba(96,165,250,.35);
    }
    .footer-note{
      font-size:.85rem;
      color: var(--muted);
    }
    .chip{
      background: rgba(96,165,250,.12);
      border:1px solid rgba(96,165,250,.35);
      color:#cfe2ff;
      padding:.35rem .6rem;
      border-radius: 999px;
      font-size: .8rem;
    }
  </style>
</head>
<body>
<nav class="navbar sticky-top">
  <div class="container-fluid px-3 px-md-4">
    <span class="navbar-brand mb-0 h5 text-light">
      <i class="bi bi-activity me-2 text-primary"></i> User Fatigue Dashboard
    </span>
    <span class="chip"><i class="bi bi-clock-history me-1"></i> Live (1s)</span>
  </div>
</nav>

<div class="container py-4 py-md-5">

  {% set has = data is not none %}
  {% set status = (data.fatigue_status if has else '')|string %}
  {% set badge_class = 'badge-ok' if status|lower in ['normal','alert','ok','awake'] 
                   else ('badge-warn' if status|lower in ['drowsy','caution'] 
                   else ('badge-bad' if status else 'badge-warn')) %}

  <!-- Top Row: Status + Essentials -->
  <div class="row g-4 align-items-stretch">
    <div class="col-12 col-lg-4">
      <div class="card h-100">
        <div class="card-body d-flex flex-column justify-content-between">
          <div class="d-flex justify-content-between align-items-start mb-3">
            <div>
              <div class="muted mb-1">Current Status</div>
              <div class="h4 glow mb-0">
                {% if has %} {{ data.fatigue_status }} {% else %} — {% endif %}
              </div>
            </div>
            <span class="badge badge-status {{badge_class}}">
              {% if has %} {{ data.fatigue_status }} {% else %} Waiting for data {% endif %}
            </span>
          </div>
          <div class="mt-2">
            <div class="d-flex align-items-center gap-2 muted">
              <i class="bi bi-calendar-event"></i>
              <span>Last update:
                {% if has and data.get('created_at') %}
                  {{ data.created_at }}
                {% elif has and data.get('timestamp') %}
                  {{ data.timestamp }}
                {% else %}
                  just now
                {% endif %}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Stat cards -->
    <div class="col-12 col-lg-8">
      <div class="row g-4">
        <div class="col-12 col-sm-6 col-xl-3">
          <div class="card h-100">
            <div class="card-body">
              <div class="metric">{% if has %}{{ '%.3f'|format(data.ear|float) if data.ear is not none else '—' }}{% else %}—{% endif %}</div>
              <div class="metric-label">EAR (Eye Aspect Ratio)</div>
              <div class="mt-2 muted"><i class="bi bi-eye"></i> Lower EAR → eyes closing</div>
            </div>
          </div>
        </div>

        <div class="col-12 col-sm-6 col-xl-3">
          <div class="card h-100">
            <div class="card-body">
              <div class="metric">{% if has %}{{ '%.3f'|format(data.mar|float) if data.mar is not none else '—' }}{% else %}—{% endif %}</div>
              <div class="metric-label">MAR (Mouth Aspect Ratio)</div>
              <div class="mt-2 muted"><i class="bi bi-emoji-neutral"></i> Higher MAR → yawning</div>
            </div>
          </div>
        </div>

        <div class="col-12 col-sm-6 col-xl-3">
          <div class="card h-100">
            <div class="card-body">
              <div class="metric">{% if has %}{{ data.blink_count if data.blink_count is not none else '—' }}{% else %}—{% endif %}</div>
              <div class="metric-label">Blinks (session)</div>
              <div class="mt-2 muted"><i class="bi bi-lightning-charge"></i> Sudden spikes may indicate fatigue</div>
            </div>
          </div>
        </div>

        <div class="col-12 col-sm-6 col-xl-3">
          <div class="card h-100">
            <div class="card-body">
              <div class="metric">{% if has %}{{ '%.1f'|format(data.blink_rate|float) if data.blink_rate is not none else '—' }}{% else %}—{% endif %}</div>
              <div class="metric-label">Blinks / min</div>
              <div class="mt-2 muted"><i class="bi bi-activity"></i> Very high or low rate can be a sign</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Secondary row: Details -->
  <div class="row g-4 mt-1">
    <div class="col-12">
      <div class="card">
        <div class="card-body d-flex flex-wrap gap-3 align-items-center">
          <div class="muted"><i class="bi bi-info-circle me-1"></i> Details</div>
          <div class="vr"></div>
          <div>Reading ID:
            <span class="chip">{% if has and data.get('id') %}#{{data.id}}{% else %}—{% endif %}</span>
          </div>
          <div>Thresholds:
            <span class="chip">EAR↓ risky</span>
            <span class="chip">MAR↑ yawning</span>
            <span class="chip">Blink↑ drowsy</span>
          </div>
          {% if not has %}
            <div class="ms-auto muted">No data yet… waiting for first reading.</div>
          {% endif %}
        </div>
      </div>
    </div>
  </div>

  <div class="d-flex justify-content-between align-items-center mt-4">
    <div class="footer-note">
      <i class="bi bi-shield-check me-1"></i>
      Live preview only. For production, disable debug and serve via a WSGI server (gunicorn/uwsgi) behind Nginx.
    </div>
    <div class="footer-note">
      Server time: {{ now }}
    </div>
  </div>
</div>

</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(HTML, data=get_data(), now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
