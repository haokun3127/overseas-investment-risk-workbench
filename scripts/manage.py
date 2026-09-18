"""Run from repository root: python -m scripts.manage backup|init-admin|restore."""
import argparse
import getpass
import hashlib
import json
import secrets
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from app.config import Settings
from app.store import Store

def backup(directory,destination):
    destination=destination.resolve()
    if destination.exists():
        raise ValueError('备份目标已存在，请使用新目录。')
    if directory.resolve()==destination or directory.resolve() in destination.parents:
        raise ValueError('备份目录不能位于数据目录内。')
    destination.mkdir(parents=True)
    source=sqlite3.connect(directory/'risk.db')
    target=sqlite3.connect(destination/'risk.db')
    try: source.backup(target)
    finally: source.close();target.close()
    shutil.copytree(directory/'uploads',destination/'uploads')
    (destination/'backup.json').write_text(json.dumps({'created_at':datetime.now().isoformat(),'format':1},indent=2),encoding='utf-8')
    print(f'备份完成：{destination}')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['init-admin','backup','restore'])
    parser.add_argument('--destination',type=Path)
    parser.add_argument('--source',type=Path)
    args=parser.parse_args();settings=Settings()
    if args.action=='init-admin':
        store=Store(settings.data_dir)
        if store.setting('admin'):raise ValueError('管理员已存在，拒绝覆盖。')
        password=getpass.getpass('设置管理员密码（至少10位）：')
        if not 10<=len(password)<=128 or password!=getpass.getpass('再次输入：'):raise ValueError('密码长度不符或两次输入不一致。')
        salt=secrets.token_hex(16)
        digest=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),300000).hex()
        with store.db() as db:db.execute('INSERT INTO settings VALUES (?,?)',('admin',json.dumps({'salt':salt,'hash':digest})))
        print('管理员已初始化。')
    elif args.action=='backup':
        if not args.destination:raise ValueError('请指定 --destination 备份目录。')
        backup(settings.data_dir,args.destination)
    else:
        if not args.source or not args.destination:raise ValueError('请指定 --source 备份目录与 --destination 新数据目录。')
        if args.destination.exists():raise ValueError('恢复目标必须是不存在的新目录，拒绝覆盖现有数据。')
        if not (args.source/'risk.db').is_file() or not (args.source/'uploads').is_dir():raise ValueError('备份不完整。')
        with sqlite3.connect(args.source/'risk.db') as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('备份数据库完整性检查失败。')
        shutil.copytree(args.source,args.destination)
        # Restored sessions must not revive old logins.
        with sqlite3.connect(args.destination/'risk.db') as db:db.execute('DELETE FROM sessions')
        print(f'已恢复到新目录：{args.destination.resolve()}。修改 DATA_DIR 后启动服务。')

if __name__=='__main__':
    try:main()
    except ValueError as e:raise SystemExit(str(e))
