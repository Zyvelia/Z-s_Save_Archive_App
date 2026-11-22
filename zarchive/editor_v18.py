"""v1.8: conservative declarative game-specific editor engine.

No arbitrary Python plugins are executed. Imported saves and originals are immutable.
Only explicitly registered JSON file fields can be changed.
"""
from __future__ import annotations
import hashlib, json, os, re, shutil, tempfile, uuid
from pathlib import Path
from .upgrade_v17 import ArchiveV17
from .storage import folder_digest, now

MAX_FILE = 8 * 1024 * 1024
MAX_WORKING = 512 * 1024 * 1024
MAX_FIELDS = 64
TOKEN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')


NUMBERED_SAVE = re.compile(r'(Save)?([0-9a-f]+)(\.sav)', re.I)


def numbered_save_name(filename, number):
    """Replace the slot in a numbered .sav filename, preserving its prefix and zero padding."""
    match = NUMBERED_SAVE.fullmatch(filename)
    if match is None:
        raise ValueError('Choose a numbered .sav file.')
    requested = number.strip()
    if not re.fullmatch(r'[0-9a-f]+', requested, re.I):
        raise ValueError('Enter a slot using digits 0–9 or hexadecimal letters A–F.')
    prefix, slot, extension = match.groups()
    if len(slot) > 1 and slot.startswith('0'):
        requested = requested.zfill(len(slot))
    name = (prefix or '') + requested + extension
    if name.casefold() == filename.casefold():
        raise ValueError('Choose a different save number.')
    return name


def _safe_rel(value):
    if not isinstance(value,str) or not value or '\\' in value or '\0' in value:
        raise ValueError('Invalid relative filename')
    p=Path(value)
    if p.is_absolute() or '..' in p.parts or p.parts[0] in ('.','') or ':' in value or len(p.parts)>8:
        raise ValueError('Unsafe relative filename')
    return p


