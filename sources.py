"""Public discovery + official authorized API adapters. No browser scraping or bypasses."""
from __future__ import annotations
import csv, io, json, os, re, threading, time, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, quote
import requests
from engine import Record, Store, TARGET, canonical_url, detect_platform, utcnow

UA='LeakSourceInvestigator/3.0 (personal investigation; API-only; contact: local-user)'

class LimitStop(Exception): pass


def query_set():
    # Small, diverse searches. Broad-to-narrow: no strict requirement for all synonyms in one message.
    subjects=['"d0nut2x"','"dOnut2x"','"d0nut2x" "Bleach"', '"d0nut2x" "One Piece"','"d0nut2x" "Mushoku Tensei"']
    intents=[
       '"how" "episode"','"watch early"','"before release"','"how do you"',
       '"source"','"screener"','"leak"','"staff"', '"how did"',
       '"how does he"', '"access"','"contact"','"insider"','"credits"',
       '"comment" "avance"','"épisode en avance"', '"先行"','"リーク"',
    ]
    queries=[]
    for s in subjects:
        for intent in intents:
            queries.append(s+' '+intent)
    specialized=[
       'site:x.com/d0nut2x/ "episode"', 'site:x.com/d0nut2x/ "source"',
       'site:twitter.com/d0nut2x/ "episode"', 'site:reddit.com "d0nut2x" "early"',
       'site:reddit.com "d0nut2x" "leaks"', 'site:reddit.com "d0nut2x" "screeners"',
       'site:reddit.com "d0nut2x" "how"', 'site:reddit.com "d0nut2x" "Bleach"',
       'site:reddit.com "d0nut2x" "episode 49"',
       'site:reddit.com "Bleach TYBW" "early access"',
       'site:reddit.com/r/bleach "d0nut2x"',
       'site:reddit.com/r/AnimeLeaks "Bleach"',
       'site:discord.com "d0nut2x" "leaks"',
       'site:t.me "d0nut2x"', '"d0nut2x" "YonkouProd"',
       '"d0nut2x" "staff list"', '"d0nut2x" "studio"',
       '"BLEACH" "49" "full staff"',
       '"BLEACH" "49" "advance screener"',
       '"bleach" "先行視聴" "49"',
       '"bleach" "フラゲ" "49"',
    ]
    # De-duplicate keeping order.
    return list(dict.fromkeys(specialized+queries))


class HTTP:
    def __init__(self, stop=None, timeout=18):
        self.stop=stop or threading.Event()
        self.timeout=timeout
        self.session=requests.Session(); self.session.headers.update({'User-Agent':UA})
        self.last={}
    def get(self,url,*,params=None,headers=None,minimum_interval=1.2):
        if self.stop.is_set(): raise LimitStop('Arrêt demandé')
        from urllib.parse import urlsplit
        host=urlsplit(url).hostname
        gap=time.monotonic()-self.last.get(host,-1e12)
        if gap<minimum_interval:
            if self.stop.wait(minimum_interval-gap): raise LimitStop('Arrêt demandé')
        self.last[host]=time.monotonic()
        try:
            r=self.session.get(url, params=params, headers=headers, timeout=self.timeout, allow_redirects=True)
        except requests.RequestException as e:
            raise RuntimeError('Connexion : '+str(e)[:160]) from e
        if r.status_code==429:
            raise LimitStop('Quota 429 (Retry-After='+str(r.headers.get('Retry-After','non fourni'))+'). Arrêt sans contourner la limitation.')
        if r.status_code in (401,403):
            raise LimitStop('Accès refusé HTTP '+str(r.status_code)+' — arrêter plutôt que contourner la protection.')
        if r.status_code>=400: raise RuntimeError('HTTP '+str(r.status_code)+' '+urlsplit(r.url).hostname)
        if len(r.content)>5_000_000: raise RuntimeError('Réponse trop grande')
        return r


def normalize_search_entry(title,url,text,query,kind):
    clean=canonical_url(url)
    return Record(url=clean,title=title,text=re.sub(r'<[^>]+>',' ',text or ''),platform=detect_platform(clean),query=query,source_kind=kind)


