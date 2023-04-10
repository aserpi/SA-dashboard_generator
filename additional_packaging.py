import shutil
import subprocess
import sys
from pathlib import Path


def additional_packaging(ta_name):
    output_path = Path("output") / ta_name
    shutil.copy(Path("LICENSE.md"), output_path)
    shutil.copy(Path("README.md"), output_path)

    subprocess.check_call([sys.executable, "-m", "pip", "install", "charset-normalizer",
                           "--no-binary=:all:", f"--target={output_path / 'lib'}", "--upgrade"])
