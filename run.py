"""
Start the server with this script on Windows instead of calling uvicorn directly.
The event loop policy must be set BEFORE uvicorn calls asyncio.run(), which happens
before app.main is imported — making the policy in main.py too late to take effect.
"""
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
