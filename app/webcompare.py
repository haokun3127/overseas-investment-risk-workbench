"""Compare saved snapshots of the same URL within one configured source."""
import re
from difflib import SequenceMatcher


def normalized(text):
    return re.sub(r'\s+',' ',text or '').strip()


def archive(page):
    return bool(page.get('archived_at') or page.get('method')=='archive' or page.get('title','').startswith('［网页存档'))


def previous_page(db, page, source_id):
    row = db.execute('''SELECT p.id,p.run_id,p.title,p.url,p.body,p.method,p.archived_at,p.fetched_at
        FROM web_pages p JOIN web_runs r ON r.id=p.run_id
        WHERE r.source_id=? AND r.status='completed' AND r.id<? AND p.url=?
        ORDER BY r.id DESC,p.id DESC LIMIT 1''',(source_id,page['run_id'],page['url'])).fetchone()
    return dict(row) if row else None


def summary(current, previous):
    if not previous:
        status = 'added'
    elif archive(current)!=archive(previous):
        status = 'incomparable'
    elif normalized(current['body'])==normalized(previous['body']):
        status = 'unchanged'
    else:
        status = 'changed'
    return {'status':status,'previous_id':previous['id'] if previous else None,
            'previous_run_id':previous['run_id'] if previous else None,
            'previous_fetched_at':previous['fetched_at'] if previous else None}


def units(text):
    # Sentence/paragraph boundaries make Chinese and minified pages readable;
    # bounded pieces keep the diff usable for very long paragraphs.
    return [part[i:i+400] for part in re.split(r'(?<=[。！？；.!?;])\s*|[\r\n]+',text.strip())
            if part.strip() for i in range(0,len(part),400)]


def differences(current, previous):
    before,after = units(previous['body']),units(current['body'])
    matcher = SequenceMatcher(None,before,after,autojunk=True)
    hunks,added,removed,used,truncated = [],0,0,0,False
    for tag,i,j,k,l in matcher.get_opcodes():
        if tag!='equal':
            removed += sum(len(t) for t in before[i:j])
            added += sum(len(t) for t in after[k:l])
    for group in matcher.get_grouped_opcodes(1):
        rows=[]
        for tag,i,j,k,l in group:
            if tag=='equal':
                entries=[('context',t) for t in after[k:l]]
            else:
                entries=[('removed',t) for t in before[i:j]]+[('added',t) for t in after[k:l]]
            for kind,text in entries:
                if used+len(text)>60000 or sum(len(h) for h in hunks)+len(rows)>=240:
                    truncated=True
                    break
                rows.append({'kind':kind,'text':text})
                used+=len(text)
            if truncated:break
        if rows:hunks.append(rows)
        if truncated:break
    return {'hunks':hunks,'added_characters':added,'removed_characters':removed,'truncated':truncated}


def comparison(current,previous):
    result=summary(current,previous)
    fields=('id','run_id','title','url','fetched_at','method','archived_at')
    result['current']={k:current[k] for k in fields}
    result['previous']={k:previous[k] for k in fields} if previous else None
    result.update(differences(current,previous) if result['status']=='changed' else {'hunks':[],'added_characters':0,'removed_characters':0,'truncated':False})
    return result