def bing_rss(http,q):
    r=http.get('https://www.bing.com/search',params={'q':q,'format':'rss'},minimum_interval=2.5)
    doc=ET.fromstring(r.content)
    if doc.tag.lower() != 'rss': raise RuntimeError('Flux RSS invalide : le fournisseur renvoie autre chose qu’un RSS')
    out=[]
    for item in doc.findall('./channel/item'):
        title=item.findtext('title','')
        link=item.findtext('link','')
        body=item.findtext('description','')
        out.append(normalize_search_entry(title,link,body,q,'rss_snippet'))
    return out


def news_rss(http,q):
    r=http.get('https://news.google.com/rss/search',params={'q':q,'hl':'en-US','gl':'US','ceid':'US:en'},minimum_interval=2.5)
    doc=ET.fromstring(r.content)
    if doc.tag.lower() != 'rss': raise RuntimeError('Flux RSS invalide : le fournisseur renvoie autre chose qu’un RSS')
    out=[]
    for item in doc.findall('./channel/item'):
        title=item.findtext('title','')
        link=item.findtext('link','')
        body=item.findtext('description','')
        out.append(normalize_search_entry(title,link,body,q,'rss_snippet'))
    return out


def brave_web(http,q,key):
    r=http.get('https://api.search.brave.com/res/v1/web/search',params={'q':q,'count':20,'search_lang':'en','safesearch':'moderate'},
               headers={'X-Subscription-Token':key,'Accept':'application/json'},minimum_interval=0.7)
    data=r.json()
    return [normalize_search_entry(x.get('title',''),x.get('url',''),x.get('description',''),q,'search_snippet')
      for x in data.get('web',{}).get('results',[])]


def discover(store:Store,http:HTTP,emit, max_queries=36, mode='rss', brave_key='',stop=None, on_brave_results=None):
    """Only index/snippet discovery; never claim complete X or Reddit comments."""
    queries=query_set(); max_queries=max(1,min(160,int(max_queries)))
    providers=[]
    if mode in ('rss','both','all_plus'): providers=[('Bing RSS',bing_rss),('Google News RSS',news_rss)]
    if mode in ('brave','both','all_plus') and brave_key: providers.append(('Brave API (crédits)',None))
    if not providers:
        emit('Aucune source activée (clé Brave absente ?)'); return
    for provider,fn in providers:
        found=0; attempted=0; errors=[]
        for q in queries[:max_queries]:
            if stop and stop.is_set(): break
            checkpoint='discovery:'+provider+':'+q
            # Resume within 18h; indexed searches change, so can be rerun later.
            old=store.checkpoint(checkpoint)
            if old:
                try:
                    from datetime import datetime, timezone
                    if (datetime.now(timezone.utc)-datetime.fromisoformat(old)).total_seconds()<18*3600:
                        continue
                except ValueError: pass
            attempted+=1
            try:
                batch=brave_web(http,q,brave_key) if fn is None else fn(http,q)
                if fn is None:
                    # Brave Search Terms (Sep 2026) forbid storage/cache/database
                    # of API Search Results, including URLs, titles and snippets.
                    # Keep results ONLY transiently in GUI memory for live inspection.
                    if on_brave_results is not None:
                        on_brave_results(batch)
                    new=len(batch)
                else:
                    new=sum(store.add(rec) for rec in batch)
                found+=new
                store.checkpoint(checkpoint,utcnow())
                emit(f'{provider} · {attempted} requêtes · {len(batch)} résultats · ' +
                     (f'{new} temporaires (non sauvegardés)' if fn is None else f'{new} nouveaux'))
            except LimitStop as e:
                errors.append(str(e)); emit('STOP '+provider+' : '+str(e)); break
            except (ValueError, ET.ParseError, RuntimeError,requests.RequestException) as e:
                errors.append(str(e)[:160]); emit('Erreur '+provider+' : '+str(e)[:160]);
                if len(errors)>=5:
                    emit('Arrêt du connecteur après 5 erreurs (pas de boucle infinie)'); break
        state='PARTIEL' if errors or (stop and stop.is_set()) else 'TERMINE_POUR_QUERIES_CONFIGUREES'
        store.run(provider,state,attempted,found,('; '.join(errors[:4]) or 'Indexation, non exhaustif') + (' · Brave : résultats uniquement en RAM, non sauvegardés' if fn is None else ''))
        emit(f'{provider} terminé · {found} nouveaux · état {state}')


