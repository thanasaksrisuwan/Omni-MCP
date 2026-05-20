import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# CSEA-Compliant Fallback CLI for Omni-MCP
# Use this when Gemini/Codex hit token limits to perform manual discovery or small tasks.

PROJECT_ROOT = Path(__file__).resolve().parents[1]

def run_csea(command):
    """Run a command through the CSEA policy enforcer."""
    print(f"[*] Executing via CSEA: {command}")
    cmd = [sys.executable, str(PROJECT_ROOT / "scripts" / "csea_policy_enforcer.py"), "--run", command]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        data = json.loads(result.stdout)
        if data.get("status") == "ok":
            print(data.get("stdout"))
        else:
            print(f"[!] CSEA Blocked/Failed: {data.get('reason')}")
            print(data.get("stderr"))
    else:
        print(f"[!] Execution failed (Exit {result.returncode})")
        print(result.stderr)

def show_status():
    """Print the current project status from .agent_bus."""
    status_file = PROJECT_ROOT / ".agent_bus" / "status" / "current.md"
    if status_file.exists():
        print(status_file.read_text(encoding='utf-8'))
    else:
        print("[!] .agent_bus/status/current.md not found.")

def main():
    parser = argparse.ArgumentParser(description='Omni-MCP Fallback CLI')
    parser.add_argument('command', nargs='?', help='Command to run via CSEA (e.g., git status)')
    parser.add_argument('--status', action='store_true', help='Show project status')
    
    args = parser.parse_args()
    
    if args.status:
        show_status()
    elif args.command:
        run_csea(args.command)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
