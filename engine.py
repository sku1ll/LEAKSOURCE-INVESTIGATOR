"""LEAKSOURCE 3 — evidence analysis and durable provenance (Python 3.10+)."""
from __future__ import annotations
import csv, hashlib, html, json, os, re, shutil, sqlite3, time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / 'sorties'
OUTPUT.mkdir(exist_ok=True)
DB = OUTPUT / 'enquete.sqlite3'
TARGET = 'd0nut2x'

QUESTION = [
    r'how (?:did|do|can|are|were) (?:you|u|they|he|she|someone).*?(?:watch|see|get|access|view|obtain|episode|early|before)',
    r'(?:where|how|who).*?(?:leak|episode|screener|source|watch|download|early|access)',
    r'(?:how|where).*?(?:you|they).*?(?:get|know).*?(?:staff|credits|ost|episode)',
    r'(?:comment|où|d.où|comment est.ce que).*?(?:épisode|avance|avant|accès|source|regarde|obtien|fuite)',
    r'(?:どうやって|なぜ|どこで).*?(?:先行|視聴|見れ|見た|リーク|入手|情報)',
    r'(?:where|how).{0,60}(?:before release|early access|prior to release)',
]
ACCESS = [
    r'\b(?:screener|press copy|preview copy|early access|advance copy|pre.?release|internal copy|staff credits|production files)\b',
    r'\b(?:studio|animator|subcontractor|insider|source|contact|distribution|pre.?air|private group|discord|telegram|leak|leaker)\b',
    r'\b(?:copie privée|accès presse|avant.première|épisode en avance|contact du studio|source interne|fuite)\b',
    r'(?:先行視聴|先行公開|制作関係者|関係者|流出|リーク|スタッフ|情報源)',
]
NEGATION = re.compile(r"(?:i (?:don.?t|do not|never|didn.?t|cannot|can.?t) (?:have|get|watch|see|know)|not (?:seen|watched|got|received)|je n.ai pas|je ne (?:sais|peux|regarde)|no (?:access|copy|screener))", re.I)
DIRECT = re.compile(r'(?:i (?:have|had|got|received|watched|saw|was sent|was given)|my (?:source|contact)|they sent me|je (?:l.ai|reçois|connais)|見ました|見た|入手した)', re.I)
EARLY = re.compile(r'\b(?:episode|bleach|tybw|early|leak|before|screener|source|staff|preview|access|credits|pierrot|one piece|yonkou)\b|(?:épisode|avant|fuite|accès|animateur|制作|先行|リーク)', re.I)
LINK_PAT = re.compile(r'https?://[^\s<>"\']+')


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def canonical_url(url):
    url = (url or '').strip()
    try:
        p = urlsplit(url)
        if p.scheme not in ('http', 'https') or not p.hostname:
            return ''
        host = p.hostname.lower().removeprefix('www.')
        if host in ('twitter.com', 'mobile.twitter.com'): host = 'x.com'
        if host in ('old.reddit.com', 'new.reddit.com', 'redd.it'): host = 'reddit.com'
        if host == 'x.com':
            match = re.search(r'/status/(\d+)', p.path)
            if match:
                username = p.path.split('/')[1]
                return f'https://x.com/{username}/status/{match.group(1)}'
        if host == 'reddit.com':
            match = re.search(r'/comments/([\w]+)/', p.path + '/')
            if match:
                after = re.search(r'/comments/[\w]+/[^/]*/([\w]+)/', p.path + '/')
                return 'https://www.reddit.com/comments/' + match.group(1) + ('/_/' + after.group(1) if after else '')
        params = urlencode([(k,v) for k,v in parse_qsl(p.query) if k.lower() not in {'utm_source','utm_medium','utm_campaign','utm_term','utm_content','ref','ref_src','fbclid','gclid'}])
        return urlunsplit(('https',host,p.path.rstrip('/') or '/',params,''))
    except Exception:
        return ''


def detect_platform(url):
    host = urlsplit(url).hostname or ''
    if host.endswith('reddit.com'): return 'reddit'
    if host.endswith('x.com') or host.endswith('twitter.com'): return 'x'
    if host.endswith('t.me') or host.endswith('telegram.org'): return 'telegram_public'
    if host.endswith('discord.com') or host.endswith('discord.gg'): return 'discord_public_index'
    return 'web'


