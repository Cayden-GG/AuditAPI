import os
import shutil
import subprocess
from pathlib import Path

# Paths
# BASE_DIR = Path("/var/www/valvanta-audit")
BASE_DIR = Path("/home/caydeng/Desktop/Code/Valvanta/AuditAPI")
RESULTS_DIR = BASE_DIR / "audit_results"
LOGS_DIR = BASE_DIR / "logs"

def clean_up_service_files():
    """Safely removes all files in results and logs without using the shell."""
    for target_dir in [RESULTS_DIR, LOGS_DIR]:
        if not target_dir.exists():
            continue
            
        # Instead of 'rm -rf *', we empty the directory contents
        for item in target_dir.iterdir():
            try:
                if item.is_file() or item.is_symlink():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            except Exception as e:
                print(f"Error deleting {item}: {e}")
                
    print("Service files: Audit results and logs cleared.")

def clean_up_system_files():
    """Cleans up the massive Lighthouse/Chrome temp files and vacuums logs."""
    
    # 1. Clear Lighthouse Temp folders (The 33GB preventer)
    # This specifically targets the folders Chrome creates in /tmp
    temp_path = Path("/tmp")
    for folder in temp_path.glob("lighthouse.*"):
        try:
            shutil.rmtree(folder)
        except Exception:
            pass # Usually means the file is still in use

    # 2. Vacuum System Logs (Keep only the last 2 days)
    # This prevents your disk from slowly filling with journald logs
    subprocess.run(["sudo", "journalctl", "--vacuum-time=2d"], capture_output=True)

    print("System files: /tmp/lighthouse.* cleared and logs vacuumed.")

# --- Trigger both ---
def run_full_cleanup():
    clean_up_service_files()
    clean_up_system_files()
