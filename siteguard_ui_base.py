"""SiteGuard desktop dashboard. Run: python app.py"""
import json
import os
from pathlib import Path
import queue
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import date
from PIL import Image, ImageTk
from safety.engine import Config, Runner
from safety.storage import Store, export_csv, export_pdf

BG, PANEL, TEXT, MUTED, ACCENT = '#0b1220','#142033','#e5edf7','#91a4bc','#38bdf8'

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('SiteGuard | Construction PPE Safety')
        self.geometry('1440x900')
        self.minsize(1100,720)
        self.configure(bg=BG)
        self.runner = None
        self.messages = queue.Queue()
        self.last_image = None
        self.last_metrics = None
        self.photo = None
        self.rows = []
        self.closing = False
        self.settings_file = Path.home()/'.siteguard_settings.json'
        self.style()
        header = tk.Frame(self,bg=BG)
        header.pack(fill='x',padx=24,pady=(18,12))
        tk.Label(header,text='SITEGUARD',font=('Segoe UI',24,'bold'),fg=TEXT,bg=BG).pack(side='left')
        tk.Label(header,text='  /  CONSTRUCTION SAFETY INTELLIGENCE',font=('Segoe UI',10),fg=MUTED,bg=BG).pack(side='left')
        self.badge = tk.Label(header,text='OFFLINE',fg=ACCENT,bg=PANEL,padx=18,pady=8)
        self.badge.pack(side='right')
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill='both',expand=True,padx=20,pady=(0,8))
        self.monitor = ttk.Frame(self.tabs)
        self.history = ttk.Frame(self.tabs)
        self.settings = ttk.Frame(self.tabs)
        self.guide = ttk.Frame(self.tabs)
        for name,page in [('Live monitoring',self.monitor),('Violation history',self.history),('Settings',self.settings),('Model setup',self.guide)]:
            self.tabs.add(page,text=name)
        self.vars = {}
        self.build_settings()
        self.load_settings()
        self.build_monitor()
        self.build_history()
        self.build_guide()
        self.status_text = tk.StringVar(value='Ready. Choose Settings to load best.pt, or run the synthetic demo.')
        tk.Label(self,textvariable=self.status_text,anchor='w',fg=MUTED,bg=BG,padx=24,pady=10).pack(fill='x')
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.after(80,self.poll)

    def style(self):
        s = ttk.Style(self)
        s.theme_use('clam')
        s.configure('.',background=BG,foreground=TEXT,font=('Segoe UI',10))
        s.configure('TFrame',background=BG)
        s.configure('TLabel',background=BG,foreground=TEXT)
        s.configure('TButton',padding=(14,9),background='#20344e',foreground=TEXT,borderwidth=0)
        s.map('TButton',background=[('active','#315274')])
        s.configure('Accent.TButton',background='#0369a1')
        s.configure('TNotebook',background=BG,borderwidth=0)
        s.configure('TNotebook.Tab',padding=(20,12),background=PANEL,foreground=MUTED)
        s.map('TNotebook.Tab',background=[('selected','#20344e')],foreground=[('selected',TEXT)])
        s.configure('TEntry',fieldbackground=PANEL,foreground=TEXT,insertcolor=TEXT,padding=7)
        s.configure('TCombobox',fieldbackground=PANEL,foreground=TEXT,arrowcolor=TEXT,padding=6)
        s.map('TCombobox',fieldbackground=[('readonly',PANEL)],foreground=[('readonly',TEXT)])
        s.configure('Treeview',background=PANEL,fieldbackground=PANEL,foreground=TEXT,rowheight=32,borderwidth=0)
        s.configure('Treeview.Heading',background='#20344e',foreground=TEXT,padding=8)
        s.map('Treeview',background=[('selected','#075985')])
        s.configure('TLabelframe',background=BG,bordercolor='#284059')
        s.configure('TLabelframe.Label',background=BG,foreground=MUTED)

    def build_settings(self):
        left = ttk.Frame(self.settings,padding=24)
        left.pack(side='left',fill='both',expand=True)
        right = ttk.Frame(self.settings,padding=24)
        right.pack(side='left',fill='both',expand=True)
        defaults = Config()
        fields = [
            ('mode','Input mode',['Demo','Image','Video','Webcam','IP Camera']),
            ('weights','Custom model (.pt)',None),('source','File / webcam index / RTSP URL',None),
            ('camera','Camera ID',None),('output','Results folder',None),('mapping','Optional class_map.json',None),
            ('tracker','Worker tracker',['bytetrack','botsort']),('device','Device',['auto','cpu','0','1']),
            ('confidence','Confidence threshold',None),('iou','IoU threshold',None),
            ('imgsz','Inference resolution (multiple of 32)',None),('stride','Process every Nth frame',None),
            ('fps','Live FPS limit / camera request',None),('confirm','Confirmation frames (1–5)',None)]
        for idx,(key,label,choices) in enumerate(fields):
            parent = left if idx<7 else right
            row = idx if idx<7 else idx-7
            ttk.Label(parent,text=label).grid(row=row*2,column=0,sticky='w',pady=(9,5),columnspan=2)
            var = tk.StringVar(value=str(getattr(defaults,key)))
            self.vars[key] = var
            if choices: widget = ttk.Combobox(parent,textvariable=var,values=choices,state='readonly')
            else: widget = ttk.Entry(parent,textvariable=var,show='*' if key=='source' else '')
            widget.grid(row=row*2+1,column=0,sticky='ew',pady=(0,4))
            parent.columnconfigure(0,weight=1)
            if key in ('weights','source','output','mapping'):
                ttk.Button(parent,text='Browse',command=lambda k=key:self.browse(k)).grid(row=row*2+1,column=1,padx=(8,0))
        self.vars['save_media'] = tk.BooleanVar(value=True)
        ttk.Checkbutton(right,text='Save annotated images / videos',variable=self.vars['save_media']).grid(row=15,column=0,sticky='w',pady=15)
        ttk.Label(left,text='Source is hidden to protect camera credentials.\nFor Webcam enter 0 (or another camera index).\nSettings apply when a new session starts.',foreground=MUTED).grid(row=15,column=0,columnspan=2,sticky='w',pady=15)
        ttk.Button(right,text='Save settings',command=self.save_settings).grid(row=16,column=0,sticky='w')

    def browse(self,key):
        if key=='output': path = filedialog.askdirectory()
        else:
            filters = [('All files','*.*')]
            if key=='weights': filters = [('PyTorch model','*.pt')]
            if key=='mapping': filters = [('JSON','*.json')]
            if key=='source': filters = [('Media','*.jpg *.jpeg *.png *.bmp *.webp *.mp4 *.avi *.mkv *.mov'),('All files','*.*')]
            path = filedialog.askopenfilename(filetypes=filters)
        if path:
            self.vars[key].set(path)
            if key=='source':
                self.vars['mode'].set('Image' if Path(path).suffix.lower() in ('.jpg','.jpeg','.png','.bmp','.webp') else 'Video')

    def build_monitor(self):
        toolbar = ttk.Frame(self.monitor,padding=(16,14))
        toolbar.pack(fill='x')
        self.start_btn = ttk.Button(toolbar,text='Start monitoring',style='Accent.TButton',command=self.start)
        self.start_btn.pack(side='left')
        self.stop_btn = ttk.Button(toolbar,text='Stop',command=self.stop,state='disabled')
        self.stop_btn.pack(side='left',padx=8)
        ttk.Button(toolbar,text='Save current frame',command=self.save_frame).pack(side='left')
        self.scope = tk.StringVar(value='Current frame')
        cb = ttk.Combobox(toolbar,textvariable=self.scope,values=['Current frame','Session latest'],state='readonly',width=18)
        cb.pack(side='right')
        cb.bind('<<ComboboxSelected>>',lambda e:self.update_metrics())
        ttk.Label(toolbar,text='Statistics: ').pack(side='right')
        cards = tk.Frame(self.monitor,bg=BG)
        cards.pack(fill='x',padx=16,pady=(0,12))
        self.cards = {}
        for i,(key,title,color) in enumerate([('total','WORKERS',TEXT),('safe','COMPLIANT','#34d399'),('unsafe','VIOLATIONS','#fb7185'),('unknown','UNKNOWN','#fbbf24'),('compliance','COMPLIANCE',ACCENT)]):
            card = tk.Frame(cards,bg=PANEL,padx=18,pady=12)
            card.grid(row=0,column=i,sticky='ew',padx=(0,8))
            cards.columnconfigure(i,weight=1)
            tk.Label(card,text=title,fg=MUTED,bg=PANEL,font=('Segoe UI',9)).pack(anchor='w')
            v = tk.StringVar(value='0% ' if key=='compliance' else '0')
            self.cards[key] = v
            tk.Label(card,textvariable=v,fg=color,bg=PANEL,font=('Segoe UI',26,'bold')).pack(anchor='w')
        center = ttk.Frame(self.monitor)
        center.pack(fill='both',expand=True,padx=16)
        self.canvas = tk.Canvas(center,bg='#060c16',highlightthickness=0)
        self.canvas.pack(side='left',fill='both',expand=True)
        self.canvas.bind('<Configure>',lambda e:self.paint())
        self.side_text = tk.StringVar(value='PPE BREAKDOWN\n\nStart a session to see detections.\n\nGreen: compliant\nRed: confirmed violation\nAmber: unknown / pending')
        tk.Label(center,textvariable=self.side_text,justify='left',anchor='nw',bg=PANEL,fg=TEXT,
                 font=('Segoe UI',11),padx=20,pady=24,width=27).pack(side='right',fill='y',padx=(12,0))
        self.scope_note = tk.StringVar(value='Session IDs are tracking estimates. Unknown PPE never counts as compliant.')
        ttk.Label(self.monitor,textvariable=self.scope_note,foreground=MUTED,padding=16).pack(fill='x')

    def build_history(self):
        top = ttk.Frame(self.history,padding=16)
        top.pack(fill='x')
        self.filter_day = tk.StringVar(value=date.today().isoformat())
        self.filter_camera = tk.StringVar()
        self.demo_history = tk.BooleanVar(value=False)
        ttk.Label(top,text='Date (YYYY-MM-DD):').pack(side='left')
        ttk.Entry(top,textvariable=self.filter_day,width=13).pack(side='left',padx=8)
        ttk.Label(top,text='Camera:').pack(side='left')
        ttk.Entry(top,textvariable=self.filter_camera,width=12).pack(side='left',padx=8)
        ttk.Checkbutton(top,text='Demo records',variable=self.demo_history).pack(side='left',padx=10)
        ttk.Button(top,text='Search',command=self.refresh_history).pack(side='left')
        actions = ttk.Frame(self.history,padding=(16,0,16,12))
        actions.pack(fill='x')
        for title,command in [('Export filtered CSV',self.csv),('Daily PDF report',self.pdf),('Open evidence',self.open_evidence),('Daily summary',self.daily)]:
            ttk.Button(actions,text=title,command=command).pack(side='left',padx=(0,8))
        frame = ttk.Frame(self.history)
        frame.pack(fill='both',expand=True,padx=16,pady=(0,12))
        columns = ['time','session','worker','camera','helmet','jacket','violation','confidence','media']
        self.table = ttk.Treeview(frame,columns=columns,show='headings')
        for col in columns:
            self.table.heading(col,text=col.title())
            self.table.column(col,width=170 if col in ('time','violation') else 95,minwidth=70)
        sy = ttk.Scrollbar(frame,orient='vertical',command=self.table.yview)
        sx = ttk.Scrollbar(frame,orient='horizontal',command=self.table.xview)
        self.table.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
        self.table.grid(row=0,column=0,sticky='nsew'); sy.grid(row=0,column=1,sticky='ns'); sx.grid(row=1,column=0,sticky='ew')
        frame.rowconfigure(0,weight=1); frame.columnconfigure(0,weight=1)
        self.table.bind('<Double-1>',lambda e:self.open_evidence())
        ttk.Label(self.history,text='Blank date/camera shows all matching records. Daily reports use the chosen date and all cameras.',foreground=MUTED,padding=16).pack(fill='x')

    def build_guide(self):
        box = tk.Text(self.guide,wrap='word',bg=PANEL,fg=TEXT,font=('Segoe UI',12),padx=30,pady=25,borderwidth=0)
        box.pack(fill='both',expand=True,padx=20,pady=20)
        box.insert('1.0','''LOAD YOUR TRAINED YOLO26x MODEL

1. Train your model separately in VS Code. No training runs inside this application.
2. In Settings, select your custom best.pt weights.
3. Use these class names: person, helmet, no_helmet, vest, no_vest.
   Common alternatives such as Hardhat, NO-Hardhat, Safety Vest and NO-Safety Vest are recognized.
4. Person labels cover the full worker. Helmet/no_helmet labels cover the head region.
   Vest/no_vest labels cover the torso region. Whole-person negative PPE boxes do not fit this association method.
5. For other names, supply class_map.json with the correct integer class IDs (see included example).
6. Choose Image, Video, Webcam, or IP Camera. Choose the file, camera index, or stream URL.
7. Start monitoring. Use Stop before changing source or model.

ASSESSMENT RULES

SAFE requires both helmet and vest confirmed. An explicit no_helmet or no_vest detection produces a violation after confirmation. Occluded, small, contradictory or ambiguous PPE remains UNKNOWN; failure to detect an item alone does not prove it is absent. Demo uses synthetic illustrations and is stored separately.

COUNTING AND EVENTS

Current frame counts only currently tracked workers. Session latest counts every ID seen in this run using its last observed PPE state. A worker ID is not an identity: exits, occlusions and re-entry may cause new IDs. No cross-camera identity deduplication is claimed. Each continuous violation creates one event. Confirmed safe recovery rearms the next event; unknown observations do not. Helmet/jacket event subtotals describe the episode at its first confirmation.

OUTPUTS

Evidence JPGs, annotated media and SQLite records go to the Results folder. Video positions are stored separately from the analysis timestamp. Live MP4 is an analysis recording, not a guaranteed real-time synchronized recording; frame_timestamps.csv contains actual timestamps. No audio is saved. The daily report aggregates session snapshots recorded that day; a session spanning midnight can appear on both days.

PERFORMANCE

Auto selects CUDA GPU when available, otherwise CPU. YOLO26x at high resolution needs substantial compute. No FPS/accuracy is promised without testing your hardware and data. Frame skipping can reduce tracking quality. BoT-SORT uses motion association here; appearance ReID is disabled. Test on representative footage before using operationally.
''')
        box.configure(state='disabled')

    def config(self):
        values = {k:v.get() for k,v in self.vars.items()}
        for k in ('imgsz','stride','fps','confirm'): values[k] = int(values[k])
        for k in ('confidence','iou'): values[k] = float(values[k])
        if not .05<=values['confidence']<=.95 or not .1<=values['iou']<=.95: raise ValueError('Confidence: 0.05–0.95. IoU: 0.1–0.95.')
        if not 320<=values['imgsz']<=2560 or values['imgsz']%32: raise ValueError('Resolution must be 320–2560 and a multiple of 32.')
        if not 1<=values['stride']<=30 or not 1<=values['fps']<=120 or not 1<=values['confirm']<=5: raise ValueError('Stride: 1–30, FPS: 1–120, confirmation: 1–5.')
        if not values['camera'].strip(): raise ValueError('Enter a camera ID.')
        if not values['output'].strip(): raise ValueError('Choose a results folder.')
        return Config(**values)

    def start(self):
        if self.runner is not None: return
        try:
            cfg = self.config()
            if cfg.mode!='Demo':
                if not Path(cfg.weights).is_file(): raise ValueError('Select your trained best.pt model in Settings.')
                if cfg.mode in ('Image','Video') and not Path(cfg.source).is_file(): raise ValueError('Select an image or video file.')
                if cfg.mode=='Webcam': int(cfg.source or '0')
                if cfg.mode=='IP Camera' and not cfg.source.startswith(('rtsp://','rtsps://','http://','https://')): raise ValueError('Enter an RTSP or HTTP camera URL.')
            self.runner = Runner(cfg,self.messages)
            self.runner.start()
            self.start_btn.configure(state='disabled'); self.stop_btn.configure(state='normal')
            self.badge.configure(text='DEMO' if cfg.mode=='Demo' else 'MONITORING')
            self.status_text.set('Starting session...')
            self.tabs.select(self.monitor)
        except Exception as e: messagebox.showerror('Settings',str(e))

    def stop(self):
        if self.runner:
            self.runner.stop()
            self.status_text.set('Stopping after the current inference / capture operation...')
            self.stop_btn.configure(state='disabled')

    def poll(self):
        if self.runner:
            frame = self.runner.take_frame()
            if frame:
                self.last_image,self.last_metrics,fps = frame
                self.paint(); self.update_metrics(fps)
        while True:
            try: kind,value = self.messages.get_nowait()
            except queue.Empty: break
            if kind in ('status','event'): self.status_text.set(value)
            elif kind=='error':
                self.status_text.set('Session failed: '+value)
                if not self.closing: messagebox.showerror('Monitoring error',value)
            elif kind=='done':
                # Only release the thread once its finally block has fully finished.
                self.after(100,self.finish)
        if self.closing and self.runner is None:
            self.destroy(); return
        self.after(80,self.poll)

    def finish(self):
        if self.runner and self.runner.is_alive():
            self.after(100,self.finish); return
        # Consume final image before discarding the runner (important for still images).
        if self.runner:
            frame = self.runner.take_frame()
            if frame:
                self.last_image,self.last_metrics,fps = frame
                self.paint(); self.update_metrics(fps)
        self.runner = None
        self.start_btn.configure(state='normal'); self.stop_btn.configure(state='disabled')
        self.badge.configure(text='OFFLINE')

    def paint(self):
        w,h = self.canvas.winfo_width(),self.canvas.winfo_height()
        self.canvas.delete('all')
        if self.last_image:
            preview = self.last_image.copy()
            preview.thumbnail((max(1,w),max(1,h)),Image.Resampling.LANCZOS)
            self.photo = ImageTk.PhotoImage(preview)
            self.canvas.create_image(w/2,h/2,image=self.photo)
        else:
            self.canvas.create_text(w/2,h/2,text='YOUR SITE. ONE CLEAR VIEW.\n\nLoad your model or start the synthetic demo.',fill=MUTED,font=('Segoe UI',17),justify='center')

    def update_metrics(self,fps=None):
        if not self.last_metrics: return
        m = self.last_metrics
        counts = m['current' if self.scope.get()=='Current frame' else 'session']
        for key,var in self.cards.items(): var.set(str(counts[key])+('%' if key=='compliance' else ''))
        self.side_text.set(f"PPE BREAKDOWN\n\nHelmet present       {counts['helmet']}\nHelmet missing       {counts['no_helmet']}\nHelmet unknown       {counts['helmet_unknown']}\n\nJacket present        {counts['vest']}\nJacket missing        {counts['no_vest']}\nJacket unknown        {counts['vest_unknown']}\n\nSESSION TOTALS\n\nUnique track IDs      {m['session']['total']}\nEver unsafe IDs       {m['ever_unsafe']}\nViolation episodes    {m['events']}\nHelmet episodes       {m['helmet_events']}\nJacket episodes       {m['vest_events']}\nBoth missing          {m['multiple_events']}"+(f'\n\nProcessing FPS: {fps:.1f}' if fps else ''))
        self.scope_note.set('Current frame: currently tracked workers only.' if self.scope.get()=='Current frame' else 'Session latest: all IDs seen, using each ID’s last observation. IDs may repeat across sessions.')

    def save_frame(self):
        if self.last_image is None: return
        path = filedialog.asksaveasfilename(defaultextension='.jpg',filetypes=[('JPEG','*.jpg')])
        if path:
            try: self.last_image.save(path,quality=95)
            except OSError as e: messagebox.showerror('Save frame',str(e))

    def store(self):
        return Store(Path(self.vars['output'].get())/('demo' if self.demo_history.get() else 'records'))

    def validated_day(self,required=False):
        day = self.filter_day.get().strip()
        if required and not day: raise ValueError('Enter a date for the daily report.')
        if day: date.fromisoformat(day)
        return day

    def refresh_history(self):
        try:
            day = self.validated_day()
            store = self.store()
            try: self.rows = store.events(day,self.filter_camera.get().strip())
            finally: store.close()
            self.table.delete(*self.table.get_children())
            for i,r in enumerate(self.rows):
                self.table.insert('', 'end',iid=str(i),values=[r['recorded_at'],r['session'][:8],f"{r['worker']:03d}",r['camera'],r['helmet'],r['vest'],r['violation'],f"{r['confidence']:.2f}",f"{r['media_seconds']:.2f}s"])
            self.status_text.set(f'{len(self.rows)} matching violation episodes.')
            return True
        except Exception as e:
            messagebox.showerror('History',str(e)); return False

    def csv(self):
        if not self.refresh_history(): return
        path = filedialog.asksaveasfilename(defaultextension='.csv',initialfile='siteguard_violations.csv')
        if path:
            try: export_csv(path,self.rows)
            except Exception as e: messagebox.showerror('CSV export',str(e))

    def pdf(self):
        try:
            day = self.validated_day(True)
            store = self.store()
            try: rows,summary = store.events(day),store.daily(day)
            finally: store.close()
            path = filedialog.asksaveasfilename(defaultextension='.pdf',initialfile=f'safety_{day}.pdf')
            if path: export_pdf(path,rows,summary)
        except Exception as e: messagebox.showerror('PDF report',str(e))

    def daily(self):
        try:
            store = self.store()
            try: summary = store.daily(self.validated_day(True))
            finally: store.close()
            messagebox.showinfo('Daily summary','\n'.join(f'{k.replace("_"," ").title()}: {v}' for k,v in summary.items())+'\n\nTrack IDs are not deduplicated across sessions or cameras.')
        except Exception as e: messagebox.showerror('Daily summary',str(e))

    def open_evidence(self):
        selected = self.table.selection()
        if not selected: return
        path = Path(self.rows[int(selected[0])]['evidence'])
        if not path.is_file(): messagebox.showwarning('Evidence','Evidence file no longer exists.'); return
        popup = tk.Toplevel(self); popup.title('Violation evidence')
        image = Image.open(path); image.thumbnail((1100,750))
        photo = ImageTk.PhotoImage(image)
        label = tk.Label(popup,image=photo,bg=BG); label.image = photo; label.pack()

    def save_settings(self):
        try:
            cfg = self.config()
            data = vars(cfg).copy()
            data.pop('source',None)  # Never store camera URL credentials.
            self.settings_file.write_text(json.dumps(data,indent=2),encoding='utf-8')
            self.status_text.set('Settings saved. Source addresses are not saved.')
        except Exception as e: messagebox.showerror('Settings',str(e))

    def load_settings(self):
        try:
            data = json.loads(self.settings_file.read_text(encoding='utf-8'))
            for key,value in data.items():
                if key in self.vars and key!='source': self.vars[key].set(value)
        except (OSError,ValueError): pass

    def close(self):
        self.closing = True
        if self.runner: self.stop()
        else: self.destroy()

if __name__=='__main__':
    App().mainloop()
