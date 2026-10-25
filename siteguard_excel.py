"""Portable Excel export for the desktop application.

Populates the bundled, styled report template using Python's standard library.
No Excel installation, Node runtime, openpyxl, or package update is needed on
the user's PC. Input text is always written as a literal spreadsheet string.
"""
from datetime import datetime
from pathlib import Path
import json
import math
import os
import re
import sqlite3
import tempfile
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
ET.register_namespace('',NS)
ET.register_namespace('r','http://schemas.openxmlformats.org/officeDocument/2006/relationships')
TAG=lambda name:f'{{{NS}}}{name}'
TEMPLATE=Path(__file__).resolve().parent/'assets'/'report_template.xlsx'
BAD_XML=re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]')


def read_report_data(root,day='',camera='',session_id=''):
    """Read both datasets in one consistent SQLite transaction, without writes."""
    path=Path(root)/'safety.db'
    if not path.is_file(): return [],[]
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=15)
    db.row_factory=sqlite3.Row
    try:
        db.execute('BEGIN')
        events=[dict(r) for r in db.execute(
            'SELECT * FROM events WHERE (?="" OR day=?) AND (?="" OR camera=?) '
            'AND (?="" OR session=?) ORDER BY id DESC',
            (day,day,camera,camera,session_id,session_id))]
        sessions=[dict(r) for r in db.execute(
            'SELECT * FROM snapshots WHERE (?="" OR day=?) AND (?="" OR camera=?) '
            'AND (?="" OR session=?) ORDER BY day,camera,session',
            (day,day,camera,camera,session_id,session_id))]
        for row in sessions: row['metrics']=json.loads(row['metrics'])
        return events,sessions
    finally: db.close()


def _col(n):
    text=''
    while n:
        n,rem=divmod(n-1,26)
        text=chr(65+rem)+text
    return text


def _cell(sheet,address):
    data=sheet.find(TAG('sheetData'))
    number=int(re.search(r'\d+$',address).group())
    row=next((r for r in data if int(r.get('r'))==number),None)
    if row is None:
        row=ET.Element(TAG('row'),r=str(number))
        data.append(row)
        data[:]=sorted(data,key=lambda r:int(r.get('r')))
    cell=next((c for c in row if c.get('r')==address),None)
    if cell is None:
        cell=ET.SubElement(row,TAG('c'),r=address)
    return cell


def _put(cell,value,formula=None):
    for child in list(cell): cell.remove(child)
    cell.attrib.pop('t',None)
    if formula is not None:
        ET.SubElement(cell,TAG('f')).text=formula.lstrip('=')
        if isinstance(value,str): cell.set('t','str')
        ET.SubElement(cell,TAG('v')).text=str(value)
    elif isinstance(value,(int,float)) and not isinstance(value,bool):
        if not math.isfinite(value): raise ValueError('The report contains a non-finite number.')
        ET.SubElement(cell,TAG('v')).text=str(value)
    elif value is not None:
        cell.set('t','inlineStr')
        inline=ET.SubElement(cell,TAG('is'))
        text=ET.SubElement(inline,TAG('t'))
        text.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
        text.text=BAD_XML.sub('',str(value))[:32767]


def _when(raw):
    value=datetime.fromisoformat(str(raw))
    offset=value.strftime('%z')
    offset=offset[:3]+':'+offset[3:] if offset else ''
    local=value.replace(tzinfo=None)
    serial=(local-datetime(1899,12,30)).total_seconds()/86400
    return serial,offset


def _set_rows(sheet,rows,columns):
    if len(rows)>1048570: raise ValueError('Too many rows for one Excel sheet. Filter by date or camera.')
    data=sheet.find(TAG('sheetData'))
    sample=next((r for r in data if r.get('r')=='7'),None)
    styles={re.sub(r'\d','',c.get('r')):c.get('s','0') for c in sample} if sample is not None else {}
    height=sample.get('ht','25') if sample is not None else '25'
    for row in list(data):
        if int(row.get('r'))>=7: data.remove(row)
    for idx,values in enumerate(rows,7):
        row=ET.SubElement(data,TAG('row'),r=str(idx),ht=height,customHeight='1')
        for n,value in enumerate(values,1):
            col=_col(n)
            cell=ET.SubElement(row,TAG('c'),r=f'{col}{idx}',s=styles.get(col,'0'))
            if isinstance(value,tuple): _put(cell,value[1],formula=value[0])
            else: _put(cell,value)
    end=max(6,6+len(rows))
    dim=sheet.find(TAG('dimension'))
    if dim is not None: dim.set('ref',f'A1:{_col(columns)}{end}')
    filt=sheet.find(TAG('autoFilter'))
    if filt is None:
        filt=ET.Element(TAG('autoFilter'))
        sheet.insert(list(sheet).index(data)+1,filt)
    filt.set('ref',f'A6:{_col(columns)}{end}')
    # A stale selected range must not point outside the new exported data.
    for selection in sheet.findall('.//'+TAG('selection')):
        selection.set('activeCell','A7')
        selection.set('sqref','A7')


