"""L&T SiteGuard desktop UI. Launch with: .venv\\Scripts\\python.exe app_lnt.py

Uses the existing app.py callbacks and safety/ engine. No training imports or jobs
run in this entry point. The three reference-inspired visual components below
use Tk/Pillow only; no new runtime dependencies are required.
"""
from collections import deque
from datetime import datetime, date
from pathlib import Path
import queue
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageDraw, ImageFilter, ImageTk

from siteguard_ui_base import App as OriginalApp
from siteguard_excel import read_report_data, export_excel

BG = '#f1f2fb'
WHITE = '#ffffff'
INK = '#172b49'
MUTED = '#7c889f'
LINE = '#e8edf6'
BLUE = '#5265ed'
CYAN = '#20c6df'
PURPLE = '#8361ed'
GREEN = '#15a789'
RED = '#e65d83'
AMBER = '#d29429'
ASSETS = Path(__file__).resolve().parent / 'assets'
FONT = 'Segoe UI'


def label(parent, text='', size=10, color=INK, bold=False, bg=WHITE, **kwargs):
    return tk.Label(parent, text=text, font=(FONT, size, 'bold' if bold else 'normal'),
                    bg=bg, fg=color, bd=0, **kwargs)


class SoftCard(tk.Canvas):
    """A resizable rounded white panel with a soft, cached raster shadow."""
    def __init__(self, parent, padding=20, color=WHITE, **kwargs):
        super().__init__(parent, bg=BG, highlightthickness=0, bd=0, **kwargs)
        self.fill_color, self.padding = color, padding
        self.body = tk.Frame(self, bg=color)
        self._window = self.create_window(12+padding, 10+padding, anchor='nw', window=self.body)
        self._photo = None
        self._size = None
        self.bind('<Configure>', self._layout)

    def _layout(self, event):
        w, h = max(1,event.width), max(1,event.height)
        if w<40 or h<40: return
        if self._size == (w,h): return
        self._size = (w,h)
        image = Image.new('RGBA',(w,h),BG)
        shadow = Image.new('RGBA',(w,h))
        ImageDraw.Draw(shadow).rounded_rectangle((12,15,w-12,h-8),radius=24,fill=(79,83,157,21))
        image = Image.alpha_composite(image,shadow.filter(ImageFilter.GaussianBlur(8)))
        ImageDraw.Draw(image).rounded_rectangle((9,6,w-10,h-15),radius=22,fill=self.fill_color)
        self._photo = ImageTk.PhotoImage(image)
        self.delete('card')
        self.create_image(0,0,anchor='nw',image=self._photo,tags='card')
        self.tag_lower('card')
        self.itemconfigure(self._window,width=max(1,w-24-2*self.padding),
                           height=max(1,h-31-2*self.padding))


class GradientButton(tk.Canvas):
    """Keyboard-accessible cyan/violet action button without a theme install."""
    def __init__(self,parent,text,command,width=166,height=43):
        super().__init__(parent,width=width,height=height,bg=WHITE,bd=0,
                         highlightthickness=0,takefocus=1,cursor='hand2')
        self.text,self.command,self.enabled = text,command,True
        self._photo = None
        self.bind('<ButtonRelease-1>',self._invoke)
        self.bind('<Return>',self._invoke)
        self.bind('<space>',self._invoke)
        self.bind('<FocusIn>',lambda e:self._draw(True))
        self.bind('<FocusOut>',lambda e:self._draw())
        self.bind('<Configure>',lambda e:self._draw())
        self._draw()

    def _invoke(self,event=None):
        if self.enabled: self.command()

    def configure(self,cnf=None,**kwargs):
        state = kwargs.pop('state',None)
        if state is not None:
            self.enabled = state != 'disabled'
            self._draw()
        return super().configure(cnf,**kwargs)

    def _draw(self,focused=False):
        w,h = int(self.cget('width')),int(self.cget('height'))
        image = Image.new('RGBA',(w,h))
        draw = ImageDraw.Draw(image)
        for x in range(w):
            t=x/max(1,w-1)
            a,b=((32,198,223),(107,79,241)) if self.enabled else ((184,197,215),(184,197,215))
            draw.line((x,0,x,h),fill=tuple(int(a[i]*(1-t)+b[i]*t) for i in range(3)))
        mask=Image.new('L',(w,h))
        ImageDraw.Draw(mask).rounded_rectangle((1,1,w-2,h-2),radius=14,fill=255)
        image.putalpha(mask)
        self._photo=ImageTk.PhotoImage(image)
        self.delete('all')
        self.create_image(0,0,anchor='nw',image=self._photo)
        self.create_text(w/2,h/2,text=self.text,fill=WHITE,font=(FONT,10,'bold'))
        if focused: self.create_rectangle(3,3,w-4,h-4,outline=INK,dash=(3,3))


