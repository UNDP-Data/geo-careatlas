# from mitmproxy import http
# import re
    

# def request(flow: http.HTTPFlow) -> None:
#     # Match the 8-character hex SID (your uuid.uuid4().hex[:8])
#     match = re.search(r"/edit/([0-9a-f]{8})(.*)", flow.request.path)
    
#     if match:
#         sid = match.group(1)
#         # 1. Get the port from the cookie
#         port_str = flow.request.cookies.get(f"marimo_port_{sid}")
        
#         if port_str:
#             try:
#                 port_num = int(port_str)
#                 target_host = 'api'  # Container name in Docker Compose
                
#                 # 2. Reroute the flow
#                 flow.request.host = target_host
#                 flow.request.port = port_num
                
#                 # 3. Marimo Security/Host Headers
#                 # Marimo validates the Host and Origin headers for CSRF protection.
#                 # We set these to the internal address so the kernel accepts the request.
#                 flow.request.headers["Host"] = f"{target_host}:{port_num}"
                
#                 # For WebSockets and CORS, the Origin header is vital
#                 if "Origin" in flow.request.headers:
#                     flow.request.headers["Origin"] = f"http://{target_host}:{port_num}"
                
                
#             except ValueError:
#                 # Handle corrupted cookie data
#                 flow.response = http.Response.make(400, b"Invalid session port format.")
#         else:
#             # 5. Handle missing cookie
#             # If it's a static asset request, we might want to return a 404.
#             # If it's the main page load, we redirect back to the session explorer.
#             if flow.request.path.endswith(sid + "/"):
#                 flow.response = http.Response.make(
#                     307, b"", {"Location": "/"}
#                 )
#             else:
#                 flow.response = http.Response.make(404, b"Marimo session port cookie expired or missing.")

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


def response(flow: http.HTTPFlow) -> None:
    # Match the main HTML page load for the session to inject the script.
    # We look for the exact SID path (with or without trailing slash) and ensure it's HTML.
    if re.search(r"/edit/[0-9a-f]{8}/?$", flow.request.path) and "text/html" in flow.response.headers.get("Content-Type", ""):
        
        js_injection = b"""
        <script>
            const checkExist = setInterval(() => {
            const firstCell = document.querySelector('marimo-cell, [id^="cell-"]');
                
                if (firstCell) {
                    console.log("Mitmproxy: Cell found in DOM.");
                    clearInterval(checkExist); 
                    
                    // 1. Simulate a mouse hover to force React to render the hidden UI buttons
                    firstCell.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
                    firstCell.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                    
                    setTimeout(() => {
                        // 2. Search using Marimo's internal test IDs and broader selectors
                        const runButton = firstCell.querySelector('[data-testid="run-button"], button[title*="run" i], button[aria-label*="run" i]'); 
                        
                        if (runButton) {
                            runButton.click();
                            console.log("Mitmproxy: Successfully run first cell.");
                        } else {
                            console.log("Mitmproxy: Button still hidden. Firing Shift+Enter shortcut.");
                            
                            // 3. Ultimate Fallback: Target the CodeMirror editor and press Shift+Enter
                            const editor = firstCell.querySelector('.cm-content, [contenteditable="true"]');
                            if (editor) {
                                editor.focus();
                                editor.dispatchEvent(new KeyboardEvent('keydown', {
                                    key: 'Enter', 
                                    code: 'Enter', 
                                    shiftKey: true, 
                                    bubbles: true,
                                    cancelable: true
                                }));
                                console.log("Mitmproxy: Shift+Enter dispatched to the kernel.");
                            } else {
                                console.log("Mitmproxy: Could not find the code editor.");
                            }
                        }
                    }, 150); // Give React 150ms to react to the hover event
                }
            }, 250);

            // Safety cutoff
            setTimeout(() => {
                clearInterval(checkExist);
            }, 10000);
        </script>
        """
        
        # Inject the script right before the closing body tag
        if flow.response.content and b"</body>" in flow.response.content:
            flow.response.content = flow.response.content.replace(b"</body>", js_injection + b"</body>")