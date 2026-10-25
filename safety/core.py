"""PPE association and temporal decisions; independent of UI and inference."""
from dataclasses import dataclass, field
from collections import deque
import math
import re
import numpy as np
from scipy.optimize import linear_sum_assignment

PRESENT, MISSING, UNKNOWN = 'Present', 'Missing', 'Unknown'
ALIASES = {
 'person': {'person', 'worker', 'workman', 'workmen'},
 'helmet': {'helmet', 'hardhat', 'safetyhelmet'},
 'no_helmet': {'nohelmet', 'nohardhat', 'withouthelmet'},
 'vest': {'vest', 'safetyvest', 'safetyjacket', 'reflectivevest', 'jacket'},
 'no_vest': {'novest', 'nosafetyvest', 'nosafetyjacket', 'nojacket', 'withoutvest'},
}

def class_map(names, overrides=None):
    result = {}
    for idx, name in names.items():
        key = re.sub(r'[^a-z0-9]', '', name.lower())
        for role, aliases in ALIASES.items():
            if key in aliases:
                if role in result:
                    raise ValueError(f'Multiple classes map to {role}. Use class_map.json to select IDs.')
                result[role] = int(idx)
    if overrides:
        result.update({k: int(v) for k, v in overrides.items()})
    required = set(ALIASES)
    if required - result.keys():
        raise ValueError('PPE weights must contain person, helmet, no_helmet, vest, no_vest. '
                         f'Missing: {sorted(required - result.keys())}. Stock yolo26x.pt is not PPE-trained.')
    if len(set(result.values())) != len(result) or any(v not in names for v in result.values()):
        raise ValueError('Class IDs must be distinct and present in model.names.')
    return result

@dataclass
class Detection:
    box: tuple
    confidence: float
    role: str
    track_id: int = 0


def status(helmet, vest):
    if MISSING in (helmet, vest):
        return 'VIOLATION'
    return 'SAFE' if helmet == vest == PRESENT else 'UNKNOWN'


def match_equipment(workers, equipment, kind, frame_shape):
    """One-to-one Hungarian assignment per body region, competing +/- labels.
    Ambiguous ownership and conflicting class evidence are explicitly unknown.
    Missing labels must annotate bare HEAD / unvested TORSO, not whole persons.
    """
    n, m = len(workers), len(equipment)
    answer = [(UNKNOWN, 0.0)] * n
    if not n or not m:
        return answer
    scores = np.zeros((n, m))
    height, width = frame_shape[:2]
    visible = []
    for i, w in enumerate(workers):
        x1, y1, x2, y2 = w.box
        bw, bh = max(1, x2-x1), max(1, y2-y1)
        # Reject distant or boundary-clipped assessment regions.
        valid = bh >= 60 and bw >= 18 and (y1 > 2 if kind == 'helmet' else True)
        visible.append(valid)
        if not valid:
            continue
        ry1, ry2 = (y1 - .05*bh, y1 + .32*bh) if kind == 'helmet' else (y1+.18*bh, y1+.72*bh)
        rx1, rx2 = x1-.08*bw, x2+.08*bw
        target_y = y1 + (.10 if kind == 'helmet' else .43)*bh
        for j, p in enumerate(equipment):
            a,b,c,d = p.box
            pw, ph = max(1, c-a), max(1, d-b)
            cx, cy = (a+c)/2, (b+d)/2
            if not (rx1 <= cx <= rx2 and ry1 <= cy <= ry2):
                continue
            if pw > 1.15*bw or ph > (.4 if kind == 'helmet' else .65)*bh:
                continue
            overlap = max(0, min(c, rx2)-max(a, rx1))*max(0, min(d, ry2)-max(b, ry1))/(pw*ph)
            if overlap < .55:
                continue
            distance = math.hypot((cx-(x1+x2)/2)/bw, (cy-target_y)/bh)
            scores[i,j] = .6*overlap + .25*max(0,1-distance) + .15*p.confidence
    # Discard a PPE box if two workers are nearly equally plausible owners.
    for j in range(m):
        ordered = sorted(scores[:,j], reverse=True)
        if len(ordered)>1 and ordered[1]>0 and ordered[0]-ordered[1]<.08:
            scores[:,j] = 0
    # Reject contradictory positive/negative evidence for the same worker.
    conflict = set()
    for i in range(n):
        roles = {equipment[j].role for j in range(m) if scores[i,j]>.55}
        if kind in roles and 'no_'+kind in roles:
            conflict.add(i)
            scores[i,:] = 0
    padded = np.concatenate([scores, np.full((n,n), .55)], axis=1)
    rows, cols = linear_sum_assignment(-padded)
    for i,j in zip(rows,cols):
        if j<m and scores[i,j]>.55 and i not in conflict and visible[i]:
            p = equipment[j]
            answer[i] = (MISSING if p.role.startswith('no_') else PRESENT, p.confidence)
    return answer

