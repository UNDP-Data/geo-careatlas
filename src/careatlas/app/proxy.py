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
                
                # 4. Pass-through Auth Headers
                # Ensure the kernel knows who is talking to it (from oauth2-proxy)
                # flow.request.headers["X-User-Email"] = flow.request.headers.get("x-auth-request-email", "Guest")

            except ValueError:
                # Handle corrupted cookie data
                flow.response = http.Response.make(400, b"Invalid session port format.")
        else:
            # 5. Handle missing cookie
            # If it's a static asset request, we might want to return a 404.
            # If it's the main page load, we redirect back to the session explorer.
            if flow.request.path.endswith(sid + "/"):
                flow.response = http.Response.make(
                    307, b"", {"Location": "/explorer/"}
                )
            else:
                flow.response = http.Response.make(404, b"Marimo session port cookie expired or missing.")
# def request(flow: http.HTTPFlow) -> None:
    
#     # print(f'flow', flow.request.path)
#     # New Regex: Only looks for the SID, doesn't expect a PORT in the path
#     #match = re.search(r"/edit/([^/]+)(.*)", flow.request.path)
#     match = re.search(r"/edit/([0-9a-f]{8})(.*)", flow.request.path)
#     #match = re.search(r"/edit/(\d+)/([0-9a-f]{32})(.*)", flow.request.path)
#     # print('match', match)
#     if match:
#         sid = match.group(1)
#         rest = match.group(2)
        
#         # 1. Look for the Identity Headers from Auth-Proxy
#         # user = flow.request.headers.get("x-auth-request-user")
#         # email = flow.request.headers.get("x-auth-request-email")
        
#         # # 1. Check Identity (from Auth-Proxy)
#         # user = flow.request.headers.get("x-auth-request-user")
#         # if not user:
#         #      # If no user, they bypassed the proxy. 
#         #      # Let's send a 403 instead of a 307 to stop the loop.
#         #      flow.response = http.Response.make(403, b"Auth Header Missing")
#         #      return
#         port_str = flow.request.cookies.get(f"marimo_port_{sid}")
#         if port_str:
#             port_num = int(port_str)
#             target_host = 'api'  #"127.0.0.1" in aks
#             # 2. Reroute to the internal Pod address
#             flow.request.host = target_host
#             flow.request.port = port_num
            
#             # For now, ensure these exist so the kernel doesn't 401/403:
#             # flow.request.headers["x-auth-request-user"] = user
#             # flow.request.headers["x-auth-request-email"] = email
            
#             # 3. Clean headers (Marimo expects to see itself on 127.0.0.1)
#             flow.request.headers["Host"] = f"{target_host}:{port_num}"
#             flow.request.headers["Origin"] = f"http://{target_host}:{port_num}"
            
#             # 4. Path remains clean (/edit/sid/...)
#             # No need to strip the port because it wasn't there!
#         else:
#             # If no cookie, we can't route. Send back to the 'open' logic.
#             # We don't have the notebook name here, so we redirect to a general re-sync
#             flow.response = http.Response.make(307, b"", {"Location": f"/sessions"})