def analyze(text, author='', platform='', parent_ref='', source_kind=''):
    text = (text or '').strip()
    question = any(re.search(p, text, re.I | re.S) for p in QUESTION) or ('?' in text and bool(EARLY.search(text)))
    access = bool(EARLY.search(text) and any(re.search(p, text, re.I) for p in ACCESS))
    denial = bool(NEGATION.search(text))
    firsthand = bool(DIRECT.search(text)) and not denial
    target = author.lstrip('@').casefold() == TARGET.casefold()
    categories=[]
    if question: categories.append('QUESTION_ACCES')
    if access: categories.append('INDICE_ACCES')
    if firsthand and access: categories.append('AFFIRMATION_PERSONNELLE')
    if denial: categories.append('DENEGATION')
    if target: categories.append('AUTEUR_CIBLE')
    score = (15 if question else 0) + (30 if access else 0) + (25 if firsthand and access else 0) + (15 if parent_ref and access else 0) + (10 if target and access else 0)
    if denial: score = max(0, score-18)
    if source_kind in ('search_snippet','rss_snippet'): score = min(score, 45)
    label = 'EXTRAIT INDEXÉ — NON VÉRIFIÉ' if source_kind in ('search_snippet','rss_snippet') else 'MESSAGE FOURNI' if source_kind == 'import' else 'API AUTORISÉE'
    return {'question':question, 'access':access, 'firsthand':firsthand, 'denial':denial, 'score': min(100,score), 'labels':','.join(categories), 'verification':label}


@dataclass
class Record:
    url: str
    text: str
    title: str = ''
    author: str = ''
    platform: str = 'web'
    source_kind: str = 'search_snippet'
    external_id: str = ''
    parent_ref: str = ''
    published_at: str = ''
    fetched_at: str = ''
    query: str = ''


