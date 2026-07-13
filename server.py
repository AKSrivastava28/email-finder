import json
import asyncio
import os
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

# Import helper functions from our existing email_finder script
from email_finder import clean_domain, generate_permutations, get_mx_records, verify_smtp, check_hunter_io

app = FastAPI(title="Email Finder API")

# Enable CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permits access from Vite local server on Port 5173
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/stream-verify")
def stream_verify(name: str = Query(...), domain: str = Query(...)):
    """
    Streams email verification progress steps in real time via Server-Sent Events (SSE).
    """
    async def event_generator():
        # Step 1: Start
        yield f"data: {json.dumps({'event': 'start', 'message': f'Starting check for {name}...'})}\n\n"
        await asyncio.sleep(0.2)
        
        # Step 2: Domain sanitization
        cleaned_domain = clean_domain(domain)
        yield f"data: {json.dumps({'event': 'cleaned', 'domain': cleaned_domain})}\n\n"
        await asyncio.sleep(0.2)
        
        # Step 3: Permutation generation
        perms = generate_permutations(name, cleaned_domain)
        yield f"data: {json.dumps({'event': 'permutations', 'permutations': perms})}\n\n"
        await asyncio.sleep(0.2)
        
        # Step 4: MX record resolution
        yield f"data: {json.dumps({'event': 'mx_start', 'message': f'Resolving DNS MX records for {cleaned_domain}...'})}\n\n"
        mxs = get_mx_records(cleaned_domain)
        if not mxs:
            yield f"data: {json.dumps({'event': 'error', 'message': f'No mail servers configured for {cleaned_domain}'})}\n\n"
            return
            
        mx_host = mxs[0]
        yield f"data: {json.dumps({'event': 'mx_found', 'mx_host': mx_host})}\n\n"
        await asyncio.sleep(0.2)
        
        # Load API Key if available
        hunter_key = None
        if os.path.exists(".env"):
            try:
                with open(".env", "r") as f:
                    for line in f:
                        if line.strip().startswith("HUNTER_API_KEY="):
                            hunter_key = line.strip().split("=", 1)[1].strip().strip("'\"")
            except Exception:
                pass
        
        # Step 5: Check catch-all mailbox status
        yield f"data: {json.dumps({'event': 'catchall_start', 'message': 'Testing domain catch-all status...'})}\n\n"
        catch_all_test_email = f"verify_catch_all_test_123456@{cleaned_domain}"
        catch_all_status = verify_smtp(catch_all_test_email, mx_host)
        
        # Case A: Network or Timeout error (typically Port 25 blocked)
        if "error" in catch_all_status:
            yield f"data: {json.dumps({'event': 'port_blocked', 'hunter_key_present': bool(hunter_key)})}\n\n"
            if not hunter_key:
                yield f"data: {json.dumps({'event': 'error', 'message': f'SMTP handshake failure: {catch_all_status}'})}\n\n"
                return
                
            # Run Hunter.io database checking loop
            for email in perms:
                yield f"data: {json.dumps({'event': 'testing_db', 'email': email})}\n\n"
                await asyncio.sleep(0.1) # tiny delay to let UI render the step
                status = check_hunter_io(email, hunter_key)
                
                if status == "valid":
                    yield f"data: {json.dumps({'event': 'success', 'email': email, 'method': 'hunter'})}\n\n"
                    return
            yield f"data: {json.dumps({'event': 'fail', 'message': 'No verified email found in Hunter.io database.'})}\n\n"
            return

        # Case B: Domain is Catch-All
        if catch_all_status == "valid":
            yield f"data: {json.dumps({'event': 'catchall_detected', 'hunter_key_present': bool(hunter_key)})}\n\n"
            if not hunter_key:
                return
                
            # Run Hunter.io database checking loop
            for email in perms:
                yield f"data: {json.dumps({'event': 'testing_db', 'email': email})}\n\n"
                await asyncio.sleep(0.1)
                status = check_hunter_io(email, hunter_key)
                
                if status == "valid":
                    yield f"data: {json.dumps({'event': 'success', 'email': email, 'method': 'hunter'})}\n\n"
                    return
            yield f"data: {json.dumps({'event': 'fail', 'message': 'No verified email found in Hunter.io database.'})}\n\n"
            return

        # Case C: Domain is normal (Not catch-all) - verify each permutation
        yield f"data: {json.dumps({'event': 'verify_loop_start', 'message': 'Domain is not catch-all. Starting verification...'})}\n\n"
        for email in perms:
            yield f"data: {json.dumps({'event': 'testing_email', 'email': email})}\n\n"
            await asyncio.sleep(0.1)
            status = verify_smtp(email, mx_host)
            
            if status == "valid":
                yield f"data: {json.dumps({'event': 'success', 'email': email, 'method': 'smtp'})}\n\n"
                return
                
        yield f"data: {json.dumps({'event': 'fail', 'message': 'No working email address found (all combinations bounced).'})}\n\n"
        
    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