@dataclass
class WorkerState:
    track_id: int
    helmet: str = UNKNOWN
    vest: str = UNKNOWN
    confidence: float = 0.0
    last_seen: float = 0
    history: deque = field(default_factory=lambda: deque(maxlen=5))
    episode: bool = False
    clear_run: int = 0
    ever_violation: bool = False
    box: tuple = (0,0,0,0)

class Assessor:
    def __init__(self, confirm=3):
        self.confirm = confirm
        self.previous_ids = set()
        self.workers = {}
        self.events = 0
        self.helmet_events = self.vest_events = self.multiple_events = 0

    def update(self, workers, equipment, shape, now, still=False):
        helmets = match_equipment(workers, [e for e in equipment if e.role in ('helmet','no_helmet')], 'helmet', shape)
        vests = match_equipment(workers, [e for e in equipment if e.role in ('vest','no_vest')], 'vest', shape)
        events, active = [], []
        for i, detection in enumerate(workers):
            s = self.workers.setdefault(detection.track_id, WorkerState(detection.track_id))
            if detection.track_id not in self.previous_ids:
                s.history.clear()
            s.last_seen, s.box = now, detection.box
            s.history.append((helmets[i], vests[i]))
            states, confidences = [], []
            required = 1 if still else self.confirm
            for column in (0,1):
                recent = list(s.history)[-required:]
                values = [row[column][0] for row in recent]
                agreed = len(values)>=required and len(set(values))==1 and values[0]!=UNKNOWN
                states.append(values[0] if agreed else UNKNOWN)
                confidences.append(min(row[column][1] for row in recent) if agreed else 0)
            s.helmet, s.vest = states
            # Confidence of evidence supporting violation, or both positive PPE labels.
            selected = [c for v,c in zip(states,confidences) if v==MISSING] if MISSING in states else confidences
            s.confidence = min([detection.confidence]+selected)
            decision = status(*states)
            if decision == 'VIOLATION':
                s.clear_run = 0
                s.ever_violation = True
                if not s.episode:
                    s.episode = True
                    self.events += 1
                    self.helmet_events += int(s.helmet==MISSING)
                    self.vest_events += int(s.vest==MISSING)
                    self.multiple_events += int(s.helmet==s.vest==MISSING)
                    events.append(s)
            elif decision == 'SAFE':
                s.clear_run += 1
                if s.clear_run >= required:
                    s.episode = False
            else:
                s.clear_run = 0  # Unknown never rearms a violation episode.
            active.append(s)
        self.previous_ids = {w.track_id for w in workers}
        return active, events

    def metrics(self, active):
        all_states = list(self.workers.values())
        def counts(states):
            total = len(states)
            safe = sum(status(s.helmet,s.vest)=='SAFE' for s in states)
            violation = sum(status(s.helmet,s.vest)=='VIOLATION' for s in states)
            return dict(total=total, safe=safe, unsafe=violation, unknown=total-safe-violation,
                        helmet=sum(s.helmet==PRESENT for s in states),
                        no_helmet=sum(s.helmet==MISSING for s in states),
                        vest=sum(s.vest==PRESENT for s in states),
                        no_vest=sum(s.vest==MISSING for s in states),
                        helmet_unknown=sum(s.helmet==UNKNOWN for s in states),
                        vest_unknown=sum(s.vest==UNKNOWN for s in states),
                        compliance=round(100*safe/total,1) if total else 0)
        return dict(current=counts(active), session=counts(all_states),
                    ever_unsafe=sum(s.ever_violation for s in all_states), events=self.events,
                    helmet_events=self.helmet_events, vest_events=self.vest_events,
                    multiple_events=self.multiple_events)