class Store:
    def __init__(self, path=DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), timeout=20)
        self.conn.row_factory=sqlite3.Row
        self.conn.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS records(
          id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT NOT NULL UNIQUE, text TEXT, title TEXT,
          author TEXT, platform TEXT, source_kind TEXT, external_id TEXT, parent_ref TEXT,
          published_at TEXT, fetched_at TEXT, query TEXT, score INTEGER, categories TEXT,
          verification TEXT, checked INTEGER DEFAULT 0, note TEXT DEFAULT '', screenshot TEXT DEFAULT '',
          updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_external ON records(external_id);
        CREATE INDEX IF NOT EXISTS ix_parent ON records(parent_ref);
        CREATE INDEX IF NOT EXISTS ix_score ON records(score);
        CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, ts TEXT, provider TEXT,
          status TEXT, queries INTEGER, found INTEGER, notes TEXT);
        CREATE TABLE IF NOT EXISTS checkpoints(key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);
        ''')
        self.conn.commit()
        # Privacy/Reddit deletion precaution: no retained Reddit API content beyond 48h.
        # Fresh collection on the next authorized run can refresh it.
        with self.conn:
            # Migration from V3: Brave snippets had source_kind='search_snippet'.
            # Eliminate any previously retained Brave Search Results on DB opening.
            self.conn.execute("DELETE FROM records WHERE source_kind='search_snippet'")
            self.conn.execute('''DELETE FROM records WHERE platform='reddit'
                AND julianday('now')-julianday(fetched_at)>2''')

    def add(self, r:Record):
        r.url=canonical_url(r.url)
        if not r.url: return False
        r.text = (r.text or '')[:30000]
        r.title = (r.title or '')[:1000]
        r.fetched_at = r.fetched_at or utcnow()
        a=analyze(r.title+'\n'+r.text,r.author,r.platform,r.parent_ref,r.source_kind)
        existing=self.conn.execute('SELECT id,source_kind,length(text) AS len FROM records WHERE url=?',(r.url,)).fetchone()
        # Never overwrite richer API/import text with an indexed snippet.
        if existing:
            if existing['source_kind'] not in ('rss_snippet','search_snippet') and r.source_kind in ('rss_snippet','search_snippet'):
                return False
            if (existing['len'] or 0)>len(r.text) and existing['source_kind']==r.source_kind:
                return False
        with self.conn:
            self.conn.execute('''INSERT INTO records(url,text,title,author,platform,source_kind,external_id,parent_ref,published_at,
               fetched_at,query,score,categories,verification,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(url) DO UPDATE SET text=excluded.text,title=excluded.title,author=excluded.author,
              platform=excluded.platform,source_kind=excluded.source_kind,external_id=excluded.external_id,
              parent_ref=excluded.parent_ref,published_at=excluded.published_at,fetched_at=excluded.fetched_at,
              query=excluded.query,score=excluded.score,categories=excluded.categories,
              verification=excluded.verification,updated_at=excluded.updated_at''',(
                r.url,r.text,r.title,r.author,r.platform,r.source_kind,r.external_id,r.parent_ref,
                r.published_at,r.fetched_at,r.query,a['score'],a['labels'],a['verification'],utcnow()))
        return not bool(existing)

    def rows(self, minimum=0, limit=30000):
        return self.conn.execute('SELECT * FROM records WHERE score>=? ORDER BY score DESC,id DESC LIMIT ?', (minimum,limit)).fetchall()

    def summary(self):
        return dict(self.conn.execute('SELECT count(*) AS total, sum(score>=30) AS pistes, sum(checked) AS verified, sum(source_kind IN ("rss_snippet","search_snippet")) AS snippets FROM records').fetchone())

    def runs(self): return self.conn.execute('SELECT * FROM runs ORDER BY id DESC').fetchall()
    def run(self, provider,status,queries,found,notes=''):
        with self.conn:
            self.conn.execute('INSERT INTO runs(ts,provider,status,queries,found,notes) VALUES(?,?,?,?,?,?)',
                (utcnow(),provider,status,queries,found,str(notes)[:3000]))

    def checkpoint(self,key, value=None):
        if value is None:
            r=self.conn.execute('SELECT value FROM checkpoints WHERE key=?',(key,)).fetchone()
            return r['value'] if r else None
        with self.conn:
            self.conn.execute('INSERT OR REPLACE INTO checkpoints VALUES(?,?,?)',(key,str(value),utcnow()))

    def annotate(self,id,checked=False,note='',screenshot=''):
        if screenshot:
            src=Path(screenshot)
            if not src.is_file() or src.suffix.lower() not in ('.png','.jpg','.jpeg','.webp'):
                raise ValueError('Capture invalide')
            if src.stat().st_size>25*1024*1024: raise ValueError('Capture trop volumineuse (>25 Mo)')
            dest=OUTPUT/'captures'; dest.mkdir(exist_ok=True)
            digest=hashlib.sha256(src.read_bytes()).hexdigest()[:16]
            new=dest/(digest+src.suffix.lower());
            if src.resolve()!=new.resolve(): shutil.copy2(src,new)
            screenshot=str(new.relative_to(OUTPUT))
        with self.conn:
            self.conn.execute('UPDATE records SET checked=?, note=?, screenshot=?,updated_at=? WHERE id=?',
                (int(checked),note[:4000],screenshot,utcnow(),id))

    def remove_reddit_deleted(self, ids):
        # Reddit terms require deletion of previously stored removed user content.
        with self.conn:
            for id in ids:
                self.conn.execute('''UPDATE records SET text='',title='',author='',categories='SUPPRIME_SUR_REDDIT',
                      score=0, note='',screenshot='',checked=0,updated_at=? WHERE external_id=? AND platform='reddit' ''',(utcnow(),id))


def esc(x): return html.escape(str(x or ''))

def export(store:Store):
    rows=store.rows(); runs=store.runs()
    csvpath=OUTPUT/'preuves.csv'
    # Protect spreadsheet programs against CSV formula injection.
    def cell(v):
        s=str(v if v is not None else '')
        return "'"+s if s.lstrip().startswith(('=','+','-','@')) else s
    with csvpath.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f,delimiter=';')
        cols=['id','platform','score','categories','verification','title','text','url','author','published_at','parent_ref','source_kind','checked','note','screenshot']
        w.writerow(cols)
        for r in rows: w.writerow([cell(r[k]) for k in cols])
    with (OUTPUT/'preuves.json').open('w',encoding='utf-8') as f:
        json.dump([dict(r) for r in rows],f,ensure_ascii=False,indent=2)
    groups={}
    for r in rows:
        if r['external_id']: groups[(r['platform'],r['external_id'])]=r
    pairs=[]
    for r in rows:
        if r['parent_ref']:
            p=groups.get((r['platform'],r['parent_ref']))
            if p and ('QUESTION_ACCES' in p['categories'] or 'QUESTION_ACCES' in r['categories']) and r['id']!=p['id']:
                pairs.append((p,r))
    cards=[]
    for r in rows:
        if r['score']<=0: continue
        screenshot=''
        if r['screenshot']:
            screenshot=f'<a href="{esc(r["screenshot"])}">Capture originale (écran utilisateur)</a><div><img src="{esc(r["screenshot"])}" alt="Capture ajoutée localement" style="max-width:min(100%,570px);border-radius:9px;margin-top:10px"></div>'
        cards.append(f'''<article><div class="meta"><b>{esc(r['platform'])}</b><span>{esc(r['verification'])}</span>
        <strong>{r['score']}/100</strong></div><h3>{esc(r['title'] or '(sans titre)')}</h3><p>{esc((r['text'] or '')[:2000])}</p>
        <small>{esc(r['categories'])} · Auteur : {esc(r['author'])} · {esc(r['published_at'])}</small>
        <p><a href="{esc(r['url'])}" target="_blank" rel="noopener noreferrer">Ouvrir la publication originale ↗</a> {screenshot}</p>
        <p class="note">{esc(r['note'])}</p></article>''')
    statuses=''.join(f'<tr><td>{esc(x["ts"])}</td><td>{esc(x["provider"])}</td><td>{esc(x["status"])}</td><td>{x["queries"]}</td><td>{x["found"]}</td><td>{esc(x["notes"])}</td></tr>' for x in runs)
    rel=''.join(f'<li><a href="{esc(p["url"])}">Question</a> → <a href="{esc(r["url"])}">Réponse</a> ({esc(r["author"])})</li>' for p,r in pairs)
    page=f'''<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>LEAKSOURCE — Rapport de provenance</title><style>body{{background:#0d111c;color:#eaf0f7;font:15px system-ui;margin:0}}main{{max-width:1060px;margin:45px auto;padding:0 20px}}h1{{font-size:29px}}h2{{margin-top:32px}}p{{line-height:1.6}}.muted,small{{color:#9daabc}}article{{border:1px solid #31394c;padding:20px;border-radius:13px;margin:13px 0;background:#171d2c}}article p{{white-space:pre-wrap;overflow-wrap:anywhere}}article h3{{margin:9px 0}}a{{color:#9aceff}}.meta{{display:flex;gap:15px;justify-content:space-between;color:#a6cfff}}.note{{color:#d2e0be}}.warn{{border-left:4px solid #e9b454;background:#23212b;padding:15px}}table{{border-collapse:collapse;width:100%;font-size:12px}}td,th{{text-align:left;border-bottom:1px solid #354056;padding:7px;overflow-wrap:anywhere}}.scroll{{overflow-x:auto}}</style>
    <main><h1>LEAKSOURCE INVESTIGATOR — Rapport</h1><p class="muted">Généré {esc(utcnow())} · Compte cible @d0nut2x · {len(rows)} éléments stockés · {len(pairs)} relations question-réponse identifiées</p>
    <p class="warn"><b>Limites documentées :</b> un résultat indexé n'est PAS une capture de tweet ni une preuve que le message existe encore. Aucun connecteur ne garantit toutes les archives. Les notes ne prouvent jamais l'existence d'une copie piratée ou l'identité d'une source confidentielle. Les scores classent la pertinence linguistique, pas la fiabilité d'un témoignage. Respecter la vie privée des personnes.</p>
    <h2>Couverture et erreurs par source</h2><div class="scroll"><table><tr><th>Date</th><th>Connecteur</th><th>État</th><th>Requêtes/threads</th><th>Nouveaux éléments</th><th>Remarques</th></tr>{statuses}</table></div>
    <h2>Questions et réponses reliées par ID de parent (pas par supposition)</h2><ul>{rel or '<li>Aucune relation vérifiée dans les données disponibles</li>'}</ul>
    <h2>Éléments triés par pertinence</h2>{''.join(cards) or '<p>Aucun élément pertinent enregistré.</p>'}</main></html>'''
    path=OUTPUT/'rapport.html'; path.write_text(page,encoding='utf-8')
    return path