def validate_definition(schema):
    if not isinstance(schema,dict) or schema.get('schema_version')!=1:
        raise ValueError('Unknown plugin schema version')
    if not isinstance(schema.get('id'),str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{1,63}',schema['id']):
        raise ValueError('Invalid editor id')
    if not isinstance(schema.get('name'),str) or not 1<=len(schema['name'])<=100:raise ValueError('Invalid name')
    platforms=schema.get('platforms')
    if not isinstance(platforms,list) or not platforms or not set(platforms)<= {'PS3','PC'}:raise ValueError('Invalid platforms')
    game=schema.get('game')
    if not isinstance(game,str) or not 1<=len(game)<=120:raise ValueError('Game name required')
    _safe_rel(schema.get('file'))
    fields=schema.get('fields')
    if not isinstance(fields,list) or not 1<=len(fields)<=MAX_FIELDS:raise ValueError('Invalid fields')
    seen=set()
    for f in fields:
        if not isinstance(f,dict) or not TOKEN.fullmatch(str(f.get('key',''))):raise ValueError('Invalid field key')
        if f['key'] in seen:raise ValueError('Duplicate field')
        seen.add(f['key'])
        if f.get('type') not in ('integer','boolean','string'):raise ValueError('Unsupported field type')
        if f['type']=='integer':
            if type(f.get('min'))!=int or type(f.get('max'))!=int or f['min']>f['max'] or abs(f['min'])>10**15 or abs(f['max'])>10**15:
                raise ValueError('Invalid numeric limits')
        if f['type']=='string' and (type(f.get('max_length'))!=int or not 1<=f['max_length']<=1024):
            raise ValueError('Invalid string limit')
    return schema


def _json_root(folder,schema):
    p=(Path(folder)/_safe_rel(schema['file']))
    if p.is_symlink() or not p.is_file() or p.stat().st_size>MAX_FILE:raise ValueError('Missing or oversized editor file')
    # check all parent path links
    for parent in list(p.parents):
        if parent==Path(folder):break
        if parent.is_symlink():raise ValueError('Symlinked path')
    with p.open('r',encoding='utf-8') as fd: obj=json.load(fd)
    if not isinstance(obj,dict):raise ValueError('Editor requires a JSON object')
    return p,obj


def _validate_value(spec,value):
    ty=spec['type']
    if ty=='integer':
        if type(value)!=int or not spec['min']<=value<=spec['max']:raise ValueError('Integer outside declared limits')
    elif ty=='boolean':
        if type(value)!=bool:raise ValueError('Boolean required')
    elif ty=='string':
        if not isinstance(value,str) or len(value)>spec['max_length']:raise ValueError('Invalid text length')
    return value


class ArchiveV18(ArchiveV17):
    def __init__(self,root):
        super().__init__(root)
        self.conn.executescript('''
        CREATE TABLE IF NOT EXISTS editors_v18(id TEXT PRIMARY KEY, definition TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS edits_v18(id TEXT PRIMARY KEY,save_id TEXT NOT NULL,plugin_id TEXT NOT NULL,
            backup_path TEXT NOT NULL,output_path TEXT NOT NULL,before_hash TEXT NOT NULL,after_hash TEXT NOT NULL,
            created_at TEXT NOT NULL, FOREIGN KEY(save_id) REFERENCES saves(id));
        ''')

    def _delete_save_record(self, record_id):
        self.conn.execute('DELETE FROM edits_v18 WHERE save_id=?', (record_id,))
        super()._delete_save_record(record_id)

    def install_editor(self,definition):
        validate_definition(definition)
        with self.conn:self.conn.execute('INSERT INTO editors_v18(id,definition) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET definition=excluded.definition',
            (definition['id'],json.dumps(definition,sort_keys=True)))
        return definition['id']

    def editors(self,game=None,platform=None):
        rows=[json.loads(r['definition']) for r in self.conn.execute('SELECT definition FROM editors_v18 WHERE enabled=1 ORDER BY id')]
        return [r for r in rows if (game is None or r['game'].casefold()==game.casefold()) and (platform is None or platform in r['platforms'])]

    def save_for_edit(self,save_id):
        row=self.conn.execute('SELECT * FROM active_saves WHERE id=?',(save_id,)).fetchone()
        if row is None:raise ValueError('Save not in archive')
        folder=(self.root/row['stored_path']).resolve()
        if not folder.is_relative_to(self.data_dir.resolve()) or not folder.is_dir():raise ValueError('Invalid stored save path')
        digest=folder_digest(folder)
        if digest!=(row['file_hash'],row['size_bytes'],row['file_count']):raise ValueError('Archived save integrity check failed')
        return dict(row),folder

    def numbered_saves(self, save_id):
        _, folder = self.save_for_edit(save_id)
        return sorted(path.relative_to(folder) for path in folder.rglob('*')
                      if NUMBERED_SAVE.fullmatch(path.name) and path.is_file())

    def export_numbered_save(self, save_id, relative_file, number, output_folder):
        _, folder = self.save_for_edit(save_id)
        relative = Path(relative_file)
        if relative.anchor or '..' in relative.parts:
            raise ValueError('Choose a file from the archived save.')
        filename = numbered_save_name(relative.name, number)
        original = folder / relative
        if original.resolve(strict=True) != original or not original.is_file():
            raise ValueError('Choose a regular file from the archived save.')
        output = Path(output_folder).expanduser().resolve(strict=True)
        if not output.is_dir() or output.is_relative_to(self.root):
            raise ValueError('Choose an existing folder outside the managed archive.')
        target = output / filename
        with original.open('rb') as source:
            destination = target.open('xb')
            try:
                with destination:
                    shutil.copyfileobj(source, destination)
            except BaseException:
                target.unlink(missing_ok=True)
                raise
        return target

    def inspect_editor(self,save_id,plugin_id,working_folder=None):
        row,folder=self.save_for_edit(save_id)
        plugin=next((p for p in self.editors(row['game'],row['platform']) if p['id']==plugin_id),None)
        if plugin is None:raise ValueError('No matching editor definition for this game and platform')
        folder=Path(working_folder).expanduser().resolve(strict=True) if working_folder else folder
        if folder!= (self.root/row['stored_path']).resolve():
            if not folder.is_dir() or folder.is_symlink():raise ValueError('Invalid decrypted folder')
            folder_digest(folder)
        _,data=_json_root(folder,plugin)
        fields={}
        for spec in plugin['fields']:
            key=spec['key']
            if key not in data:raise ValueError(f'Declared field missing: {key}')
            fields[key]=_validate_value(spec,data[key])
        return {'save_id':save_id,'game':row['game'],'platform':row['platform'],
                'plugin':plugin,'values':fields,'source':str(folder)}

    def edit_copy(self,save_id,plugin_id,changes,output_dir,working_folder=None):
        """Backup original, stage a working copy, validate, atomically export NEW folder.

        Output is not re-imported automatically and never touches console or original data.
        """
        row,original=self.save_for_edit(save_id)
        inspected=self.inspect_editor(save_id,plugin_id,working_folder)
        plugin=inspected['plugin']
        if not isinstance(changes,dict) or not changes:raise ValueError('No edits supplied')
        specs={f['key']:f for f in plugin['fields']}
        for key,v in changes.items():
            if key not in specs:raise ValueError('Undeclared field: '+str(key))
            _validate_value(specs[key],v)
        target=Path(output_dir).expanduser().resolve()
        if target.exists():raise FileExistsError('Choose a new output folder')
        if target.is_relative_to(self.root) or self.root.is_relative_to(target):raise ValueError('Output must be outside managed archive')
        src=Path(inspected['source'])
        if target.is_relative_to(src) or src.is_relative_to(target):raise ValueError('Unsafe output location')
        target.parent.mkdir(parents=True,exist_ok=True)
        tmp=Path(tempfile.mkdtemp(prefix='.zsave-edit-',dir=target.parent))
        try:
            shutil.copytree(src,tmp,dirs_exist_ok=True,symlinks=False)
            before=folder_digest(tmp)
            if before[1]>MAX_WORKING:raise ValueError('Working save too large')
            p,data=_json_root(tmp,plugin)
            data.update(changes)
            for spec in plugin['fields']:_validate_value(spec,data[spec['key']])
            updated=json.dumps(data,indent=2,ensure_ascii=False)+'\n'
            if len(updated.encode('utf-8'))>MAX_FILE:raise ValueError('Edited file too large')
            scratch=p.with_name('.'+p.name+'.tmp')
            try:
                with scratch.open('x',encoding='utf-8',newline='\n') as fd:
                    fd.write(updated);fd.flush();os.fsync(fd.fileno())
                os.replace(scratch,p)
            finally:scratch.unlink(missing_ok=True)
            _json_root(tmp,plugin)
            after=folder_digest(tmp)
            # create and verify original backup before exposing output
            backup=self.make_backup(save_id)
            backup_row=self.conn.execute('SELECT id FROM backups WHERE path=?',(str(backup.relative_to(self.root)),)).fetchone()
            if not backup_row or not self.verify_backup(backup_row['id']):raise ValueError('Pre-edit backup verification failed')
            tmp.rename(target)
            eid=uuid.uuid4().hex
            with self.conn:self.conn.execute('INSERT INTO edits_v18 VALUES (?,?,?,?,?,?,?,?)',
                (eid,save_id,plugin_id,str(backup.relative_to(self.root)),str(target),before[0],after[0],now()))
            return {'edit_id':eid,'backup':str(backup),'output':str(target),'before_sha256':before[0],'after_sha256':after[0]}
        finally:
            if tmp.exists():shutil.rmtree(tmp,ignore_errors=True)

    def edit_history(self,save_id):
        return [dict(x) for x in self.conn.execute('SELECT * FROM edits_v18 WHERE save_id=? ORDER BY created_at DESC',(save_id,))]


def compare_binary(left,right,*,max_bytes=1024*1024,max_differences=256):
    """Bounded, read-only raw comparison. No format interpretation or patching."""
    a,b=Path(left),Path(right)
    if not a.is_file() or not b.is_file() or a.is_symlink() or b.is_symlink():raise ValueError('Two ordinary files required')
    if not 1<=max_bytes<=8*1024*1024 or not 1<=max_differences<=2048:raise ValueError('Invalid limits')
    out=[];checked=0
    with a.open('rb') as x,b.open('rb') as y:
        while checked<max_bytes and len(out)<max_differences:
            aa=x.read(1);bb=y.read(1)
            if not aa and not bb:break
            if aa!=bb:out.append({'offset':checked,'left':aa.hex() if aa else None,'right':bb.hex() if bb else None})
            checked+=1
    return {'differences':out,'bytes_checked':checked,'left_size':a.stat().st_size,'right_size':b.stat().st_size,
            'truncated':checked<max(a.stat().st_size,b.stat().st_size)}
