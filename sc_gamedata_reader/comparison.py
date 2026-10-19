"""Compare static reader exports, never game code. CC0-1.0."""
import argparse
from collections import Counter, defaultdict
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path, PurePosixPath
from .contract import FORMAT_VERSION, CALL_FORMAT_VERSION
from .reporting import write_csv


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def label(value):
    if not isinstance(value,str) or not value or '\\' in value or ':' in value:
        raise ValueError('Export file labels must be portable relative paths')
    path=PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Export file labels must be portable relative paths')
    return path.as_posix()


def validate_document(document):
    if not isinstance(document,dict) or document.get('format_version') != FORMAT_VERSION:
        raise ValueError('Comparison requires reader format_version 2')
    label(document.get('file'))
    if not isinstance(document.get('assignments'),list) or not isinstance(document.get('warnings'),list):
        raise ValueError('Malformed reader export')
    for assignment in document['assignments']:
        if (not isinstance(assignment,dict) or not isinstance(assignment.get('target'),str)
                or 'value' not in assignment or type(assignment.get('line')) is not int
                or type(assignment.get('conditional')) is not bool
                or (assignment.get('scope') is not None and not isinstance(assignment['scope'],str))):
            raise ValueError('Malformed assignment record')
    for warning in document['warnings']:
        if not isinstance(warning,dict) or not all(isinstance(warning.get(k),str) for k in ('code','message')) or type(warning.get('line')) is not int:
            raise ValueError('Malformed warning record')
        if warning['code']=='input':
            raise ValueError('Unreadable-input exports must be regenerated before comparison')
    capability=document.get('call_format_version')
    if capability is not None and capability != CALL_FORMAT_VERSION:
        raise ValueError('Unsupported structured-call capability')
    if capability == CALL_FORMAT_VERSION:
        if not isinstance(document.get('calls'),list):
            raise ValueError('Malformed call collection')
        for call in document['calls']:
            if not isinstance(call,dict) or not isinstance(call.get('arguments'),list) or type(call.get('line')) is not int:
                raise ValueError('Malformed call record')
    return document


def definition(document, record):
    scope=record.get('scope')
    if scope is None:
        return 0
    definitions=[f for f in document.get('functions',[]) if f['name']==scope]
    for index,function in enumerate(definitions,1):
        if function['line'] <= record['line'] <= (function.get('end_line') or float('inf')):
            return index
    return 0


def align(before,after,key,signature):
    """Retain matching repeated records before pairing changed blocks."""
    left,right=defaultdict(list),defaultdict(list)
    for i,record in enumerate(before): left[key(record,True)].append((i,record))
    for i,record in enumerate(after): right[key(record,False)].append((i,record))
    pairs=[]
    for group in sorted(left.keys() | right.keys(),key=canonical):
        old,new=left[group],right[group]
        matcher=SequenceMatcher(a=[signature(r) for _,r in old],b=[signature(r) for _,r in new],autojunk=False)
        for _,a,b,c,d in matcher.get_opcodes():
            for offset in range(max(b-a,d-c)):
                li=a+offset if a+offset<b else None
                ri=c+offset if c+offset<d else None
                pairs.append((group,old[li] if li is not None else None,
                              new[ri] if ri is not None else None,
                              li+1 if li is not None else '',ri+1 if ri is not None else ''))
    return pairs


def assignment_signature(record):
    return canonical([record['value'],record['conditional']])


def entries(value):
    if isinstance(value,list):
        return list(enumerate(value,1))
    if isinstance(value,dict):
        if '$table' in value:
            return [(e['key'],e['value']) for e in value['$table']]
        if not any(k.startswith('$') for k in value):
            return list(value.items())
    return []


def segment(key):
    return (key if isinstance(key,str) else canonical(key)).replace('~','~0').replace('/','~1')


def gameplay_lists(value,target=''):
    found={}

    def capture(modes,path):
        pairs=entries(modes)
        keys=[k for k,_ in pairs]
        contiguous=(all(type(k) is int for k in keys)
                    and sorted(keys)==list(range(1,len(keys)+1)))
        values=[v for _,v in sorted(pairs)] if contiguous else [v for _,v in pairs]
        table=isinstance(modes,list) or (isinstance(modes,dict) and '$table' in modes)
        concrete=table and contiguous and all(type(v) is int for v in values)
        found[path]=dict(state='literal' if concrete else 'unresolved',
                         ids=values if concrete else None,sha256=digest(modes))

    def levels(value,path):
        maps=entries(value)
        if not maps:
            capture(value,path+'/<empty-or-unresolved>')
        counts=Counter()
        for key,modes in maps:
            name=segment(key);counts[name]+=1
            capture(modes,path+'/'+name+'#'+str(counts[name]))

    def walk(value,path):
        counts=Counter()
        for key,child in entries(value):
            name=segment(key);counts[name]+=1
            child_path=path+'/'+name+'#'+str(counts[name])
            if key=='levelsDesc': levels(child,child_path)
            elif key=='gameplays': capture(child,child_path)
            else: walk(child,child_path)

    if '.levelsDesc' in target:
        suffix=target.split('.levelsDesc',1)[1]
        if not suffix: levels(value,'/levelsDesc')
        elif suffix.startswith(('.', '[')): capture(value,'/levelsDesc/'+segment(suffix))
        else: walk(value,'')
    elif target.endswith('.gameplays'):
        capture(value,'/gameplays')
    else:
        walk(value,'')
    return found


