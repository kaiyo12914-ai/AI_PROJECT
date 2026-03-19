import os
import sys

# Ensure project root is in path before anything else
sys.path.append(r"F:\AI\AI_TOOLS")

import django
from django.conf import settings
from django.urls import get_resolver
from django.test import RequestFactory
from webapps.portal.middleware_proxy_prefix import ForwardedPrefixMiddleware

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'webproj.settings')
django.setup()

def audit():
    print(f"ENV: {os.getenv('ENV')}")
    print(f"FORCE_SCRIPT_NAME: {settings.FORCE_SCRIPT_NAME}")
    print(f"STATIC_URL: {settings.STATIC_URL}")
    print(f"STATIC_ROOT: {settings.STATIC_ROOT}")
    print(f"STATICFILES_DIRS: {settings.STATICFILES_DIRS}")

    rf = RequestFactory()
    path = "/djangoai/static/portal/css/index.css"
    request = rf.get(path)
    
    def get_resp(r): return r
    middleware = ForwardedPrefixMiddleware(get_resp)
    middleware(request)
    
    stripped_path = request.path_info
    print(f"Original path: {path}")
    print(f"Middleware stripped path: {stripped_path}")
    
    resolver = get_resolver()
    try:
        match = resolver.resolve(stripped_path)
        print(f"Resolved to: {match.func} with args {match.args} and kwargs {match.kwargs}")
        
        # Test if the view can actually find the file
        from django.views.static import serve
        try:
            resp = match.func(request, **match.kwargs)
            print(f"View status code: {resp.status_code}")
            if resp.status_code != 200:
                # Check real file existence
                root = match.kwargs.get('document_root')
                rel_path = match.kwargs.get('path')
                full_path = os.path.join(root, rel_path)
                print(f"Physical file exists: {os.path.exists(full_path)}")
                print(f"Checking path: {full_path}")
        except Exception as e:
            print(f"View execution error: {e}")
            
    except Exception as e:
        print(f"Resolution error: {e}")
    
    print("\n--- URL Patterns ---")
    resolver = get_resolver()
    for p in resolver.url_patterns:
        if hasattr(p, 'pattern') and 'static' in str(p.pattern):
            print(f"Pattern: {p.pattern} -> {p.callback}")

if __name__ == "__main__":
    audit()
