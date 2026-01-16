import time
import subprocess
import os
import shutil
from supabase import create_client

print("🔍 Booting worker...")

cartesia_path = shutil.which("cartesia") or "/root/.cartesia/bin/cartesia"

print("Using cartesia at:", cartesia_path)

if not os.path.exists(cartesia_path):
    raise RuntimeError("❌ Cartesia CLI not found")

subprocess.run([cartesia_path, "--version"], check=True)

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

print("CARTESIA_API_KEY set?", bool(os.getenv("CARTESIA_API_KEY")))

def poll():
    print("🔎 Polling for new call jobs...")

    res = (
        supabase.table("voice_call_jobs")
        .select("*")
        .eq("status", "pending")
        .limit(1)
        .execute()
    )

    if not res.data:
        return

    job = res.data[0]
    phone = job["phone"]

    print(f"📞 Calling {phone}")

    process = subprocess.Popen(
        [cartesia_path, "call", phone],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    for line in process.stdout:
        print(line, end="")

    process.wait()

    if process.returncode == 0:
        supabase.table("voice_call_jobs").update(
            {"status": "completed"}
        ).eq("id", job["id"]).execute()
        print("✅ Call completed")
    else:
        print(f"❌ Call failed ({process.returncode})")


if __name__ == "__main__":
    while True:
        try:
            poll()
            time.sleep(3)
        except Exception as e:
            print(f"🔥 Worker crashed: {e}")
            time.sleep(5)
