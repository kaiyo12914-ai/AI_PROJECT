
import re
def test_middleware_replacement():
      html = '<script defer src="/static/comment/js/performance.js"></script>'
      pattern = r'(<[^>]+?\s)(href|src)=["\'](/static/)'             
      replacement = lambda m: f"{m.group(1)}{m.group(2)}=\"{m.group(3).replace('/static/', 'static/')}"            
      html = re.sub(pattern, replacement, html)
      print(html)