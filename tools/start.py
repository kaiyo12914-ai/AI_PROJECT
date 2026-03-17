import os
import traceback
from waitress import serve

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")

from webproj.wsgi import application

if __name__ == "__main__":
    try:
        print("Starting Waitress on http://0.0.0.0:8090 ...")
        serve(application, host="0.0.0.0", port=8090, threads=4)
    except Exception:
        print("Waitress failed to start:")
        traceback.print_exc()
        input("Press Enter to exit...")