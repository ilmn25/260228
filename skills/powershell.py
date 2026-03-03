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
    try:
        completed = subprocess.run(
            ["powershell", "-Command", command],
            capture_output=True,
            text=True,
            check=True
        )
        return completed.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"Error: {e.stderr.strip()}"
