import subprocess

def run_powershell_command(command: str) -> str:
    """
    Runs a PowerShell command and returns its output as a string.
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
