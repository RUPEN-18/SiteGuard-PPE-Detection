"""Background inference, capture and evidence pipeline. Heavy imports are lazy."""
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
import json
import threading
import time
import uuid
import queue
from PIL import Image, ImageDraw, ImageFont
from .core import Detection, Assessor, class_map, status
from .storage import Store

@dataclass
class Config:
    weights: str = ''
    source: str = ''
    mode: str = 'Demo'
    camera: str = 'CAM-01'
    tracker: str = 'bytetrack'
    device: str = 'auto'
    confidence: float = .40
    iou: float = .50
    imgsz: int = 1280
    stride: int = 1
    fps: int = 20
    confirm: int = 3
    save_media: bool = True
    output: str = str(Path.home()/'Documents'/'SiteGuard')
    mapping: str = ''


def annotate(image, active, demo=False):
    image = image.copy()
    draw = ImageDraw.Draw(image)
    try: font = ImageFont.truetype('DejaVuSans.ttf',16)
    except OSError: font = ImageFont.load_default()
    for s in active:
        decision = status(s.helmet,s.vest)
        color = {'SAFE':'#34d399','VIOLATION':'#fb7185','UNKNOWN':'#fbbf24'}[decision]
        x1,y1,x2,y2 = [int(v) for v in s.box]
        draw.rectangle((x1,y1,x2,y2),outline=color,width=3)
        label = f'ID {s.track_id:03d} | H: {s.helmet} | J: {s.vest} | {decision}'
        bbox = draw.textbbox((0,0),label,font=font)
        tw = bbox[2]+10
        lx, ly = max(0,min(x1,image.width-tw)), max(34,y1-25)
        draw.rectangle((lx,ly,lx+tw,ly+24),fill='#0f172a')
        draw.text((lx+4,ly+2),label,fill=color,font=font)
    draw.rectangle((0,0,image.width,30),fill='#0f172a')
    draw.text((12,5),'SYNTHETIC DEMO - NOT AI DETECTIONS' if demo else 'SITEGUARD | PPE monitoring',fill='#ffffff',font=font)
    return image


class LatestCapture:
    """Drain a live stream continuously; keep one latest frame to avoid backlog."""
    def __init__(self, cap):
        self.cap = cap
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.latest = None
        self.sequence = 0
        self.failed = False
        self.thread = threading.Thread(target=self._read,daemon=True)
        self.thread.start()

    def _read(self):
        try:
            while not self.stop.is_set():
                ok, frame = self.cap.read()
                if not ok:
                    self.failed = True
                    break
                with self.lock:
                    self.latest = frame
                    self.sequence += 1
        finally:
            self.cap.release()

    def get(self, previous):
        with self.lock:
            return (self.sequence,self.latest) if self.sequence!=previous else (previous,None)

    def close(self):
        self.stop.set()
        self.thread.join(timeout=6)


