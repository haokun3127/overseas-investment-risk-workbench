"""Authenticated reference data, separate from model analysis and business documents."""
import hashlib
import json
from pathlib import Path
import re

LEVEL_ORDER=('lv1','lv2','lv3','lv4','lv5')
SOURCE_FILENAME='风险预警分级1027.doc'
UNAVAILABLE='分级对策原文暂不可用，请管理员核对原文文件与对策数据。'


def _paths(data_dir):
    root=Path(data_dir).resolve()
    directory=root/'reference-data'/'grading-1027'
    paths=(directory/'bank.json',directory/'source.doc')
    if any(not path.resolve().is_relative_to(root) for path in paths):
        raise ValueError('Reference data must remain inside the data directory')
    return paths


def load_library(data_dir):
    """Fail visibly on missing, malformed or mismatched sources; never invent fallback advice."""
    try:
        bank_path,source_path=_paths(data_dir)
        if bank_path.stat().st_size>131072 or source_path.stat().st_size>10*1024*1024:
            raise ValueError('Reference source exceeds size limit')
        data=json.loads(bank_path.read_text(encoding='utf-8'))
        if data.get('schema_version')!=1 or set(data['levels'])!=set(LEVEL_ORDER):
            raise ValueError('Reference schema or grade set is invalid')
        source=data['source']
        if not isinstance(source,dict) or not re.fullmatch(r'[a-f0-9]{64}',source.get('sha256','')):
            raise ValueError('Invalid source fingerprint')
        if hashlib.sha256(source_path.read_bytes()).hexdigest()!=source['sha256']:
            raise ValueError('Original document does not match the reference')
        for key in ('title','version','section'):
            if not isinstance(source.get(key),str) or not source[key].strip() or len(source[key])>300:
                raise ValueError('Invalid reference description')
        ids=set()
        for key in LEVEL_ORDER:
            entry=data['levels'][key]
            if entry['level']!=key:
                raise ValueError('Grade key does not match its data')
            for name in ('label','threshold','standard','standard_locator'):
                if not isinstance(entry.get(name),str) or not entry[name].strip() or len(entry[name])>3000:
                    raise ValueError('Invalid grade reference')
            for role in ('enterprise','state'):
                items=entry.get(role)
                if not isinstance(items,list) or not 1<=len(items)<=100:
                    raise ValueError('Reference role is empty or invalid')
                for item in items:
                    if not isinstance(item,dict) or not re.fullmatch(role+r'-r[1-9]\d*',item.get('id','')):
                        raise ValueError('Invalid reference item')
                    if item['id'] in ids:
                        raise ValueError('Duplicate reference item')
                    ids.add(item['id'])
                    for field in ('text','locator'):
                        if not isinstance(item.get(field),str) or not item[field].strip() or len(item[field])>3000:
                            raise ValueError('Invalid reference text')
        fields=('level','label','threshold','standard','standard_locator','enterprise','state')
        return {'status':'available','source':{key:source[key] for key in ('title','version','section','sha256')},
                'levels':[{field:data['levels'][key][field] for field in fields} for key in LEVEL_ORDER]}
    except (OSError,ValueError,TypeError,KeyError,AttributeError):
        return {'status':'unavailable','message':UNAVAILABLE,'source':None,'levels':[]}


def for_level(library,level):
    if level not in LEVEL_ORDER:
        return {'status':'unsupported_level','level':level,
                'message':'该记录未采用当前五级标准，请先核对预警等级，不能直接套用分级对策。'}
    if library['status']!='available':
        return {'status':'unavailable','level':level,'message':UNAVAILABLE}
    return {'status':'available','source':library['source'],
            **next(entry for entry in library['levels'] if entry['level']==level)}


def report_reference(library,levels):
    present=set(levels)
    return {'status':library['status'],'message':library.get('message',''),'source':library['source'],
            'groups':[for_level(library,key) for key in LEVEL_ORDER if key in present],
            'unsupported_levels':sorted(present-set(LEVEL_ORDER))}


def source_file(data_dir):
    if load_library(data_dir)['status']!='available':
        return None
    return _paths(data_dir)[1]
