from django.utils.deprecation import MiddlewareMixin
import re

class StaticPathMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        # 替換所有 <link> 和 <script> 標籤中的 /static/ 為 static/
        if response.get('Content-Type', '').startswith('text/html'):
            html = response.content.decode('utf-8')            
            pattern = r'(<[^>]+?\s)(href|src)=["\'](/static/)'             
            replacement = lambda m: f"{m.group(1)}{m.group(2)}=\"{m.group(3).replace('/static/', '../static/')}"             
            html = re.sub(pattern, replacement, html)            
            response.content = html.encode('utf-8')
        return response