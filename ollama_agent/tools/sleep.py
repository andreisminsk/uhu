"""Sleep tool — wait for a specified number of seconds.

Used primarily to wait between job_submit and job_result polling.
Auto-approved (no side effects). Prints a countdown so the user
can see the agent is waiting, not frozen.
"""

import time
import sys


class SleepTool:
    name = "sleep"
    description = "Wait for a specified number of seconds (max 600)"
    system_prompt = """## sleep

Wait for a specified number of seconds. Use this when you need to wait for a
background job to finish, a server to start, or a rate limit to clear.
Max 600 seconds (10 minutes). Auto-approved — no confirmation needed.

Primary use case: after job_submit, sleep for the estimated task duration,
then use job_list to check status and job_result to retrieve output.

Parameters (JSON object):
- seconds (integer, required): Number of seconds to wait (max 600)

Examples:
- {"seconds": 30}
- {"seconds": 90}"""
    parameters = {
        "seconds": {"type": "integer", "required": True, "description": "Seconds to wait (max 600)"},
    }
    do_not_truncate_observations = True

    def execute(self, params, workdir=None):
        seconds = params.get("seconds", 0)
        try:
            seconds = int(seconds)
        except (ValueError, TypeError):
            return "Error: 'seconds' must be an integer."
        if seconds <= 0:
            return "Error: 'seconds' must be positive."
        if seconds > 600:
            seconds = 600

        try:
            elapsed = 0
            while elapsed < seconds:
                remaining = seconds - elapsed
                # Print countdown every 15s, or at the start
                if elapsed % 15 == 0 or remaining <= 5:
                    sys.stdout.write(f"\r[Waiting... {remaining}s remaining]    ")
                    sys.stdout.flush()
                chunk = min(1, remaining)
                time.sleep(chunk)
                elapsed += chunk
            sys.stdout.write("\r[Done waiting]                        \n")
            sys.stdout.flush()
        except KeyboardInterrupt:
            sys.stdout.write("\r[Interrupted]                        \n")
            sys.stdout.flush()
            return f"Interrupted after {elapsed}s."

        return f"Slept {seconds}s. Continuing."