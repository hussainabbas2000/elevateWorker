import time
import subprocess
from supabase import create_client
import os

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

def poll():
    print("🔎 Polling for new call jobs...")
    subprocess.run(["cartesia", "--version"], check=True)
    print("Cartesia home:", os.environ.get("CARTESIA_HOME"))
    print("Files:", os.listdir("/app/.cartesia"))
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
        process = subprocess.Popen(
            ["cartesia", "call", phone],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        print("Here", process)
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

if __name__ == "__main__":
    while True:
        try:
            poll()
            time.sleep(3)
        except Exception as e:
            print(f"🔥 Worker crashed: {e}, restarting in 5s...")
            time.sleep(5)