def import_records(path,store:Store):
    """Ingest data that user already holds. No network access. CSV or JSON/JSONL."""
    path=Path(path)
    if path.stat().st_size>80_000_000: raise ValueError('Fichier >80 Mo : traiter en plusieurs exports')
    if path.suffix.lower()=='.csv':
        with path.open('r',encoding='utf-8-sig',newline='') as f: data=list(csv.DictReader(f))
    elif path.suffix.lower()=='.jsonl':
        data=[json.loads(x) for x in path.read_text(encoding='utf-8-sig').splitlines() if x.strip()]
    elif path.suffix.lower()=='.json':
        data=json.loads(path.read_text(encoding='utf-8-sig'))
    else: raise ValueError('Importer .csv, .json ou .jsonl')
    if isinstance(data,dict):
        data=data.get('data',data.get('records',data.get('tweets',data.get('comments',[data]))))
    if not isinstance(data,list): raise ValueError('Format JSON attendu : liste de messages')
    total=0
    for x in data:
        if not isinstance(x,dict): continue
        # X-like API tweet object or normalized rows (URLs required).
        text=x.get('text',x.get('body',x.get('selftext','')))
        url=x.get('url',x.get('permalink',''))
        external=str(x.get('external_id',x.get('id','')))
        platform=x.get('platform',detect_platform(url))
        if url.startswith('/r/') or url.startswith('/comments/'): url='https://www.reddit.com'+url
        if not url and platform=='x' and external.isdigit():
            url=f'https://x.com/i/status/{external}'
        parent_ref=str(x.get('parent_ref',x.get('parent_id','')))
        if isinstance(x.get('referenced_tweets'),list):
            refs=x['referenced_tweets']; parent_ref=str(next((a['id'] for a in refs if a.get('type')=='replied_to'),parent_ref))
        author=x.get('author',x.get('username',''))
        if isinstance(author,dict): author=author.get('name','')
        r=Record(url=url,text=str(text or ''),title=str(x.get('title','')),author=str(author or ''),
             source_kind='import',platform=platform,external_id=external,parent_ref=parent_ref,
             published_at=str(x.get('created_at',x.get('published_at',''))))
        if store.add(r): total+=1
    store.run('Import fichier', 'TERMINE',len(data),total,path.name)
    return total


def _praw_module():
    try: import praw; return praw
    except ImportError: raise RuntimeError('Module PRAW absent : exécuter INSTALLER.bat pour activer Reddit')


