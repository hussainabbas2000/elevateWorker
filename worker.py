import time
import subprocess
from supabase import create_client
from dotenv import load_dotenv
import os

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_ANON_KEY
)

def poll():
    print("🔎 Polling for new call jobs...")
    res = (
        supabase
        .table("voice_call_jobs")
        .select("*")
        .eq("status", 'pending')
        .limit(1)
        .execute()
    )

    if not res.data:
        return

    job = res.data[0]
    phone = job["phone"]

    print(f"📞 Calling {phone}")

    try:
        # Capture output in real-time
        process = subprocess.Popen(
            ["cartesia", "call", phone],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        # Print logs as they come in
        for line in process.stdout:
            print(line, end='')
        
        process.wait()
        
        if process.returncode == 0:
            supabase.table("voice_call_jobs").update({
                "status": "completed"
            }).eq("id", job["id"]).execute()
            print("✅ Call completed")
        else:
            print(f"❌ Call failed with code {process.returncode}")

    except Exception as e:
        print(f"❌ Error: {e}")

while True:
    poll()
    time.sleep(3)