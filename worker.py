import os
import time
import subprocess
import signal
from supabase import create_client
# from dotenv import load_dotenv

# load_dotenv()
# ---------------- CONFIG ----------------

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]
CARTESIA_API_KEY = os.environ["CARTESIA_API_KEY"]

GOODBYE_PHRASES = [
    "bye",
    "goodbye",
    "talk to you later",
    "see you",
    "thanks, bye",
]

# ----------------------------------------

supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def start_call(phone_number: str):
    env = os.environ.copy()
    env["CARTESIA_API_KEY"] = CARTESIA_API_KEY

    print(f"📞 Calling {phone_number}")

    return subprocess.Popen(
        ["cartesia", "call", phone_number],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )


def should_end_call(line: str) -> bool:
    lower = line.lower()
    return any(phrase in lower for phrase in GOODBYE_PHRASES)


def poll():
    print("🔎 Polling for new call jobs...")

    while True:
        res = (
            supabase
            .table("voice_call_jobs")
            .select("*")
            .eq("status", "pending")
            .limit(1)
            .execute()
        )

        if not res.data:
            time.sleep(5)
            continue

        job = res.data[0]
        phone = job["phone"]

        # mark as processing
        supabase.table("voice_call_jobs").update(
            {"status": "processing"}
        ).eq("id", job["id"]).execute()

        proc = start_call(phone)

        try:
            for line in proc.stdout:
                print(line.strip())

                if should_end_call(line):
                    print("👋 Goodbye detected — ending call")
                    proc.send_signal(signal.SIGINT)
                    break

        except Exception as e:
            print("⚠️ Error during call:", e)

        finally:
            if proc.poll() is None:
                proc.terminate()

            supabase.table("voice_call_jobs").update(
                {"status": "completed"}
            ).eq("id", job["id"]).execute()

        time.sleep(2)


if __name__ == "__main__":
    poll()
