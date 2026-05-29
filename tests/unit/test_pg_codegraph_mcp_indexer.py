from tools.pg_codegraph_mcp.indexer import extract_javascript, extract_python


def test_extract_python_symbols_and_calls():
    source = '''
class Service:
    def run(self, value):
        return helper(value)

def helper(value):
    return str(value)
'''

    symbols = extract_python(source)
    by_qualname = {s.qualname: s for s in symbols}

    assert by_qualname["Service"].kind == "class"
    assert by_qualname["Service.run"].kind == "method"
    assert by_qualname["helper"].kind == "function"
    assert ("helper", 4) in by_qualname["Service.run"].calls


def test_extract_python_imports_variables_routes_and_extends():
    source = '''
from django.urls import path
VALUE = 1

class Child(Base):
    pass

urlpatterns = [
    path("hello/", view),
]
'''

    symbols = extract_python(source)
    kinds = {s.name: s.kind for s in symbols}

    assert kinds["django.urls"] == "import"
    assert kinds["VALUE"] == "variable"
    assert kinds["urlpatterns"] == "variable"
    assert kinds["hello/"] == "route"
    assert ("Base", 5) in next(s for s in symbols if s.name == "Child").extends


def test_extract_javascript_symbols_and_calls():
    source = '''
import api from "./api.js";
const baseUrl = "/doc/";
function load() {
  return apiurl("doc/list/");
}
'''

    symbols = extract_javascript(source, module_prefix="static.app")
    kinds = {s.name: s.kind for s in symbols}
    load = next(s for s in symbols if s.name == "load")

    assert kinds["api.js"] == "import"
    assert kinds["baseUrl"] == "constant"
    assert kinds["load"] == "function"
    assert "doc/list/" not in kinds
    assert ("apiurl", 5) in load.calls