def compare_documents(before,after):
    """Return compact changes for one file; None represents an absent file."""
    for document in (before,after):
        if document is not None: validate_document(document)
    file=(before or after)['file']
    if before and after and before['file'] != after['file']:
        raise ValueError('Matched exports have different source file labels')
    old=before or dict(assignments=[],warnings=[],functions=[])
    new=after or dict(assignments=[],warnings=[],functions=[])
    rows=[];games=[];warnings=[]
    pairs=align(old['assignments'],new['assignments'],
                lambda a,left:(a.get('scope'),definition(old if left else new,a),a['target']),
                assignment_signature)
    changed_pairs={}; matched=[]

    def row_for(group,left,right,lo,ro,change):
        a=left[1] if left else None;b=right[1] if right else None
        return dict(file=file,scope=group[0],definition=group[1],target=group[2],
                    occurrence_before=lo,occurrence_after=ro,change=change,
                    before_line=a['line'] if a else '',after_line=b['line'] if b else '',
                    before_type=type(a['value']).__name__ if a else '',
                    after_type=type(b['value']).__name__ if b else '',
                    before_sha256=digest([a['value'],a['conditional']]) if a else '',
                    after_sha256=digest([b['value'],b['conditional']]) if b else '')

    def game_rows(group,left,right,lo,ro,kind):
        a=left[1] if left else None;b=right[1] if right else None
        av=(a['value'] if kind=='assignment' else a['arguments']) if a else None
        bv=(b['value'] if kind=='assignment' else b['arguments']) if b else None
        first=gameplay_lists(av,group[2] if kind=='assignment' else '') if a else {}
        second=gameplay_lists(bv,group[2] if kind=='assignment' else '') if b else {}
        for path in sorted(first.keys() | second.keys()):
            x,y=first.get(path),second.get(path)
            if x==y:continue
            old_ids=x['ids'] if x else None; new_ids=y['ids'] if y else None
            change='added' if x is None else ('removed' if y is None else 'changed')
            if x and y and old_ids is not None and new_ids is not None and set(old_ids)==set(new_ids):
                change='order_or_multiplicity_changed'
            games.append(dict(file=file,scope=group[0],definition=group[1],container_kind=kind,
                              container=group[2],occurrence_before=lo,occurrence_after=ro,path=path,change=change,
                              before_line=a['line'] if a else '',after_line=b['line'] if b else '',
                              before_state=x['state'] if x else 'absent',after_state=y['state'] if y else 'absent',
                              before_ids=canonical(old_ids),after_ids=canonical(new_ids),
                              removed_ids=canonical(sorted(set(old_ids or [])-set(new_ids or []))) if old_ids is not None and new_ids is not None else 'null',
                              added_ids=canonical(sorted(set(new_ids or [])-set(old_ids or []))) if old_ids is not None and new_ids is not None else 'null',
                              before_sha256=x['sha256'] if x else '',after_sha256=y['sha256'] if y else ''))

    for group,left,right,lo,ro in pairs:
        change='added' if left is None else ('removed' if right is None else 'changed')
        if left and right:
            matched.append((left[0],right[0],(group,left,right,lo,ro)))
        if left is None or right is None or assignment_signature(left[1]) != assignment_signature(right[1]):
            row=row_for(group,left,right,lo,ro,change);rows.append(row)
            if left and right:changed_pairs[(left[0],right[0])]=row
        if left is None or right is None or assignment_signature(left[1]) != assignment_signature(right[1]):
            game_rows(group,left,right,lo,ro,'assignment')
    old_order=sorted(matched)
    new_ranks={item[0]:rank for rank,item in enumerate(sorted(matched,key=lambda item:item[1]))}
    for rank,(li,ri,details) in enumerate(old_order):
        if new_ranks[li] != rank:
            if (li,ri) in changed_pairs: changed_pairs[(li,ri)]['change']='changed_and_reordered'
            else:rows.append(row_for(*details,'reordered'))
    calls_available=all(d is None or d.get('call_format_version')==CALL_FORMAT_VERSION for d in (before,after))
    if calls_available:
        call_pairs=align(old.get('calls',[]),new.get('calls',[]),
                         lambda c,left:(c.get('scope'),definition(old if left else new,c),c.get('callee') or '<dynamic>',c.get('context')),
                         lambda c:canonical([c['arguments'],c.get('callee_value'),c.get('conditional')]))
        for group,left,right,lo,ro in call_pairs:
            if left is None or right is None or canonical(left[1]['arguments']) != canonical(right[1]['arguments']):
                game_rows(group,left,right,lo,ro,'call')
    first=Counter((w['code'],w['message']) for w in old['warnings'])
    second=Counter((w['code'],w['message']) for w in new['warnings'])
    for key in sorted(first.keys() | second.keys()):
        if first[key] == second[key]:continue
        warnings.append(dict(file=file,code=key[0],message=key[1],before_count=first[key],
                             after_count=second[key],delta=second[key]-first[key],
                             before_lines=canonical([w['line'] for w in old['warnings'] if (w['code'],w['message'])==key]),
                             after_lines=canonical([w['line'] for w in new['warnings'] if (w['code'],w['message'])==key])))
    file_change='added' if before is None else ('removed' if after is None else ('changed' if rows or games or warnings else 'unchanged'))
    return dict(file=dict(file=file,change=file_change,before_assignments=len(old['assignments']),
                          after_assignments=len(new['assignments']),before_warnings=len(old['warnings']),
                          after_warnings=len(new['warnings']),gameplay_coverage='assignments_and_calls' if calls_available else 'assignments_only'),
                assignments=rows,gameplay_lists=games,warnings=warnings)


