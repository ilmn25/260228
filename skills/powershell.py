import subprocess


def run_powershell_command(command: str) -> str:
    r"""
    Runs a PowerShell command and returns its output as a string.
    The user's directory is C:\Users\user
    Commonly mentioned directories include: 
    - Desktop: C:\Users\user\Desktop
    - Downloads: C:\Users\user\Downloads
    Args:
        command (str): The PowerShell command to execute.
    Returns:
        str: The output from the command.
    """
    proc = subprocess.Popen(
        ["powershell", "-Command", "-NoProfile", command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        stdout, stderr = proc.communicate(timeout=6)
    except subprocess.TimeoutExpired:
        return "Command is running."

    if proc.returncode != 0:
        return f"Error: {stderr.strip()}"

    return stdout.strip()
