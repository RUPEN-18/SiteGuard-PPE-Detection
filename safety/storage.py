"""Durable session snapshots and violation history, using parameterized SQLite."""
import csv
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root/'safety.db', timeout=15)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY, session TEXT, worker INTEGER, recorded_at TEXT,
          day TEXT, camera TEXT, media_seconds REAL, helmet TEXT, vest TEXT,
          violation TEXT, confidence REAL, evidence TEXT);
        CREATE TABLE IF NOT EXISTS snapshots (
          session TEXT, day TEXT, camera TEXT, updated_at TEXT, metrics TEXT,
          PRIMARY KEY(session, day));
        CREATE INDEX IF NOT EXISTS events_day ON events(day, camera);
        ''')

    def add(self, session, worker, camera, media_seconds, evidence):
        now = datetime.now().astimezone()
        violations = []
        if worker.helmet=='Missing': violations.append('Helmet missing')
        if worker.vest=='Missing': violations.append('Jacket missing')
        with self.db:
            self.db.execute('INSERT INTO events VALUES(NULL,?,?,?,?,?,?,?,?,?,?,?)',
                (session, worker.track_id, now.isoformat(timespec='seconds'), now.date().isoformat(),
                 camera, media_seconds, worker.helmet, worker.vest, ' + '.join(violations),
                 worker.confidence, str(evidence)))

    def snapshot(self, session, camera, metrics):
        now = datetime.now().astimezone()
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO snapshots VALUES(?,?,?,?,?)',
                            (session, now.date().isoformat(), camera, now.isoformat(), json.dumps(metrics)))

    def events(self, day='', camera=''):
        self.db.row_factory = sqlite3.Row
        rows = self.db.execute('SELECT * FROM events WHERE (?="" OR day=?) AND (?="" OR camera=?) ORDER BY id DESC',
                               (day,day,camera,camera)).fetchall()
        return [dict(r) for r in rows]

    def daily(self, day):
        rows = self.db.execute('SELECT metrics FROM snapshots WHERE day=?',(day,)).fetchall()
        metrics = [json.loads(r[0]) for r in rows]
        total = sum(m['session']['total'] for m in metrics)
        safe = sum(m['session']['safe'] for m in metrics)
        events = self.events(day)
        return dict(day=day, sessions=len(rows), track_ids=total, safe_latest=safe,
                    compliance=round(100*safe/total,1) if total else 0,
                    events=len(events), helmet_events=sum(r['helmet']=='Missing' for r in events),
                    jacket_events=sum(r['vest']=='Missing' for r in events),
                    multiple_events=sum(r['helmet']==r['vest']=='Missing' for r in events))

    def close(self): self.db.close()


def export_csv(path, rows):
    fields = ['id','session','worker','recorded_at','day','camera','media_seconds','helmet','vest','violation','confidence','evidence']
    def safe(value):
        # Prevent spreadsheet formula execution when opening exported camera labels.
        return "'"+value if isinstance(value,str) and value.startswith(('=','+','-','@','\t','\r')) else value
    with open(path,'w',newline='',encoding='utf-8-sig') as handle:
        writer = csv.DictWriter(handle,fieldnames=fields)
        writer.writeheader()
        writer.writerows({k:safe(r.get(k,'')) for k in fields} for r in rows)


def export_pdf(path, rows, summary):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    styles = getSampleStyleSheet()
    p = lambda text: Paragraph(escape(str(text)), styles['BodyText'])
    story = [Paragraph('SiteGuard | Daily Safety Report',styles['Title']),
             p(f"Analysis date: {summary['day']} | Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}"), Spacer(1,12)]
    for key,value in summary.items():
        story.append(p(f'{key.replace("_"," ").title()}: {value}'))
    story += [Spacer(1,12),p('Counts are session-scoped track IDs, not verified individual identities. '
              'Compliance uses each track’s latest observed state. Unknown PPE is not compliant. '
              'Dates refer to analysis time; media position identifies the source video frame. '
              'This report contains automated observations for human review.'),Spacer(1,15)]
    data = [[p(x) for x in ['Time / session','Worker / camera','Helmet','Jacket','Violation','Confidence / media']]]
    for r in rows:
        data.append([p(r['recorded_at']+' / '+r['session'][:8]),p(f"{r['worker']:03d} / {r['camera']}"),
                     p(r['helmet']),p(r['vest']),p(r['violation']),p(f"{r['confidence']:.2f} / {r['media_seconds']:.2f}s")])
    if len(data)==1: story.append(p('No violation events for this day.'))
    else:
        table = Table(data,colWidths=[155,115,70,70,160,130],repeatRows=1)
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e2e8f0')),
                                  ('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.3,colors.lightgrey),
                                  ('BOTTOMPADDING',(0,0),(-1,-1),8)]))
        story.append(table)
    SimpleDocTemplate(str(path),pagesize=landscape(A4),leftMargin=20,rightMargin=20).build(story)