def reddit_official(store:Store,emit,stop,client_id,client_secret,username='',queries=12,max_threads=16,max_comments=2500,full=False):
    """Authorized PRAW only. Fully walks selected threads with replace_more if allowed.
    Request access/approval from Reddit beforehand. Search only threads: Reddit's own search is not a full historical comment search.
    """
    if not client_id or not client_secret: raise ValueError('Accès Reddit autorisé manquant')
    praw=_praw_module()
    api=praw.Reddit(client_id=client_id,client_secret=client_secret,user_agent=UA,check_for_async=False)
    api.read_only=True
    qlist=['"d0nut2x"','"dOnut2x"','"Bleach" "episode 49"','"Bleach" "leaker"',
           '"Bleach" "screeners"','"YonkouProd"','"BLEACH" "early"','"d0nut2x" "source"',
           '"Bleach TYBW" "leak"','"BLEACH" "staff list"', '"d0nut2x" "anime"',
           '"Bleach" "before release"'][:max(1,int(queries))]
    ids={}; search_errors=[]; fetched=0; retained=0; scanned=0; incomplete=0
    for q in qlist:
        if stop.is_set(): break
        try:
            for s in api.subreddit('all').search(q, sort='relevance', time_filter='all',limit=65):
                if s.id not in ids: ids[s.id]=s
                if len(ids)>=max_threads*4: break
            emit(f'Reddit : recherche {q} · {len(ids)} fils candidats')
        except Exception as e:
            search_errors.append(str(e)[:180]); emit('Erreur Reddit recherche : '+str(e)[:180]); break
    # Add indexed Reddit threads to candidate set via their *official* Reddit API IDs.
    # Search engines may surface discussions that Reddit's post search misses.
    for row in store.rows(limit=10000):
        if row['platform']!='reddit': continue
        m=re.search(r'/comments/([a-z0-9]+)',row['url'],re.I)
        if not m or m.group(1) in ids:continue
        try:
            candidate=api.submission(id=m.group(1))
            # Loading title can make an API request; keep within limit.
            if candidate.title: ids[m.group(1)]=candidate
            if len(ids)>=max_threads*5:break
        except Exception as e:
            emit('Reddit : fil trouvé par index indisponible : '+str(e)[:90])
    # Prioritize direct target mentions in titles/selftexts.
    submissions=sorted(ids.values(),key=lambda s:('d0nut2x' in (s.title+' '+str(s.selftext)).lower(),
                         'bleach' in s.title.lower(),s.score),reverse=True)[:max_threads]
    for sub in submissions:
        if stop.is_set() or scanned>=max_comments: break
        try:
            sub.comments.replace_more(limit=None if full else min(30,max(2,max_comments//70)), threshold=0)
            comments=sub.comments.list()
            fetched+=1
            remaining=max(0,max_comments-scanned)
            scanned+=min(len(comments),remaining)
            if len(comments)<getattr(sub,'num_comments',0): incomplete+=1
            emit(f'Reddit r/{sub.subreddit} · {len(comments)} commentaires chargés, {sub.num_comments} annoncés')
            root=Record(url='https://www.reddit.com'+sub.permalink,text=sub.selftext or '',title=sub.title,
                     author=str(sub.author) if sub.author else '',platform='reddit',source_kind='official_api',
                     external_id='t3_'+sub.id,published_at=str(sub.created_utc))
            if store.add(root): retained+=1
            count=0
            for c in comments[:remaining]:
                if stop.is_set(): break
                count+=1
                # Avoid retaining irrelevant Reddit content by default.
                body=getattr(c,'body','') or ''
                if body in ('[deleted]','[removed]'): continue
                if not re.search(r'd0nut2x|bleach|episode|screener|leak|before release|early|staff|source|how did|access|先行|リーク|フラゲ',body,re.I):
                    continue
                parent=str(c.parent_id)
                entry=Record(url='https://www.reddit.com'+c.permalink,title='',text=body,author=str(c.author) if c.author else '',
                    platform='reddit',source_kind='official_api',external_id='t1_'+c.id,parent_ref=parent,published_at=str(c.created_utc))
                if store.add(entry): retained+=1
            emit(f'Reddit : {count} commentaires explorés, {retained} éléments enregistrés')
        except Exception as e:
            search_errors.append(str(e)[:180]); emit('Erreur fil Reddit : '+str(e)[:180])
            if len(search_errors)>6: break
    state='PARTIEL' if search_errors or stop.is_set() or incomplete or scanned>=max_comments else 'SELECTION_TRAITEE'
    store.run('Reddit API autorisée',state,len(qlist)+fetched,retained,
        f'{len(ids)} candidats; {fetched} fils; {scanned} commentaires vus; {incomplete} fils potentiellement incomplets; erreurs: {search_errors[:3]}')
    return retained


def x_official(store,http,emit,stop,bearer,allow_charges=False,max_pages=3,archive=False):
    """Disabled unless opted in to potential paid X API charges; no credential-sharing or web scraping."""
    if not allow_charges: raise ValueError('X désactivé : risque de facturation, consentement explicite requis')
    if not bearer: raise ValueError('Bearer Token X manquant')
    base='https://api.x.com/2/tweets/search/' + ('all' if archive else 'recent')
    queries=['from:d0nut2x (episode OR bleach OR early OR source OR screener)',
             'to:d0nut2x (episode OR early OR source OR screener OR leak)',
             '"d0nut2x" (episode OR leak OR before OR source)']
    n=0; calls=0; errors=[]
    for q in queries:
        token=None
        for page in range(min(10,max(1,int(max_pages)))):
            if stop.is_set(): break
            pars={'query':q,'max_results':100,'tweet.fields':'author_id,conversation_id,created_at,in_reply_to_user_id,referenced_tweets','expansions':'author_id', 'user.fields':'username'}
            if token: pars['next_token']=token
            try:
                data=http.get(base,params=pars,headers={'Authorization':'Bearer '+bearer},minimum_interval=2.0).json()
                calls+=1
                users={u['id']:u.get('username','') for u in data.get('includes',{}).get('users',[])}
                for x in data.get('data',[]):
                    par=str(next((a.get('id') for a in x.get('referenced_tweets',[]) if a.get('type')=='replied_to'),''))
                    if store.add(Record(url=f'https://x.com/i/status/{x["id"]}',text=x.get('text',''),
                        author=users.get(x.get('author_id'),x.get('author_id','')),platform='x',source_kind='official_api',
                        external_id=x['id'],parent_ref=par,published_at=x.get('created_at',''),query=q)): n+=1
                token=data.get('meta',{}).get('next_token')
                emit(f'X officiel · {calls} requêtes API · {n} posts conservés')
                if not token: break
            except (LimitStop,Exception) as e:
                errors.append(str(e)[:200]); emit('X arrêté : '+str(e)[:200]); break
        if errors: break
    store.run('X API officielle','PARTIEL' if errors or stop.is_set() else 'FENETRE_TRAITEE',calls,n,
        'Recherche récente 7 jours' if not archive else 'Archive sur accès éligible'+'; '+str(errors[:2]))
    return n


def bluesky_public(store:Store,http:HTTP,emit,stop,max_queries=14,max_posts=900):
    """Official public AppView, no credentials; public post replies from indexed search, not a complete Bluesky archive."""
    queries=['d0nut2x','Bleach TYBW episode 49','Bleach early leak','Bleach screener','Bleach pre release',
             'dOnut2x Bleach','YonkouProd','bleach 49 staff', 'bleach insider', 'Bleach 先行視聴',
             'Bleach リーク', 'leaker episode early', 'Bleach leak group','Bleach before airing'][:max_queries]
    found=0; calls=0; errors=[]
    for q in queries:
        if stop.is_set():break
        for sort in ('latest','top'):
            if stop.is_set():break
            try:
                # Public app-view at api.bsky.app. One page per query: subsequent pages can be unavailable without auth.
                r=http.get('https://api.bsky.app/xrpc/app.bsky.feed.searchPosts',
                            params={'q':q,'sort':sort,'limit':100},minimum_interval=1.5)
                calls+=1
                posts=r.json().get('posts',[])
                for p in posts:
                    uri=p.get('uri','')
                    rk=uri.split('/')[-1]
                    actor=p.get('author',{}).get('handle','')
                    if not (rk and actor):continue
                    url=f'https://bsky.app/profile/{actor}/post/{rk}'
                    record=p.get('record') or {}
                    parent_uri=(record.get('reply') or {}).get('parent',{}).get('uri','')
                    txt=record.get('text','')
                    if store.add(Record(url=url,text=txt,author=actor,platform='bluesky',source_kind='official_api',
                      external_id=uri,parent_ref=parent_uri,published_at=record.get('createdAt',''),query=q)): found+=1
                emit(f'Bluesky {q} ({sort}) · {len(posts)} posts · {found} nouveaux')
            except (RuntimeError,ValueError,LimitStop) as e:
                errors.append(str(e)[:160]);emit('Bluesky : '+str(e)[:160]);break
        if errors:break
        if found>=max_posts:break
    store.run('Bluesky API publique','PARTIEL' if errors or stop.is_set() else 'FENETRE_TRAITEE',calls,found,
              'Pages de résultats accessibles uniquement, pas tout l’historique. '+str(errors[:2]))


def hackernews_public(store:Store,http:HTTP,emit,stop):
    """Third party public indexed API for Hacker News comments, often low yield for anime."""
    queries=['d0nut2x','Bleach TYBW','anime screener leaks','Bleach anime episode leak','YonkouProd']
    found=0;calls=0;errors=[]
    for q in queries:
        if stop.is_set():break
        try:
            r=http.get('https://hn.algolia.com/api/v1/search_by_date',params={'query':q,'tags':'comment','hitsPerPage':100},minimum_interval=1.5)
            calls+=1
            for hit in r.json().get('hits',[]):
                oid=hit.get('objectID','')
                if not oid: continue
                url=f'https://news.ycombinator.com/item?id={oid}'
                txt=hit.get('comment_text','')
                if store.add(Record(url=url,title=hit.get('story_title') or '',text=txt,
                   author=hit.get('author',''),platform='hackernews',source_kind='official_api',external_id=oid,
                   published_at=hit.get('created_at',''),query=q)): found+=1
            emit(f'Hacker News · {q} · {found} nouveaux')
        except (RuntimeError,ValueError,LimitStop) as e:
            errors.append(str(e)[:160]);emit('Hacker News : '+str(e)[:160]); break
    store.run('Hacker News Algolia','PARTIEL' if errors or stop.is_set() else 'FENETRE_TRAITEE',calls,found,str(errors[:2]))
