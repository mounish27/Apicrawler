import pytest
from extraction.endpoint_detector import EndpointDetector


SAMPLE_HTML = """
<html><body>
<h2>Get User</h2>
<p>GET /api/v1/users/{id}</p>
<h2>Create Employee</h2>
<pre>POST /api/v1/employees</pre>
<table>
  <tr><th>Method</th><th>Path</th><th>Description</th></tr>
  <tr><td>DELETE</td><td>/api/v1/users/{id}</td><td>Delete user</td></tr>
</table>
</body></html>
"""

BADGE_HTML = """
<html><body>
<div>
  <span class="method">GET</span>
  <code>/api/v1/orders</code>
</div>
</body></html>
"""


def test_detects_inline_endpoints():
    det = EndpointDetector()
    results = det.detect(SAMPLE_HTML, "https://example.com")
    methods = {(ep["method"], ep["path"]) for ep in results}
    assert ("GET", "/api/v1/users/{id}") in methods
    assert ("POST", "/api/v1/employees") in methods
    assert ("DELETE", "/api/v1/users/{id}") in methods


def test_detects_badge_pattern():
    det = EndpointDetector()
    results = det.detect(BADGE_HTML, "https://example.com")
    paths = [ep["path"] for ep in results]
    assert "/api/v1/orders" in paths


def test_no_duplicates():
    det = EndpointDetector()
    html = "<p>GET /api/users</p><p>GET /api/users</p>"
    results = det.detect(html, "https://example.com")
    paths = [ep["path"] for ep in results]
    assert paths.count("/api/users") == 1
