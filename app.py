"""Desktop GUI; safe official API integration, indexed discovery and audit trail."""
import os, queue, threading, traceback, webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from engine import Store, DB, OUTPUT, export, Record, canonical_url
from sources import HTTP, discover, import_records, reddit_official, x_official, bluesky_public, hackernews_public
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent/'.env')
except ImportError: pass

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('LEAKSOURCE INVESTIGATOR 3.1 · enquête automatique · @d0nut2x')
        self.geometry('1190x750'); self.minsize(860,630)
        self.stop=threading.Event();self.msgs=queue.Queue(); self.busy=False
        self.vars={'mode':tk.StringVar(value='all_free'), 'queries':tk.IntVar(value=32),
            'reddit_threads':tk.IntVar(value=24), 'reddit_comments':tk.IntVar(value=3500),
            'x_pages':tk.IntVar(value=2), 'x_archive':tk.BooleanVar(value=False),
            'reddit_full':tk.BooleanVar(value=False)}
        self.brave_results=[]
        style=ttk.Style(self)
        try: style.theme_use('clam')
        except tk.TclError: pass
        style.configure('Header.TLabel',font=('Segoe UI',18,'bold'))
        style.configure('TButton',padding=7)
        style.configure('Treeview',rowheight=30,font=('Segoe UI',10))
        self.build(); self.refresh(); self.after(150,self.poll)

    def build(self):
        root=ttk.Frame(self,padding=16);root.pack(fill='both',expand=True)
        ttk.Label(root,text='LEAKSOURCE INVESTIGATOR 3.1',style='Header.TLabel').pack(anchor='w')
        ttk.Label(root,text='Recherche publique automatisée · Reddit officiel si autorisé · X officiel optionnel · aucun contournement').pack(anchor='w',pady=(0,8))
        nb=ttk.Notebook(root); nb.pack(fill='both',expand=True)
        overview=ttk.Frame(nb,padding=12); nb.add(overview,text='  1 · Enquête  ')
        proofs=ttk.Frame(nb,padding=12);nb.add(proofs,text='  2 · Indices et preuves  ')
        settings=ttk.Frame(nb,padding=12);nb.add(settings,text='  3 · Sources avancées  ')
        brave_tab=ttk.Frame(nb,padding=12);nb.add(brave_tab,text='  4 · Résultats Brave (temporaires)  ')
        controls=ttk.LabelFrame(overview,text='Découverte automatique sans aucune clé (résultats indexés uniquement)',padding=12)
        controls.pack(fill='x',pady=(0,9))
        row=ttk.Frame(controls);row.pack(fill='x')
        ttk.Label(row,text='Sources :').pack(side='left')
        ttk.Combobox(row,textvariable=self.vars['mode'],values=['all_free','all_plus','rss','brave','both'],state='readonly',width=9).pack(side='left',padx=7)
        ttk.Label(row,text='Requêtes par source :').pack(side='left',padx=(20,0))
        ttk.Spinbox(row,from_=5,to=160,textvariable=self.vars['queries'],width=7).pack(side='left',padx=6)
        self.startbtn=ttk.Button(row,text='▶ DÉMARRER L’ENQUÊTE GRATUITE',command=self.start_discovery)
        self.startbtn.pack(side='left',padx=(20,8))
        self.stopbtn=ttk.Button(row,text='■ Arrêter',command=self.stop.set,state='disabled');self.stopbtn.pack(side='left')
        ttk.Label(controls,text='all_free = RSS + Bluesky/Hacker News · all_plus = ces mêmes sources + Brave · brave = Brave uniquement · both = RSS + Brave.\nBrave : résultats VISIBLES dans l’onglet 4, non sauvegardés. Pas de lecture exhaustive des commentaires X/Reddit.',
                  wraplength=1030).pack(anchor='w',pady=(7,0))
        self.tally=ttk.Label(overview,text='');self.tally.pack(anchor='w',pady=5)
        ttk.Label(overview,text='Journal de recherche :').pack(anchor='w')
        logf=ttk.Frame(overview);logf.pack(fill='both',expand=True)
        self.logs=tk.Text(logf,height=12,wrap='word',font=('Consolas',10));self.logs.pack(side='left',fill='both',expand=True)
        sc=ttk.Scrollbar(logf,orient='vertical',command=self.logs.yview);sc.pack(side='right',fill='y');self.logs.config(yscrollcommand=sc.set)
        bottom=ttk.Frame(overview);bottom.pack(fill='x',pady=(10,0))
        ttk.Button(bottom,text='Importer des messages JSON/CSV',command=self.import_file).pack(side='left',padx=(0,8))
        ttk.Button(bottom,text='Générer rapport HTML + CSV + JSON',command=self.report).pack(side='left',padx=(0,8))
        ttk.Button(bottom,text='Ouvrir le dossier résultats',command=lambda:self.open_local(OUTPUT)).pack(side='left')
        ttk.Label(overview,text='Une absence de résultat ne prouve jamais l’absence de source. Le journal indique les erreurs et la couverture.',foreground='#a76e07').pack(anchor='w',pady=(10,0))

        bar=ttk.Frame(proofs);bar.pack(fill='x',pady=(0,8))
        ttk.Button(bar,text='Actualiser',command=self.refresh).pack(side='left')
        ttk.Button(bar,text='Ouvrir source',command=self.open_selected).pack(side='left',padx=6)
        ttk.Button(bar,text='Capture auto dans 8 s',command=self.delayed_capture).pack(side='left',padx=6)
        ttk.Button(bar,text='Ajouter capture existante',command=self.screenshot).pack(side='left',padx=6)
        ttk.Button(bar,text='Noter / vérifier',command=self.annotate).pack(side='left',padx=6)
        ttk.Button(bar,text='Ajouter un message manuellement',command=self.manual).pack(side='left',padx=6)
        treef=ttk.Frame(proofs);treef.pack(fill='both',expand=True)
        cols=('score','plateforme','type','titre','url')
        self.tree=ttk.Treeview(treef,columns=cols,show='headings',selectmode='browse')
        for col,width in [('score',70),('plateforme',100),('type',170),('titre',380),('url',380)]:
            self.tree.heading(col,text=col.upper());self.tree.column(col,width=width,stretch=True)
        self.tree.pack(fill='both',expand=True,side='left');vs=ttk.Scrollbar(treef,orient='vertical',command=self.tree.yview);vs.pack(side='right',fill='y');self.tree.configure(yscrollcommand=vs.set)
        self.tree.bind('<Double-1>',lambda e:self.open_selected())
        self.preview=tk.Text(proofs,height=8,wrap='word');self.preview.pack(fill='x',pady=(8,0));self.preview.config(state='disabled')
        self.tree.bind('<<TreeviewSelect>>',lambda e:self.preview_selected())

        fr=ttk.LabelFrame(settings,text='Reddit · uniquement si ton application a été autorisée par Reddit',padding=12);fr.pack(fill='x',pady=(0,10))
        ttk.Label(fr,text='Accès : REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET dans .env. Le programme parcourt les commentaires des fils trouvés,\ny compris les réponses imbriquées, et respecte les quotas officiels.').pack(anchor='w')
        rf=ttk.Frame(fr);rf.pack(fill='x',pady=7)
        ttk.Label(rf,text='Threads max').pack(side='left');ttk.Spinbox(rf,from_=1,to=300,textvariable=self.vars['reddit_threads'],width=6).pack(side='left',padx=6)
        ttk.Label(rf,text='Commentaires à examiner max').pack(side='left',padx=(12,0));ttk.Spinbox(rf,from_=100,to=50000,increment=100,textvariable=self.vars['reddit_comments'],width=9).pack(side='left',padx=6)
        ttk.Checkbutton(rf,text='Charger tous les MoreComments possibles (consomme des quotas)',variable=self.vars['reddit_full']).pack(side='left',padx=12)
        ttk.Button(fr,text='Explorer les threads Reddit autorisés',command=self.start_reddit).pack(anchor='w')
        xf=ttk.LabelFrame(settings,text='X · API officielle (potentiellement payante, jamais activée automatiquement)',padding=12);xf.pack(fill='x',pady=(0,10))
        ttk.Label(xf,text='X_BEARER_TOKEN dans .env. Recherche posts et réponses (fenêtre récente, ou archive si habilitée).\nNe lance aucune lecture X sans confirmation explicite de risque de coût.').pack(anchor='w')
        xr=ttk.Frame(xf);xr.pack(fill='x',pady=8)
        ttk.Label(xr,text='Pages max / requête').pack(side='left');ttk.Spinbox(xr,from_=1,to=10,textvariable=self.vars['x_pages'],width=5).pack(side='left',padx=8)
        ttk.Checkbutton(xr,text='Archive complète (seulement avec accès éligible)',variable=self.vars['x_archive']).pack(side='left')
        ttk.Button(xf,text='Interroger X (confirmation avant facturation)',command=self.start_x).pack(anchor='w')
        ttk.Label(brave_tab,text='Résultats Brave temporaires : aucun titre, extrait ou lien Brave n’est écrit en base, CSV ou rapport.\nIls disparaissent quand tu fermes le programme. Ouvre les pages originales pour vérifier les indices.',wraplength=1000).pack(anchor='w',pady=(0,10))
        brbuttons=ttk.Frame(brave_tab);brbuttons.pack(fill='x',pady=(0,6))
        ttk.Button(brbuttons,text='Ouvrir la page originale sélectionnée',command=self.open_brave).pack(side='left')
        ttk.Button(brbuttons,text='Effacer les résultats en mémoire',command=self.clear_brave).pack(side='left',padx=8)
        bframe=ttk.Frame(brave_tab);bframe.pack(fill='both',expand=True)
        self.brave_tree=ttk.Treeview(bframe,columns=('titre','url'),show='headings',selectmode='browse')
        self.brave_tree.heading('titre',text='TITRE INDEXÉ');self.brave_tree.heading('url',text='PAGE SOURCE')
        self.brave_tree.column('titre',width=380);self.brave_tree.column('url',width=580)
        self.brave_tree.pack(side='left',fill='both',expand=True)
        bscroll=ttk.Scrollbar(bframe,orient='vertical',command=self.brave_tree.yview)
        bscroll.pack(side='right',fill='y');self.brave_tree.configure(yscrollcommand=bscroll.set)
        self.brave_tree.bind('<Double-1>',lambda e:self.open_brave())
        self.brave_preview=tk.Text(brave_tab,height=7,wrap='word')
        self.brave_preview.pack(fill='x',pady=(10,0));self.brave_preview.config(state='disabled')
        self.brave_tree.bind('<<TreeviewSelect>>',lambda e:self.preview_brave())
        inf=ttk.LabelFrame(settings,text='Conformité et traçabilité',padding=12);inf.pack(fill='x')
        ttk.Label(inf,text='• Aucune connexion par cookies, aucun navigateur automatisé sur X/Reddit, aucun contournement de CAPTCHA/429.\n• Les groupes privés Discord/Telegram ne sont jamais parcourus sans autorisation.\n• Les résultats RSS/Brave sont des résumés indexés, pas des preuves de visionnage.\n• Les captures ne sont jamais inventées : tu ajoutes une vraie capture de la page originale.\n• Les contenus Reddit supprimés doivent être effacés (purge automatique après 48 h par prudence).',justify='left').pack(anchor='w')

    def log(self,line): self.msgs.put(('log',line))
    def poll(self):
        try:
            while True:
                kind,val=self.msgs.get_nowait()
                if kind=='log':
                    self.logs.insert('end',str(val)+'\n');self.logs.see('end')
                elif kind=='brave_batch':
                    known={r.url for r in self.brave_results}
                    for r in val:
                        if r.url and r.url not in known:
                            self.brave_results.append(r);known.add(r.url)
                            i=len(self.brave_results)-1
                            self.brave_tree.insert('','end',iid=str(i),values=(r.title[:180],r.url[:450]))
                elif kind=='done':
                    self.busy=False;self.startbtn.config(state='normal');self.stopbtn.config(state='disabled');self.refresh()
                    if val: self.logs.insert('end','TERMINÉ : '+str(val)+'\n'); self.logs.see('end')
        except queue.Empty: pass
        self.after(150,self.poll)
    def start_task(self,fn):
        if self.busy: messagebox.showwarning('En cours','Attends ou arrête la collecte actuelle.');return
        self.busy=True;self.stop.clear();self.startbtn.config(state='disabled');self.stopbtn.config(state='normal')
        def wrapper():
            st=None
            try:
                st=Store(DB);fn(st)
                self.msgs.put(('done','Rapport accessible après export.'))
            except Exception as e:
                self.msgs.put(('log','ERREUR : '+str(e)))
                self.msgs.put(('done','Exécution interrompue.'))
            finally:
                if st: st.conn.close()
        threading.Thread(target=wrapper,daemon=True).start()
    def start_discovery(self):
        mode=self.vars['mode'].get();limit=self.vars['queries'].get()
        key=os.getenv('BRAVE_SEARCH_API_KEY','').strip()
        if mode in ('brave','all_plus') and not key: messagebox.showerror('Clé manquante','BRAVE_SEARCH_API_KEY absent dans .env'); return
        if mode=='both' and not key:
            mode='rss'; self.log('Pas de clé Brave : uniquement RSS.')
        def work(db):
            net=HTTP(self.stop)
            discover(db,net,self.log,max_queries=limit,mode='rss' if mode=='all_free' else mode,brave_key=key,stop=self.stop,
                     on_brave_results=lambda batch:self.msgs.put(('brave_batch',batch)))
            if mode in ('all_free','all_plus') and not self.stop.is_set():
                bluesky_public(db,net,self.log,self.stop)
                hackernews_public(db,net,self.log,self.stop)
        self.start_task(work)
    def clear_brave(self):
        self.brave_results.clear()
        for i in self.brave_tree.get_children(): self.brave_tree.delete(i)
        self.brave_preview.config(state='normal');self.brave_preview.delete('1.0','end')
        self.brave_preview.config(state='disabled')
    def open_brave(self):
        sel=self.brave_tree.selection()
        if not sel:return
        i=int(sel[0])
        if 0<=i<len(self.brave_results): webbrowser.open(self.brave_results[i].url)
    def preview_brave(self):
        sel=self.brave_tree.selection()
        self.brave_preview.config(state='normal');self.brave_preview.delete('1.0','end')
        if sel:
            i=int(sel[0])
            if 0<=i<len(self.brave_results):
                r=self.brave_results[i]
                self.brave_preview.insert('1.0',f'{r.title}\n{r.text[:2000]}\n\n{r.url}\nRequête : {r.query}\nEXTRAIT INDEXÉ, NON VÉRIFIÉ — ne pas copier directement dans le rapport')
        self.brave_preview.config(state='disabled')
    def start_reddit(self):
        cid=os.getenv('REDDIT_CLIENT_ID','').strip(); sec=os.getenv('REDDIT_CLIENT_SECRET','').strip()
        if not cid or not sec:messagebox.showerror('Reddit','Identifiants absents. La connexion nécessite l’approbation de Reddit.');return
        nt=self.vars['reddit_threads'].get();nc=self.vars['reddit_comments'].get();full=self.vars['reddit_full'].get()
        self.start_task(lambda db: reddit_official(db,self.log,self.stop,cid,sec,max_threads=nt,max_comments=nc,full=full))
    def start_x(self):
        token=os.getenv('X_BEARER_TOKEN','').strip()
        if not token: messagebox.showerror('X','Bearer Token absent du .env');return
        if not messagebox.askyesno('ATTENTION — X API payante',
            'X peut facturer la lecture des posts. Aucun plafond de coût absolu n’est garanti par ce programme.\nAs-tu vérifié les tarifs et fixé ton plafond sur X Developer Console ?\n\nCONFIRMER une collecte potentiellement facturée ?'):
            return
        pages=self.vars['x_pages'].get();arch=self.vars['x_archive'].get()
        self.start_task(lambda db: x_official(db,HTTP(self.stop),self.log,self.stop,token,allow_charges=True,max_pages=pages,archive=arch))
    def import_file(self):
        filename=filedialog.askopenfilename(title='Import de messages',filetypes=[('JSON/CSV','*.json *.jsonl *.csv')])
        if not filename:return
        self.start_task(lambda db:self.log(str(import_records(filename,db))+' éléments nouveaux importés.'))
    def selected(self):
        sel=self.tree.selection()
        if not sel:return None
        db=Store(DB)
        try:return db.conn.execute('SELECT * FROM records WHERE id=?',(int(sel[0]),)).fetchone()
        finally:db.conn.close()
    def open_selected(self):
        r=self.selected()
        if r and r['url']:webbrowser.open(r['url'])
    def open_local(self,path):
        try: os.startfile(str(path))
        except AttributeError: webbrowser.open(Path(path).resolve().as_uri())
    def delayed_capture(self):
        r=self.selected()
        if not r:
            messagebox.showinfo('Choisir un indice','Sélectionne une ligne dans le tableau.');return
        if not messagebox.askyesno('Capture locale de TON écran',
           'Après confirmation, le navigateur ouvre la source sélectionnée. Dans 8 secondes, le programme capturera TOUT ton écran.\n\nFerme les éléments privés et affiche le message concerné. La capture reste sur TON PC. La capture ne prouve pas à elle seule que le contenu est authentique.\n\nContinuer ?'):
            return
        try:
            from PIL import ImageGrab
        except ImportError:
            messagebox.showerror('Pillow absent','Relance INSTALLER.bat pour activer ImageGrab.');return
        rid=r['id']; webbrowser.open(r['url']);self.iconify()
        def perform():
            try:
                from PIL import ImageGrab
                from datetime import datetime
                dest=OUTPUT/'captures';dest.mkdir(exist_ok=True)
                path=dest/f'ecran_original_{rid}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
                ImageGrab.grab(all_screens=False).save(path)
                db=Store(DB)
                try:
                    item=db.conn.execute('SELECT * FROM records WHERE id=?',(rid,)).fetchone()
                    if item: db.annotate(rid,bool(item['checked']),item['note'],str(path))
                finally:db.conn.close()
                self.deiconify();self.lift();self.refresh()
                messagebox.showinfo('Capture réalisée','Capture locale enregistrée. Vérifie dans le rapport qu’elle correspond bien à la publication.')
            except Exception as e:
                self.deiconify();messagebox.showerror('Capture',str(e))
        self.after(8000,perform)

    def screenshot(self):
        r=self.selected()
        if not r:messagebox.showinfo('Choisir un indice','Sélectionne une ligne dans le tableau.');return
        image=filedialog.askopenfilename(title='Capture ORIGINALE de la publication, faite par toi',filetypes=[('Images','*.png *.jpg *.jpeg *.webp')])
        if not image:return
        db=Store(DB)
        try:db.annotate(r['id'],bool(r['checked']),r['note'],image)
        except Exception as e:messagebox.showerror('Capture',str(e))
        finally:db.conn.close()
        self.refresh()
    def annotate(self):
        r=self.selected()
        if not r:messagebox.showinfo('Choisir un indice','Sélectionne une ligne dans le tableau.');return
        w=tk.Toplevel(self);w.title('Vérification humaine');w.geometry('660x400');w.transient(self);w.grab_set()
        verified=tk.BooleanVar(value=bool(r['checked']));ttk.Checkbutton(w,text='J’ai vérifié le message original sur sa page',variable=verified).pack(anchor='w',padx=12,pady=9)
        ttk.Label(w,text='Notes et observations (ne pas inventer de preuve) :').pack(anchor='w',padx=12)
        t=tk.Text(w,height=11,wrap='word');t.pack(fill='both',expand=True,padx=12,pady=6);t.insert('1.0',r['note'] or '')
        def save():
            db=Store(DB)
            try:db.annotate(r['id'],verified.get(),t.get('1.0','end-1c'),r['screenshot']);w.destroy();self.refresh()
            finally:db.conn.close()
        ttk.Button(w,text='Enregistrer',command=save).pack(pady=8)
    def manual(self):
        w=tk.Toplevel(self);w.title('Ajouter une preuve fournie');w.geometry('720x460');w.transient(self);w.grab_set()
        ttk.Label(w,text='URL de la publication originale (https://...)').pack(anchor='w',padx=12,pady=(10,0))
        url=tk.Entry(w);url.pack(fill='x',padx=12)
        ttk.Label(w,text='Auteur / pseudonyme public').pack(anchor='w',padx=12,pady=(10,0))
        author=tk.Entry(w);author.pack(fill='x',padx=12)
        ttk.Label(w,text='Texte affiché dans la publication (copié par toi)').pack(anchor='w',padx=12,pady=(10,0))
        txt=tk.Text(w,height=12);txt.pack(fill='both',expand=True,padx=12,pady=5)
        def save():
            u=canonical_url(url.get())
            if not u:messagebox.showerror('URL','Ajoute une URL HTTPS publique valide.',parent=w);return
            from engine import detect_platform
            db=Store(DB)
            try:db.add(Record(url=u,text=txt.get('1.0','end-1c'),author=author.get(),platform=detect_platform(u),source_kind='import'))
            finally:db.conn.close()
            w.destroy();self.refresh()
        ttk.Button(w,text='Ajouter',command=save).pack(pady=8)
    def preview_selected(self):
        r=self.selected()
        self.preview.config(state='normal');self.preview.delete('1.0','end')
        if r:self.preview.insert('1.0',f"{r['title']}\n{r['text']}\n\n{r['url']}\nTYPE : {r['verification']} | CATÉGORIE : {r['categories']}\nNOTES : {r['note']}")
        self.preview.config(state='disabled')
    def refresh(self):
        db=Store(DB)
        try:
            stats=db.summary();self.tally.config(text=f"{stats['total'] or 0} éléments conservés · {stats['pistes'] or 0} pistes linguistiques · {stats['verified'] or 0} vérifiés par toi · {stats['snippets'] or 0} extraits non vérifiés")
            if hasattr(self,'tree'):
                for child in self.tree.get_children():self.tree.delete(child)
                for r in db.rows(0,limit=3000):
                    title=(r['title'] or r['text'] or '')[:110].replace('\n',' ')
                    self.tree.insert('', 'end',iid=str(r['id']),values=(r['score'],r['platform'],r['verification'],title,r['url']))
        finally:db.conn.close()
    def report(self):
        db=Store(DB)
        try:path=export(db)
        except Exception as e:messagebox.showerror('Rapport',str(e));return
        finally:db.conn.close()
        webbrowser.open(path.resolve().as_uri())

if __name__=='__main__': App().mainloop()