class Runner(threading.Thread):
    def __init__(self, config, messages):
        super().__init__(daemon=True)
        self.cfg, self.messages = config, messages
        self.stop_event = threading.Event()
        self.session = uuid.uuid4().hex
        self.root = Path(config.output)/('demo' if config.mode=='Demo' else 'records')
        self.error = None
        self.latest = None
        self.lock = threading.Lock()

    def send(self, kind, value): self.messages.put((kind,value))
    def stop(self): self.stop_event.set()
    def frame(self, image, metrics, fps):
        with self.lock: self.latest = (image,metrics,fps)
    def take_frame(self):
        with self.lock:
            result, self.latest = self.latest, None
            return result

    def run(self):
        cap = live = writer = store = None
        assessor = Assessor(self.cfg.confirm)
        active = []
        c = self.cfg
        try:
            store = Store(self.root)
            session_dir = self.root/self.session
            session_dir.mkdir(parents=True)
            # Do not persist source URLs: they may contain camera credentials.
            (session_dir/'session.json').write_text(json.dumps({
                'session':self.session,'mode':c.mode,'camera':c.camera,'tracker':c.tracker,
                'model':Path(c.weights).name,'confidence':c.confidence,'iou':c.iou,
                'imgsz':c.imgsz,'stride':c.stride,'created_at':datetime.now().astimezone().isoformat()
            },indent=2),encoding='utf-8')
            demo = c.mode=='Demo'
            still = c.mode=='Image'
            live_mode = c.mode in ('Webcam','IP Camera')
            source_fps = float(c.fps)
            if not demo:
                self.send('status','Loading model and tracker...')
                import cv2
                import torch
                import numpy as np
                from ultralytics import YOLO
                from ultralytics.utils import YAML, IterableSimpleNamespace
                from ultralytics.utils.checks import check_yaml
                from ultralytics.trackers.byte_tracker import BYTETracker
                from ultralytics.trackers.bot_sort import BOTSORT
                if not Path(c.weights).is_file(): raise ValueError('Choose your custom-trained best.pt file.')
                model = YOLO(c.weights,task='detect')
                overrides = json.loads(Path(c.mapping).read_text()) if c.mapping else None
                roles = class_map(model.names,overrides)
                reverse = {v:k for k,v in roles.items()}
                device = ('0' if torch.cuda.is_available() else 'cpu') if c.device=='auto' else c.device
                self.send('status',f'Using {device.upper()} | {c.tracker} | session {self.session[:8]}')
                args = YAML.load(check_yaml(c.tracker+'.yaml'))
                args['with_reid'] = False  # No hidden extra model/download required for BoT-SORT.
                args['track_high_thresh'] = c.confidence
                args['new_track_thresh'] = c.confidence
                args['track_low_thresh'] = min(.1,c.confidence/2)
                tracker_class = BYTETracker if c.tracker=='bytetrack' else BOTSORT
                tracker = tracker_class(IterableSimpleNamespace(**args))
                if still:
                    raw = cv2.imdecode(np.fromfile(c.source,dtype=np.uint8),cv2.IMREAD_COLOR)
                    if raw is None: raise ValueError('Unable to decode image.')
                else:
                    if c.mode=='Webcam':
                        cap = cv2.VideoCapture(int(c.source or '0'))
                        cap.set(cv2.CAP_PROP_FPS,c.fps)
                    elif c.mode=='IP Camera':
                        cap = cv2.VideoCapture(c.source,cv2.CAP_FFMPEG,[cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,5000,cv2.CAP_PROP_READ_TIMEOUT_MSEC,5000])
                    else: cap = cv2.VideoCapture(c.source)
                    if not cap.isOpened(): raise ValueError('Could not open source. Check path, camera index, or RTSP address.')
                    source_fps = cap.get(cv2.CAP_PROP_FPS)
                    if not (1<=source_fps<=240): source_fps = float(c.fps)
                    if live_mode: live = LatestCapture(cap)
            started = time.monotonic()
            last_snapshot, sequence, index = 0,0,0
            while not self.stop_event.is_set():
                tick = time.monotonic()
                if demo:
                    image, workers, equipment = demo_frame(index)
                    media_seconds = index/10
                    shape = (image.height,image.width)
                else:
                    if live_mode:
                        sequence, raw = live.get(sequence)
                        if raw is None:
                            if live.failed: raise ValueError('Camera disconnected. Stop and restart to reconnect in a new session.')
                            self.stop_event.wait(.01)
                            continue
                        if sequence % c.stride:
                            continue
                        media_seconds = time.monotonic()-started
                    elif not still:
                        ok, raw = cap.read()
                        if not ok: break
                        index += 1
                        if (index-1)%c.stride: continue
                        media_seconds = (index-1)/source_fps
                    else: media_seconds = 0
                    shape = raw.shape
                    result = model.predict(raw,conf=min(.1,c.confidence),iou=c.iou,imgsz=c.imgsz,
                                           device=device,verbose=False,max_det=1000)[0]
                    boxes = result.boxes.cpu().numpy()
                    people = boxes[boxes.cls==roles['person']]
                    if still:
                        workers = [Detection(tuple(b.xyxy[0]),float(b.conf[0]),'person',i+1)
                                   for i,b in enumerate(people) if b.conf[0]>=c.confidence]
                    else:
                        tracked = tracker.update(people,raw)
                        workers = [Detection(tuple(r[:4]),float(r[5]),'person',int(r[4])) for r in tracked]
                    equipment = [Detection(tuple(b.xyxy[0]),float(b.conf[0]),reverse[int(b.cls[0])])
                                 for b in boxes if int(b.cls[0]) in reverse and int(b.cls[0])!=roles['person']
                                 and b.conf[0]>=c.confidence]
                    image = Image.fromarray(cv2.cvtColor(raw,cv2.COLOR_BGR2RGB))
                active, events = assessor.update(workers,equipment,shape,media_seconds,still=still)
                rendered = annotate(image,active,demo)
                for worker in events:
                    evidence = session_dir/f'worker_{worker.track_id:03d}_{uuid.uuid4().hex[:12]}.jpg'
                    rendered.save(evidence,quality=92)
                    store.add(self.session,worker,c.camera,media_seconds,evidence)
                    self.send('event',f'Worker {worker.track_id:03d}: {worker.helmet} helmet / {worker.vest} jacket')
                metrics = assessor.metrics(active)
                if time.monotonic()-last_snapshot>=1:
                    store.snapshot(self.session,c.camera,metrics)
                    last_snapshot = time.monotonic()
                if c.save_media:
                    if still: rendered.save(session_dir/'annotated.jpg',quality=95)
                    elif not demo:
                        if writer is None:
                            # File-video output preserves duration after stride decimation.
                            output_fps = source_fps/c.stride if not live_mode else max(1,min(c.fps,1/max(.001,time.monotonic()-tick)))
                            writer = cv2.VideoWriter(str(session_dir/'annotated.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),output_fps,rendered.size)
                            if not writer.isOpened(): raise ValueError('MP4 writer unavailable. Disable Save media or install a codec-enabled OpenCV build.')
                        writer.write(cv2.cvtColor(np.asarray(rendered),cv2.COLOR_RGB2BGR))
                        with (session_dir/'frame_timestamps.csv').open('a',encoding='utf-8') as f:
                            f.write(f'{media_seconds:.6f},{datetime.now().astimezone().isoformat()}\n')
                self.frame(rendered,metrics,1/max(.001,time.monotonic()-tick))
                if still: break
                if demo:
                    index += 1
                    self.stop_event.wait(.1)
                elif live_mode:
                    self.stop_event.wait(max(0,1/c.fps-(time.monotonic()-tick)))
            self.send('status',f'Session complete. Results: {session_dir}')
        except Exception as exc:
            # Avoid leaking authenticated camera URLs in dialogs/logs.
            message = str(exc)
            if c.mode=='IP Camera' and c.source: message = message.replace(c.source,'[camera address]')
            self.error = message
            self.send('error',message)
        finally:
            if live: live.close()
            elif cap is not None: cap.release()
            if writer is not None: writer.release()
            if store:
                try: store.snapshot(self.session,c.camera,assessor.metrics(active))
                finally: store.close()
            self.send('done',None)


def demo_frame(index):
    """Clearly labelled synthetic data for UI tests; never model output."""
    image = Image.new('RGB',(1080,650),'#172638')
    draw = ImageDraw.Draw(image)
    for x in range(0,1080,80): draw.line((x,0,x,650),fill='#243447')
    draw.rectangle((0,500,1080,650),fill='#263849')
    workers, equipment = [], []
    for i,x in enumerate((70,330,590,850),1):
        x += int(8*__import__('math').sin(index/15+i))
        box = (x,120,x+140,530)
        workers.append(Detection(box,.95,'person',i))
        helmet = i in (1,3)
        vest = i in (1,2)
        # One repeating recovery demonstrates event rearming.
        if i==4 and (index//120)%2: helmet=vest=True
        draw.ellipse((x+35,125,x+105,200),fill='#f8c9a3')
        draw.rectangle((x+18,205,x+122,380),fill='#fbbf24' if vest else '#64748b')
        draw.rectangle((x+25,380,x+58,525),fill='#94a3b8')
        draw.rectangle((x+82,380,x+115,525),fill='#94a3b8')
        if helmet: draw.pieslice((x+25,110,x+115,180),180,360,fill='#fbbf24')
        equipment += [Detection((x+25,120,x+115,183),.93,'helmet' if helmet else 'no_helmet'),
                      Detection((x+18,210,x+122,370),.91,'vest' if vest else 'no_vest')]
    return image,workers,equipment