def export_excel(path,events,sessions,*,day='',camera='',demo=False,session_id='',template=TEMPLATE):
    """Export filtered violations and latest daily session snapshots to .xlsx."""
    path,template=Path(path),Path(template)
    if path.resolve()==template.resolve(): raise ValueError('Choose a report filename outside the template asset.')
    if not template.is_file(): raise FileNotFoundError('Missing assets/report_template.xlsx. Copy the entire UI update.')
    violation_rows=[]
    for row in events:
        when,offset=_when(row['recorded_at'])
        violation_rows.append([when,offset,row['camera'],row['session'],f"{int(row['worker']):03d}",
                               row['helmet'],row['vest'],row['violation'],float(row['confidence']),
                               float(row['media_seconds']),row['evidence'],int(row['id'])])
    session_rows=[]
    counts=[]
    for i,row in enumerate(sessions,7):
        metrics=row['metrics']
        if isinstance(metrics,str): metrics=json.loads(metrics)
        c=metrics['session']
        counts.append(c)
        updated,offset=_when(row['updated_at'])
        day_serial,_=_when(row['day'])
        compliance=c['safe']/c['total'] if c['total'] else 0
        session_rows.append([day_serial,row['camera'],row['session'],updated,offset,
            c['total'],c['safe'],c['unsafe'],c['unknown'],c['helmet'],c['no_helmet'],c['helmet_unknown'],
            c['vest'],c['no_vest'],c['vest_unknown'],(f'=IF(F{i}=0,0,G{i}/F{i})',compliance),
            metrics['events'],metrics['helmet_events'],metrics['vest_events'],metrics['multiple_events']])
    total=sum(c['total'] for c in counts)
    safe=sum(c['safe'] for c in counts)
    values={9:len(sessions),10:total,11:safe,12:sum(c['unsafe'] for c in counts),
            13:sum(c['unknown'] for c in counts),14:safe/total if total else 'n.a.',
            15:len(events),16:sum(r['helmet']=='Missing' for r in events),
            17:sum(r['vest']=='Missing' for r in events),
            18:sum(r['helmet']==r['vest']=='Missing' for r in events),
            21:sum(c['helmet'] for c in counts),22:sum(c['no_helmet'] for c in counts),
            23:sum(c['vest'] for c in counts),24:sum(c['no_vest'] for c in counts)}
    se,ve=max(7,6+len(sessions)),max(7,6+len(events))
    formulas={9:f'=COUNTA(Sessions!C7:C{se})',10:f'=SUM(Sessions!F7:F{se})',
        11:f'=SUM(Sessions!G7:G{se})',12:f'=SUM(Sessions!H7:H{se})',13:f'=SUM(Sessions!I7:I{se})',
        14:'=IF(B10=0,"n.a.",B11/B10)',15:f'=COUNTA(Violations!L7:L{ve})',
        16:f'=COUNTIF(Violations!F7:F{ve},"Missing")',17:f'=COUNTIF(Violations!G7:G{ve},"Missing")',
        18:f'=COUNTIFS(Violations!F7:F{ve},"Missing",Violations!G7:G{ve},"Missing")',
        21:f'=SUM(Sessions!J7:J{se})',22:f'=SUM(Sessions!K7:K{se})',
        23:f'=SUM(Sessions!M7:M{se})',24:f'=SUM(Sessions!N7:N{se})'}
    with ZipFile(template) as original:
        parts={name:original.read(name) for name in original.namelist()}
    summary=ET.fromstring(parts['xl/worksheets/sheet1.xml'])
    for address,value in {'B4':'Demo (synthetic)' if demo else 'Real observations',
            'B5':day or 'All dates','B6':camera or 'All cameras',
            'D5':'Generated: '+datetime.now().astimezone().isoformat(timespec='seconds'),
            'D19':'Session filter: '+(session_id or 'All matching sessions')}.items():
        _put(_cell(summary,address),value)
    for number,value in values.items(): _put(_cell(summary,f'B{number}'),value,formula=formulas[number])
    parts['xl/worksheets/sheet1.xml']=ET.tostring(summary,encoding='utf-8',xml_declaration=True)
    for filename,rows,n in [('sheet2.xml',violation_rows,12),('sheet3.xml',session_rows,20)]:
        sheet=ET.fromstring(parts['xl/worksheets/'+filename])
        _set_rows(sheet,rows,n)
        parts['xl/worksheets/'+filename]=ET.tostring(sheet,encoding='utf-8',xml_declaration=True)
    workbook=ET.fromstring(parts['xl/workbook.xml'])
    calc=workbook.find(TAG('calcPr'))
    if calc is None: calc=ET.SubElement(workbook,TAG('calcPr'))
    calc.set('fullCalcOnLoad','1');calc.set('forceFullCalc','1');calc.set('calcMode','auto')
    parts['xl/workbook.xml']=ET.tostring(workbook,encoding='utf-8',xml_declaration=True)
    if 'xl/calcChain.xml' in parts:
        parts.pop('xl/calcChain.xml')
        for name in ['[Content_Types].xml','xl/_rels/workbook.xml.rels']:
            tree=ET.fromstring(parts[name])
            for child in list(tree):
                if 'calcChain' in child.get('PartName','') or 'calcChain' in child.get('Type',''):
                    tree.remove(child)
            parts[name]=ET.tostring(tree,encoding='utf-8',xml_declaration=True)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,temporary=tempfile.mkstemp(prefix='.siteguard-',suffix='.xlsx',dir=str(path.parent))
    os.close(fd)
    try:
        with ZipFile(temporary,'w',ZIP_DEFLATED) as output:
            for name,data in parts.items(): output.writestr(name,data)
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    return path
