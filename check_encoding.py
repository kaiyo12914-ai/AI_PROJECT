import sys, pathlib
for p in ['.roadmap/會議擬答ROADMAP.md', 'webapps/database/sync_sqlserver_to_postgres.py', 'webapps/meetingreply/views.py']:
    f = pathlib.Path(p)
    if not f.exists():
        print(f'{p} -> NOT FOUND')
        continue
    raw = f.read_bytes()
    if raw.startswith(b'\xef\xbb\xbf'):
        print(f'{p} -> BOM')
    try: 
        text = raw.decode('utf-8')
        if '\ufffd' in text:
            print(f'{p} -> MOJIBAKE (ufffd)')
        else:
            print(f'{p} -> UTF-8 OK')
    except: 
        print(f'{p} -> NOT UTF-8')
