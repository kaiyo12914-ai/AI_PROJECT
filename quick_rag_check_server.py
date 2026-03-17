import subprocess, os, time, requests

env=os.environ.copy()
env['PYTHONPATH']=r'H:\AI\Django'
sp=subprocess.Popen([r'H:\AI\Django\venv3.12\Scripts\python.exe','manage.py','runserver','8010','--noreload'],cwd=r'H:\AI\Django',env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    time.sleep(6)
    u='http://127.0.0.1:8010/djangoai/meetingreply/api/rag_only/?aaa=Fy1o2u9r1a9s5t6u0p0i'
    r=requests.post(u,json={'q':'資安','k':10},timeout=60)
    print(r.status_code)
    print(r.text[:1000])
finally:
    sp.terminate()
