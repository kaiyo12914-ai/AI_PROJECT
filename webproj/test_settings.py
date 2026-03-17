from .settings import *
PORTAL_ACL_ENABLED = False
CSRF_TRUSTED_ORIGINS = ['http://127.0.0.1:8001']
MIDDLEWARE = [m for m in MIDDLEWARE if 'CsrfViewMiddleware' not in m]