def export_paths(path):
    path=Path(path)
    if path.is_file():return {'<single>':path}
    if not path.is_dir():raise ValueError('Export input does not exist')
    files={p.relative_to(path).as_posix():p for p in sorted(path.rglob('*.json'))}
    if not files:raise ValueError('Export directory contains no JSON documents')
    return files


def read_document(path):
    if path is None:return None
    try:
        with path.open(encoding='utf-8-sig') as stream:
            return validate_document(json.load(stream,parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON value'))))
    except (OSError,UnicodeError,json.JSONDecodeError,TypeError,KeyError) as error:
        raise ValueError('Cannot read a valid reader export') from error


def compare_exports(before,after):
    left,right=export_paths(before),export_paths(after)
    if ('<single>' in left) != ('<single>' in right):
        raise ValueError('Compare two files or two export directories')
    result=dict(files=[],assignments=[],gameplay_lists=[],warnings=[])
    for key in sorted(left.keys() | right.keys()):
        changed=compare_documents(read_document(left.get(key)),read_document(right.get(key)))
        result['files'].append(changed['file'])
        for category in ('assignments','gameplay_lists','warnings'):result[category].extend(changed[category])
    result['summary']=dict(comparison_format_version=1,reader_format_version=FORMAT_VERSION,
                           files=len(result['files']),changed_files=sum(r['change']!='unchanged' for r in result['files']),
                           assignment_changes=len(result['assignments']),gameplay_list_changes=len(result['gameplay_lists']),
                           warning_changes=len(result['warnings']),
                           limited_gameplay_coverage_files=sum(r['gameplay_coverage']=='assignments_only' for r in result['files']))
    return result


FIELDS={
    'files':['file','change','before_assignments','after_assignments','before_warnings','after_warnings','gameplay_coverage'],
    'assignments':['file','scope','definition','target','occurrence_before','occurrence_after','change','before_line','after_line','before_type','after_type','before_sha256','after_sha256'],
    'gameplay_lists':['file','scope','definition','container_kind','container','occurrence_before','occurrence_after','path','change','before_line','after_line','before_state','after_state','before_ids','after_ids','removed_ids','added_ids','before_sha256','after_sha256'],
    'warnings':['file','code','message','before_count','after_count','delta','before_lines','after_lines'],
}


def main(argv=None):
    parser=argparse.ArgumentParser(description='Compare two read-only reader exports.')
    parser.add_argument('before',type=Path)
    parser.add_argument('after',type=Path)
    parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        output=args.out.resolve()
        if any(path.resolve()==output or (path.is_dir() and path.resolve() in output.parents) for path in (args.before,args.after)):
            raise ValueError('Comparison output must be outside the export inputs')
        result=compare_exports(args.before,args.after)
        output.mkdir(parents=True,exist_ok=True)
        for category,fields in FIELDS.items():write_csv(output/(category+'.csv'),fields,result[category])
        (output/'summary.json').write_text(json.dumps(result['summary'],sort_keys=True,indent=2)+'\n',encoding='utf-8')
        lines=['# Export comparison','', '*(file)* Static parsed-export comparison; input exports were read only.','',
               '| Metric | Count |','|---|---:|']
        lines += [f'| {key} | {value} |' for key,value in result['summary'].items()]
        lines += ['', 'Line/offset movement alone is ignored. Repeated targets are aligned within',
                  'scope/definition by value sequence; relative assignment order is checked.',
                  'Gameplay rows describe declarations and call arguments, not active queues.',
                  'Only literal id lists have added/removed ids; unresolved values have hashes.',
                  'Warnings compare code/message multiplicities, ignoring location-only movement.','']
        (output/'summary.md').write_text('\n'.join(lines),encoding='utf-8')
        print(json.dumps(result['summary'],sort_keys=True))
        return 1 if result['summary']['changed_files'] else 0
    except (OSError,UnicodeError,ValueError,KeyError,TypeError,RecursionError):
        parser.exit(2,'Cannot compare exports: check schema, input readability and output location\n')
