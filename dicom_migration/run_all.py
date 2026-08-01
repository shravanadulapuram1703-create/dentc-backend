import subprocess
import sys
import time
from pathlib import Path

scripts = [
    "01_scan.py",
    "02_upload.py",
    "03_load_staging.py",
    "04_reconcile.py",
    "05_promote.py",
    "06_derivatives.py",
]

base_dir = Path(__file__).parent

for script in scripts:
    print(f"\n{'=' * 70}")
    print(f"Running {script}...")
    print(f"{'=' * 70}")

    start = time.time()

    result = subprocess.run(
        [sys.executable, str(base_dir / script)],
        check=False
    )

    elapsed = time.time() - start
    print(f"Finished {script} in {elapsed:.1f} seconds")

    if result.returncode != 0:
        print(f"\n❌ {script} failed.")
        sys.exit(result.returncode)

print("\n🎉 Migration completed successfully!")