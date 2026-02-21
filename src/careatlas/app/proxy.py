from mitmproxy import http
import re
    

def request(flow: http.HTTPFlow) -> None:
    # Match the 8-character hex SID (your uuid.uuid4().hex[:8])
    match = re.search(r"/edit/([0-9a-f]{8})(.*)", flow.request.path)
    
    if match:
        sid = match.group(1)
        # 1. Get the port from the cookie
        port_str = flow.request.cookies.get(f"marimo_port_{sid}")
        
        if port_str:
            try:
                port_num = int(port_str)
                target_host = 'api'  # Container name in Docker Compose
                
                # 2. Reroute the flow
                flow.request.host = target_host
                flow.request.port = port_num
                
                # 3. Marimo Security/Host Headers
                # Marimo validates the Host and Origin headers for CSRF protection.
                # We set these to the internal address so the kernel accepts the request.
                flow.request.headers["Host"] = f"{target_host}:{port_num}"
                
                # For WebSockets and CORS, the Origin header is vital
                if "Origin" in flow.request.headers:
                    flow.request.headers["Origin"] = f"http://{target_host}:{port_num}"
                
                
            except ValueError:
                # Handle corrupted cookie data
                flow.response = http.Response.make(400, b"Invalid session port format.")
        else:
            # 5. Handle missing cookie
            # If it's a static asset request, we might want to return a 404.
            # If it's the main page load, we redirect back to the session explorer.
            if flow.request.path.endswith(sid + "/"):
                flow.response = http.Response.make(
                    307, b"", {"Location": "/"}
                )
            else:
                flow.response = http.Response.make(404, b"Marimo session port cookie expired or missing.")