class Pages:
    """Notebook-compatible select() used by the original monitoring callbacks."""
    def __init__(self,app): self.app=app
    def select(self,page): self.app.show_page(page)


class App(OriginalApp):
    def __init__(self):
        tk.Tk.__init__(self)
        self.title('L&T SiteGuard | Construction Safety Intelligence')
        self.geometry('1480x940')
        self.minsize(1120,760)
        self.configure(bg=BG)
        self.runner=None
        self.messages=queue.Queue()
        self.last_image=self.last_metrics=self.photo=None
        self.rows=[]
        self.closing=False
        self.settings_file=Path.home()/'.siteguard_settings.json'
        self.vars={}
        self.cards={}
        self.card_titles={}
        self._logos=[]
        if (ASSETS/'lnt_symbol.png').is_file():
            with Image.open(ASSETS/'lnt_symbol.png') as image:
                icon=image.copy()
            icon.thumbnail((64,64),Image.Resampling.LANCZOS)
            self._window_icon=ImageTk.PhotoImage(icon)
            self.iconphoto(True,self._window_icon)
        self._activity=deque(maxlen=6)
        self._trend=deque(maxlen=75)
        self._last_sample=0.0
        self._last_fps=None
        self._page_info={}
        self.status_text=tk.StringVar(value='Ready. Start the demo or select your trained model in Settings.')
        self.style()
        self._build_shell()
        self.build_settings()
        self.load_settings()
        if not self.settings_file.exists():
            self.vars['device'].set('cpu')
            self.vars['imgsz'].set('640')
        self.build_monitor()
        self.build_history()
        self.build_guide()
        self.tabs=Pages(self)
        self.show_page(self.monitor)
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.after(80,self.poll)
        self.after(250,self._clock)

    def style(self):
        s=ttk.Style(self)
        s.theme_use('clam')
        s.configure('.',font=(FONT,10),background=WHITE,foreground=INK)
        s.configure('TFrame',background=WHITE)
        s.configure('TLabel',background=WHITE,foreground=INK)
        s.configure('TButton',background='#eef0fd',foreground=BLUE,padding=(13,10),borderwidth=0)
        s.map('TButton',background=[('active','#e1e6ff'),('disabled','#f1f3f8')],
              foreground=[('disabled','#a0abc0')])
        s.configure('TEntry',fieldbackground='#f6f8fd',foreground=INK,bordercolor=LINE,
                    lightcolor=LINE,darkcolor=LINE,padding=8,insertcolor=INK)
        s.configure('TCombobox',fieldbackground='#f6f8fd',background='#eef1fa',foreground=INK,
                    arrowcolor=BLUE,bordercolor=LINE,padding=7)
        s.map('TCombobox',fieldbackground=[('readonly','#f6f8fd')],foreground=[('readonly',INK)])
        s.configure('TCheckbutton',background=WHITE,foreground=INK,padding=5)
        s.map('TCheckbutton',background=[('active',WHITE)])
        s.configure('Treeview',background=WHITE,fieldbackground=WHITE,foreground=INK,
                    rowheight=39,borderwidth=0,font=(FONT,10))
        s.configure('Treeview.Heading',background='#f3f5fc',foreground=MUTED,padding=12,
                    font=(FONT,9,'bold'),relief='flat')
        s.map('Treeview',background=[('selected','#e7edff')],foreground=[('selected',INK)])
        s.configure('Vertical.TScrollbar',background='#d8def0',troughcolor='#f5f7fc',borderwidth=0,arrowsize=12)
        s.configure('Horizontal.TScrollbar',background='#d8def0',troughcolor='#f5f7fc',borderwidth=0,arrowsize=12)

    def _logo(self,parent,filename,size):
        path=ASSETS/filename
        if not path.exists(): return None
        with Image.open(path) as raw:
            image=raw.copy()
        image.thumbnail(size,Image.Resampling.LANCZOS)
        photo=ImageTk.PhotoImage(image)
        self._logos.append(photo)
        tk.Label(parent,image=photo,bg=WHITE,bd=0).pack()
        return photo

    def _build_shell(self):
        sidebar=tk.Frame(self,bg=WHITE,width=220)
        sidebar.pack(side='left',fill='y')
        sidebar.pack_propagate(False)
        brand=tk.Frame(sidebar,bg=WHITE)
        brand.pack(fill='x',padx=20,pady=(28,0))
        self._logo(brand,'lnt_symbol.png',(58,58))
        label(brand,'L&T CONSTRUCTION',11,bold=True).pack(pady=(12,2))
        label(brand,'SITE SAFETY INTELLIGENCE',7,color=MUTED).pack()
        tk.Frame(sidebar,bg=LINE,height=1).pack(fill='x',padx=24,pady=25)
        label(sidebar,'WORKSPACE',8,color=MUTED,bg=WHITE,anchor='w').pack(fill='x',padx=28,pady=(0,10))
        self.content=tk.Frame(self,bg=BG)
        self.content.pack(side='left',fill='both',expand=True)
        top=tk.Frame(self.content,bg=BG)
        top.pack(fill='x',padx=27,pady=(23,8))
        self.breadcrumb=label(top,'Workspace  /  Live monitoring',9,color=MUTED,bg=BG)
        self.breadcrumb.pack(side='left')
        self.clock_text=tk.StringVar()
        label(top,textvariable=self.clock_text,size=9,color=MUTED,bg=BG).pack(side='right')
        self.page_holder=tk.Frame(self.content,bg=BG)
        self.page_holder.pack(fill='both',expand=True,padx=18)
        for attr,title,icon in [('monitor','Live monitoring','01'),('history','Violation history','02'),
                                ('settings','Settings & sources','03'),('guide','Model setup','04')]:
            page=tk.Frame(self.page_holder,bg=BG)
            setattr(self,attr,page)
            btn=tk.Button(sidebar,text=f'{icon}    {title}',anchor='w',relief='flat',bd=0,
                          font=(FONT,10),bg=WHITE,fg=MUTED,activebackground='#eef0ff',
                          activeforeground=BLUE,cursor='hand2',padx=18,pady=13,
                          command=lambda p=page:self.show_page(p))
            btn.pack(fill='x',padx=15,pady=4)
            self._page_info[page]=(title,btn)
        foot=tk.Frame(sidebar,bg=WHITE)
        foot.pack(side='bottom',fill='x',padx=20,pady=24)
        self._logo(foot,'lnt_construction.png',(174,85))
        label(foot,'SITEGUARD',13,bold=True).pack(pady=(16,3))
        label(foot,'Worker & PPE monitoring',8,color=MUTED).pack()
        label(foot,'Desktop edition  /  v2.0',8,color=MUTED).pack(pady=(3,0))
        status=tk.Frame(self.content,bg=BG)
        status.pack(fill='x',padx=28,pady=(0,12))
        label(status,textvariable=self.status_text,size=9,color=MUTED,bg=BG,
              anchor='w',wraplength=970,justify='left').pack(fill='x')

    def show_page(self,page):
        for frame,(title,btn) in self._page_info.items():
            frame.pack_forget()
            selected=frame==page
            btn.configure(bg='#edf0ff' if selected else WHITE,fg=BLUE if selected else MUTED,
                          font=(FONT,10,'bold' if selected else 'normal'))
        page.pack(fill='both',expand=True)
        self.breadcrumb.configure(text='Workspace  /  '+self._page_info[page][0])

    def _heading(self,parent,title,subtitle):
        frame=tk.Frame(parent,bg=BG)
        frame.pack(fill='x',padx=12,pady=(9,8))
        label(frame,title,24,bold=True,bg=BG).pack(anchor='w')
        label(frame,subtitle,10,color=MUTED,bg=BG).pack(anchor='w',pady=(4,0))
        return frame

    def build_monitor(self):
        outer=self.monitor
        viewport=tk.Canvas(outer,bg=BG,highlightthickness=0)
        viewport.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(outer,orient='vertical',command=viewport.yview)
        scroll.pack(side='right',fill='y')
        viewport.configure(yscrollcommand=scroll.set)
        body=tk.Frame(viewport,bg=BG)
        window=viewport.create_window(0,0,window=body,anchor='nw')
        def fit(event):
            viewport.itemconfigure(window,width=event.width,height=max(940,event.height))
            viewport.configure(scrollregion=(0,0,event.width,max(940,event.height)))
        viewport.bind('<Configure>',fit)
        self.monitor=body
        heading=self._heading(self.monitor,'A clearer view. A safer site.',
                              'Workers, protective equipment and safety observations in one workspace.')
        self.badge=label(heading,'OFFLINE',9,color=BLUE,bold=True,bg='#e8edff',padx=14,pady=7)
        self.badge.place(relx=1.0,x=-3,y=5,anchor='ne')
        metrics=tk.Frame(self.monitor,bg=BG,height=124)
        metrics.pack(fill='x')
        for i,(key,title,color,icon) in enumerate([
                ('total','WORKERS IN VIEW',BLUE,'01'),('safe','PPE COMPLIANT',GREEN,'02'),
                ('unsafe','PPE VIOLATIONS',RED,'03'),('unknown','NEEDS REVIEW',AMBER,'04')]):
            metrics.columnconfigure(i,weight=1,uniform='metrics')
            card=SoftCard(metrics,height=124,padding=12)
            card.grid(row=0,column=i,sticky='ew')
            title_var=tk.StringVar(value=title)
            self.card_titles[key]=title_var
            label(card.body,textvariable=title_var,size=8,color=MUTED,bold=True).pack(anchor='w')
            value=tk.StringVar(value='—')
            self.cards[key]=value
            label(card.body,textvariable=value,size=27,color=color,bold=True).pack(anchor='w',pady=(3,0))
        tools=SoftCard(self.monitor,height=104,padding=13)
        tools.pack(fill='x')
        self.start_btn=GradientButton(tools.body,'Start monitoring',self.start)
        self.start_btn.pack(side='left')
        self.stop_btn=ttk.Button(tools.body,text='Stop',command=self.stop,state='disabled')
        self.stop_btn.pack(side='left',padx=9)
        ttk.Button(tools.body,text='Capture',command=self.save_frame).pack(side='left')
        ttk.Button(tools.body,text='Export Excel',command=lambda:self.excel(current=True)).pack(side='left',padx=(8,0))
        self.scope=tk.StringVar(value='Current frame')
        cb=ttk.Combobox(tools.body,textvariable=self.scope,values=['Current frame','Session latest'],
                        state='readonly',width=13)
        cb.pack(side='right')
        cb.bind('<<ComboboxSelected>>',lambda e:self.update_metrics())
        self.mode_select=ttk.Combobox(tools.body,textvariable=self.vars['mode'],
                       values=['Demo','Image','Video','Webcam','IP Camera'],state='readonly',width=10)
        self.mode_select.pack(side='right',padx=10)
        self.mode_select.bind('<<ComboboxSelected>>',lambda e:self._mode_hint())
        center=tk.Frame(self.monitor,bg=BG)
        center.pack(fill='both',expand=True)
        center.columnconfigure(0,weight=1)
        center.columnconfigure(1,minsize=304)
        center.rowconfigure(0,weight=1)
        video=SoftCard(center,padding=16)
        video.grid(row=0,column=0,sticky='nsew')
        titlebar=tk.Frame(video.body,bg=WHITE)
        titlebar.pack(fill='x',pady=(0,10))
        label(titlebar,'Live site view',12,bold=True).pack(side='left')
        self.feed_caption=tk.StringVar(value='CAM-01  /  Awaiting source')
        label(titlebar,textvariable=self.feed_caption,size=8,color=MUTED).pack(side='right')
        self.canvas=tk.Canvas(video.body,bg='#f5f7fd',bd=0,highlightthickness=0)
        self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>',lambda e:self.paint())
        legend=tk.Frame(video.body,bg=WHITE)
        legend.pack(fill='x',pady=(10,0))
        for text,color in [('● Compliant',GREEN),('● Violation',RED),('● Unknown',AMBER)]:
            label(legend,text,8,color=color).pack(side='left',padx=(0,15))
        self.fps_text=tk.StringVar(value='No active session')
        label(legend,textvariable=self.fps_text,size=8,color=MUTED).pack(side='right')
        right=tk.Frame(center,bg=BG,width=304)
        right.grid(row=0,column=1,sticky='nsew')
        ring_card=SoftCard(right,height=208,padding=12)
        ring_card.pack(fill='x')
        label(ring_card.body,'PPE compliance',12,bold=True).pack(anchor='w')
        self.ring=tk.Canvas(ring_card.body,bg=WHITE,height=148,highlightthickness=0)
        self.ring.pack(fill='x',expand=True)
        self.ring.bind('<Configure>',lambda e:self.draw_ring())
        self.ring_note=tk.StringVar(value='Start monitoring to calculate')
        label(ring_card.body,textvariable=self.ring_note,size=8,color=MUTED).pack()
        ppe=SoftCard(right,padding=12,height=220)
        ppe.pack(fill='both',expand=True)
        label(ppe.body,'Equipment check',12,bold=True).pack(anchor='w',pady=(0,13))
        self.ppe_values={}
        for title,key,color in [('Helmet present','helmet',GREEN),('Helmet missing','no_helmet',RED),
                                ('Jacket present','vest',BLUE),('Jacket missing','no_vest',RED)]:
            row=tk.Frame(ppe.body,bg=WHITE)
            row.pack(fill='x',pady=4)
            label(row,title,9,color=MUTED).pack(side='left')
            var=tk.StringVar(value='—')
            self.ppe_values[key]=var
            label(row,textvariable=var,size=11,color=color,bold=True).pack(side='right')
        self.unknown_note=tk.StringVar(value='Unknown PPE is shown separately.')
        label(ppe.body,textvariable=self.unknown_note,size=8,color=MUTED,anchor='w',justify='left',
              wraplength=235).pack(anchor='w',pady=(8,0))
        bottom=tk.Frame(self.monitor,bg=BG,height=170)
        bottom.pack(fill='x')
        bottom.columnconfigure(0,weight=1,uniform='lower')
        bottom.columnconfigure(1,weight=1,uniform='lower')
        trend=SoftCard(bottom,height=170,padding=15)
        trend.grid(row=0,column=0,sticky='ew')
        title=tk.Frame(trend.body,bg=WHITE)
        title.pack(fill='x')
        label(title,'Compliance trend',11,bold=True).pack(side='left')
        label(title,'RECENT SESSION SAMPLES',7,color=MUTED).pack(side='right')
        self.chart=tk.Canvas(trend.body,bg=WHITE,height=74,highlightthickness=0)
        self.chart.pack(fill='both',expand=True,pady=(6,0))
        self.chart.bind('<Configure>',lambda e:self.draw_trend())
        activity=SoftCard(bottom,height=170,padding=15)
        activity.grid(row=0,column=1,sticky='ew')
        label(activity.body,'Recent activity',11,bold=True).pack(anchor='w')
        self.activity_text=tk.StringVar(value='No events yet. Monitoring events appear here.')
        label(activity.body,textvariable=self.activity_text,size=9,color=MUTED,justify='left',
              anchor='nw',wraplength=460).pack(fill='both',expand=True,pady=(10,0))
        self.scope_note=tk.StringVar(value='Counts are tracked IDs within one session. Unknown PPE is never counted as compliant.')
        label(self.monitor,textvariable=self.scope_note,size=8,color=MUTED,bg=BG,anchor='w',
              wraplength=980,justify='left').pack(fill='x',padx=14,pady=(0,5))
        def wheel(event):
            step=(-1 if event.num==4 else 1) if event.num in (4,5) else -int(event.delta/120)
            viewport.yview_scroll(step,'units')
        def bind_wheel(widget):
            if not isinstance(widget,ttk.Combobox):
                widget.bind('<MouseWheel>',wheel,add='+')
                widget.bind('<Button-4>',wheel,add='+')
                widget.bind('<Button-5>',wheel,add='+')
            for child in widget.winfo_children(): bind_wheel(child)
        bind_wheel(body)
        self.monitor=outer

    def _mode_hint(self):
        mode=self.vars['mode'].get()
        if mode in ('Image','Video'):
            self.browse('source')
        elif mode=='Webcam':
            self.vars['source'].set('0')
        elif mode=='IP Camera':
            self.show_page(self.settings)
            self.status_text.set('Enter the camera RTSP / HTTP address in Source, then start monitoring.')
        self.feed_caption.set(f"{self.vars['camera'].get()}  /  {self.vars['mode'].get()}")

    def build_settings(self):
        self._heading(self.settings,'Make this workspace yours.',
                      'Connect a camera, choose trained weights and tune your monitoring session.')
        card=SoftCard(self.settings,padding=20)
        card.pack(fill='both',expand=True)
        scroll=tk.Canvas(card.body,bg=WHITE,highlightthickness=0)
        scroll.pack(side='left',fill='both',expand=True)
        bar=ttk.Scrollbar(card.body,orient='vertical',command=scroll.yview)
        bar.pack(side='right',fill='y')
        scroll.configure(yscrollcommand=bar.set)
        inner=ttk.Frame(scroll)
        window=scroll.create_window(0,0,window=inner,anchor='nw')
        inner.bind('<Configure>',lambda e:scroll.configure(scrollregion=scroll.bbox('all')))
        scroll.bind('<Configure>',lambda e:scroll.itemconfigure(window,width=e.width))
        # Reuse the existing validated controls, including model/source browsing.
        self._settings_outer=self.settings
        self.settings=inner
        OriginalApp.build_settings(self)
        self.settings=self._settings_outer
        def wheel(event):
            direction=(-1 if event.num==4 else 1) if event.num in (4,5) else -int(event.delta/120)
            scroll.yview_scroll(direction,'units')
        def bind_wheel(widget):
            widget.bind('<MouseWheel>',wheel,add='+')
            widget.bind('<Button-4>',wheel,add='+')
            widget.bind('<Button-5>',wheel,add='+')
            for child in widget.winfo_children(): bind_wheel(child)
        bind_wheel(inner)

    def build_history(self):
        self._heading(self.history,'Every observation, traceable.',
                      'Review violation episodes, open evidence and export your safety records.')
        card=SoftCard(self.history,padding=14)
        card.pack(fill='both',expand=True)
        outer=self.history
        self.history=card.body
        OriginalApp.build_history(self)
        self.history=outer
        actions=card.body.winfo_children()[1]
        for button in actions.winfo_children():
            if button.cget('text')=='Export filtered CSV': button.configure(text='Export CSV')
            elif button.cget('text')=='Daily PDF report': button.configure(text='PDF report')
        first=actions.winfo_children()[0]
        ttk.Button(actions,text='Export Excel (.xlsx)',command=self.excel).pack(side='left',before=first,padx=(0,8))
        # Improve column readability while retaining the original record mapping.
        for col in self.table['columns']:
            self.table.column(col,width=185 if col in ('time','violation') else 100,stretch=True)

    def build_guide(self):
        self._heading(self.guide,'Ready for your trained model.',
                      'Your existing training workflow and this monitoring UI run independently.')
        card=SoftCard(self.guide,padding=28)
        card.pack(fill='both',expand=True)
        self._logo(card.body,'lnt_construction.png',(285,135))
        box=tk.Text(card.body,bg=WHITE,fg=INK,font=(FONT,11),wrap='word',relief='flat',
                    bd=0,padx=10,pady=18,spacing1=5,spacing3=9)
        scroll=ttk.Scrollbar(card.body,orient='vertical',command=box.yview)
        scroll.pack(side='right',fill='y')
        box.configure(yscrollcommand=scroll.set)
        box.pack(fill='both',expand=True)
        box.insert('1.0',
            '01  LOAD YOUR MODEL\n'
            'Train YOLO26s separately. In Settings & sources, browse to your custom best.pt. '
            'Choose CPU for this Quadro K4000 workstation. The interface also accepts other custom YOLO detection models.\n\n'
            '02  CHOOSE A SOURCE\n'
            'Select Image, Video, Webcam or IP Camera. Pick a file, enter a webcam index (usually 0), '
            'or supply an RTSP / HTTP address. Saved settings omit source addresses to protect credentials.\n\n'
            '03  REVIEW PPE OBSERVATIONS\n'
            'A worker is compliant only when both helmet and jacket are confirmed. Explicit missing-PPE '
            'detections produce violations after confirmation. Ambiguous or obscured PPE stays Unknown. '
            'A missed detection alone is not proof that equipment is absent.\n\n'
            '04  DATASET & CLASS MAPPING\n'
            'The Kaggle class names Person, Hardhat, NO-Hardhat, Safety Vest and NO-Safety Vest '
            'are recognized automatically. Person boxes should cover the worker, helmet boxes the head, '
            'and vest boxes the torso. Whole-person missing-PPE boxes require association changes. '
            'For different names, supply the optional class_map.json in Settings.\n\n'
            '05  HISTORY & REPORTS\n'
            'Choose Violation history to filter by analysis date and camera, open evidence, '
            'or export an Excel workbook, CSV or a daily PDF. The live Export Excel button saves '
            'the current session; history export follows the date/camera filters. '
            'Enable Demo records to review synthetic examples. '
            'Worker IDs are camera-session tracking estimates; re-entry may create a new ID.\n\n'
            'DEMO MODE\n'
            'The demo illustrates four workers and clearly marks synthetic data. Its FPS describes '
            'illustration processing, not AI inference. Nothing is labelled as live detection until a real source runs.\n\n'
            'L&T branding uses the logo assets supplied with this UI update.')
        box.configure(state='disabled')

    def paint(self):
        w,h=self.canvas.winfo_width(),self.canvas.winfo_height()
        self.canvas.delete('all')
        if w<5 or h<5: return
        if self.last_image is not None:
            preview=self.last_image.copy()
            preview.thumbnail((w,h),Image.Resampling.LANCZOS)
            self.photo=ImageTk.PhotoImage(preview)
            self.canvas.create_image(w/2,h/2,image=self.photo)
            return
        cx,cy=w/2,h/2-19
        self.canvas.create_oval(cx-45,cy-45,cx+45,cy+45,fill='#e9edff',outline='')
        self.canvas.create_rectangle(cx-22,cy-14,cx+15,cy+14,outline=BLUE,width=2)
        self.canvas.create_polygon(cx+15,cy-9,cx+28,cy-16,cx+28,cy+16,cx+15,cy+9,
                                   fill='',outline=BLUE,width=2)
        self.canvas.create_text(cx,cy+69,text='Your site. One clear view.',fill=INK,font=(FONT,16,'bold'))
        self.canvas.create_text(cx,cy+97,text='Choose a source above, or explore the synthetic demo.',
                                fill=MUTED,font=(FONT,10),width=max(100,w-50),justify='center')

    def draw_ring(self):
        if not hasattr(self,'ring'): return
        c=self.ring
        c.delete('all')
        w,h=max(1,c.winfo_width()),max(1,c.winfo_height())
        radius=min(w,h)*.39
        cx,cy=w/2,h/2
        bbox=(cx-radius,cy-radius,cx+radius,cy+radius)
        c.create_oval(*bbox,outline='#eef0f9',width=11)
        counts=self._counts()
        value=counts.get('compliance',0) if counts else 0
        if value>0:
            for i in range(80):
                a=i/79
                color='#%02x%02x%02x'%(int(32+91*a),int(198-109*a),int(223+18*a))
                c.create_arc(*bbox,start=90-i*(value*3.6/80),extent=-value*3.6/80-.6,
                             style='arc',outline=color,width=11)
        c.create_text(cx,cy-4,text=f'{value:g}%' if counts else '—',fill=INK,font=(FONT,27,'bold'))
        c.create_text(cx,cy+25,text='COMPLIANT' if counts else 'AWAITING DATA',fill=MUTED,font=(FONT,7,'bold'))

    def _counts(self):
        if not self.last_metrics: return None
        return self.last_metrics['current' if self.scope.get()=='Current frame' else 'session']

    def draw_trend(self):
        if not hasattr(self,'chart'): return
        c=self.chart
        c.delete('all')
        w,h=max(1,c.winfo_width()),max(1,c.winfo_height())
        left,right,top,bottom=29,w-9,8,h-15
        for p in (0,50,100):
            y=bottom-(bottom-top)*p/100
            c.create_line(left,y,right,y,fill=LINE)
            c.create_text(left-6,y,text=str(p),anchor='e',fill=MUTED,font=(FONT,6))
        scope=0 if self.scope.get()=='Current frame' else 1
        values=[item[scope] for item in self._trend]
        if len(values)<2:
            c.create_text((left+right)/2,(top+bottom)/2,text='Trend appears as monitoring runs',
                          fill=MUTED,font=(FONT,8))
            return
        points=[]
        for i,v in enumerate(values): points.extend((left+(right-left)*i/(len(values)-1),bottom-(bottom-top)*v/100))
        c.create_polygon(left,bottom,*points,right,bottom,fill='#edf3ff',outline='')
        c.create_line(*points,fill=BLUE,width=2,smooth=False)
        x,y=points[-2:]
        c.create_oval(x-3,y-3,x+3,y+3,fill=CYAN,outline=WHITE,width=1)

    def update_metrics(self,fps=None):
        counts=self._counts()
        if not counts: return
        if fps is not None: self._last_fps=fps
        for key,var in self.cards.items(): var.set(str(counts[key]))
        for key,var in self.ppe_values.items(): var.set(str(counts[key]))
        self.unknown_note.set(f"Unknown: {counts['helmet_unknown']} helmet · {counts['vest_unknown']} jacket")
        self.ring_note.set(f"{counts['safe']} compliant / {counts['total']} tracked workers")
        active_cfg=self.runner.cfg if self.runner is not None else None
        mode=active_cfg.mode if active_cfg else getattr(self,'_session_mode',self.vars['mode'].get())
        camera=active_cfg.camera if active_cfg else getattr(self,'_session_camera',self.vars['camera'].get())
        demo=mode=='Demo'
        if self._last_fps is not None:
            self.fps_text.set('Synthetic demo' if demo else f'{self._last_fps:.1f} processing FPS')
        self.feed_caption.set(f"{camera}  /  "+('SYNTHETIC DEMO' if demo else mode))
        scope=self.scope.get()
        self.card_titles['total'].set('WORKERS IN VIEW' if scope=='Current frame' else 'SESSION WORKER IDS')
        self.scope_note.set(('Current frame: workers visible now.' if scope=='Current frame' else
                            'Session latest: each track ID’s last observed state.')+
                           f"   ·   {self.last_metrics['events']} violation episodes   ·   "
                           f"{self.last_metrics['session']['total']} session track IDs")
        now=time.monotonic()
        if fps is not None and now-self._last_sample>=1:
            self._last_sample=now
            self._trend.append((self.last_metrics['current']['compliance'],self.last_metrics['session']['compliance']))
        self.draw_ring()
        self.draw_trend()

    def _add_activity(self,text):
        # Status is displayed as text, never interpreted as a file or command.
        compact=text if len(text)<83 else text[:80]+'…'
        self._activity.appendleft(datetime.now().strftime('%H:%M:%S')+'   '+compact)
        self.activity_text.set('\n'.join(list(self._activity)[:3]))

    def start(self):
        if self.runner is not None: return
        OriginalApp.start(self)
        if self.runner is not None:
            self.last_image=self.last_metrics=None
            for variable in self.cards.values(): variable.set('—')
            for variable in self.ppe_values.values(): variable.set('—')
            self._trend.clear()
            self._last_sample=0
            self._last_fps=None
            self._session_demo=self.runner.cfg.mode=='Demo'
            self._session_mode=self.runner.cfg.mode
            self._session_camera=self.runner.cfg.camera
            self._session_output=self.runner.cfg.output
            self._session_id=self.runner.session
            self.ring_note.set('Starting a new monitoring session')
            self.fps_text.set('Awaiting first frame')
            self.unknown_note.set('Unknown PPE is shown separately.')
            self.paint()
            self.draw_ring()
            self.draw_trend()
            self.mode_select.configure(state='disabled')
            self._add_activity('Synthetic demo started' if self._session_demo else 'Monitoring session started')

    def finish(self):
        before=self.runner
        OriginalApp.finish(self)
        if before is not None and self.runner is None:
            self.mode_select.configure(state='readonly')
            self._add_activity('Session stopped. Evidence is available in Violation history.')
            if getattr(self,'_session_demo',False): self.fps_text.set('Synthetic demo · stopped')
            else: self.fps_text.set('Session stopped')

    def poll(self):
        if self.runner:
            frame=self.runner.take_frame()
            if frame:
                self.last_image,self.last_metrics,fps=frame
                self.paint()
                self.update_metrics(fps)
        while True:
            try: kind,value=self.messages.get_nowait()
            except queue.Empty: break
            if kind in ('status','event'):
                self.status_text.set(value)
                if kind=='event': self._add_activity(value)
            elif kind=='error':
                self.status_text.set('Session failed: '+value)
                self._add_activity('Session error. Review the message below.')
                if not self.closing: messagebox.showerror('Monitoring error',value)
            elif kind=='done': self.after(100,self.finish)
        if self.closing and self.runner is None:
            self.destroy()
            return
        self.after(100,self.poll)

    def _clock(self):
        if self.closing: return
        self.clock_text.set(datetime.now().strftime('%a, %d %b %Y    %I:%M %p'))
        self.after(1000,self._clock)

    def excel(self,current=False):
        try:
            if current:
                session_id=getattr(self,'_session_id','')
                if not session_id:
                    messagebox.showinfo('Excel report','Start a session first, or use Violation history to export earlier records.')
                    return
                day=''
                camera=self._session_camera
                demo=self._session_demo
                output=self._session_output
            else:
                session_id=''
                day=self.validated_day()
                camera=self.filter_camera.get().strip()
                demo=self.demo_history.get()
                output=self.vars['output'].get()
            root=Path(output)/('demo' if demo else 'records')
            events,sessions=read_report_data(root,day,camera,session_id)
            if not events and not sessions:
                messagebox.showinfo('Excel report','No saved records match this selection. '
                                    'For a new session, wait for its first result. '
                                    'In history, check the date, camera and Demo records filter.')
                return
            path=filedialog.asksaveasfilename(title='Save Excel safety report',
                defaultextension='.xlsx',filetypes=[('Excel workbook','*.xlsx')],
                initialfile=f"SiteGuard_{'Demo_' if demo else ''}{day or date.today().isoformat()}.xlsx")
            if not path: return
            export_excel(path,events,sessions,day=day,camera=camera,demo=demo,session_id=session_id)
            self.status_text.set(f'Excel report saved: {Path(path).name} — {len(events)} episodes, {len(sessions)} session records.')
            self._add_activity('Excel report exported: '+Path(path).name)
            messagebox.showinfo('Excel report saved','Workbook saved successfully.\n\n'
                                'Sheets: Summary, Violations, Sessions.\n'+str(path))
        except PermissionError:
            messagebox.showerror('Excel report','Close the destination workbook in Excel and export again, or choose a different filename.')
        except Exception as exc:
            messagebox.showerror('Excel report',str(exc))


if __name__=='__main__':
    App().mainloop()
