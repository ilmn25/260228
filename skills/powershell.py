import subprocess
import threading
import time
from typing import List


def run_powershell_command(command: str) -> str:
    r"""
    Runs a PowerShell command and returns its output as a string.
    The user's directory is C:\Users\user
    Commonly mentioned directories include: 
    - Desktop: C:\Users\user\Desktop
    - Downloads: C:\Users\user\Downloads
    Args:
        command (str): The PowerShell command to execute, use a verbose format to get output.
    Returns:
        str: The output from the command.
    """
    proc = subprocess.Popen(
        ["powershell", "-NoProfile", "-Command", command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1  # line-buffered
    )

    output_lines: List[str] = []
    error_lines: List[str] = []
    last_activity = time.time()

    def reader(pipe, collector):
        nonlocal last_activity
        for line in iter(pipe.readline, ''):
            collector.append(line)
            last_activity = time.time()
        pipe.close()

    # Start threads to read stdout and stderr
    t_out = threading.Thread(target=reader, args=(proc.stdout, output_lines), daemon=True)
    t_err = threading.Thread(target=reader, args=(proc.stderr, error_lines), daemon=True)
    t_out.start()
    t_err.start()

    # Monitor activity
    while proc.poll() is None:
        if time.time() - last_activity > 3:
            proc.terminate()
            break
        time.sleep(0.1)

    # Ensure threads finish
    t_out.join(timeout=1)
    t_err.join(timeout=1)

    if proc.returncode not in (0, None):
        return "Error: " + "".join(error_lines).strip()

    output = "".join(output_lines).strip()
    if output == "":
        return "Finished without output or error."
    return output


def open_with_powershell(target: str) -> str:
    r"""
    Opens a website URL or executable/shortcut.
    Args:
        target (str): URL or filesystem path to open.
    Returns:
        str: The output from the command.
    """
    command = f"Start-Process '{target}'"
    return run_powershell_command(command)

