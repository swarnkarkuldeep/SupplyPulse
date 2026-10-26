"""Optional: download the DataCo dataset with the Kaggle CLI into data/raw/.

Needs a Kaggle API token (``%USERPROFILE%\\.kaggle\\kaggle.json`` or the KAGGLE_USERNAME / KAGGLE_KEY
environment variables) and ``pip install kaggle``. If you have no token, download the files by hand from
the dataset page and put them in data/raw/ (see the README).

Usage:  python scripts/download_data.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

DATASET = "shashwatwork/dataco-smart-supply-chain-for-big-data-analysis"
KEEP = ("DataCoSupplyChainDataset.csv", "DescriptionDataCoSupplyChain.csv")  # tokenized_access_logs.csv is not needed
RAW = Path(__file__).resolve().parents[1] / "data" / "raw"


def have_credentials() -> bool:
    """True if a Kaggle token file or the environment variables exist."""
    import os

    token = Path.home() / ".kaggle" / "kaggle.json"
    return token.exists() or bool(os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY"))


def main() -> int:
    """Download and unpack the two files the pipeline needs. Returns a process exit code."""
    if all((RAW / name).exists() for name in KEEP):
        print("data/raw/ already has both files; nothing to do.")
        return 0
    if shutil.which("kaggle") is None:
        print("The Kaggle CLI is not installed. Run `pip install kaggle`, or download the files by hand.")
        return 1
    if not have_credentials():
        print("No Kaggle credentials found (kaggle.json or KAGGLE_USERNAME/KAGGLE_KEY). Download by hand instead.")
        return 1
    RAW.mkdir(parents=True, exist_ok=True)
    cmd = ["kaggle", "datasets", "download", "-d", DATASET, "-p", str(RAW), "--unzip"]
    code = subprocess.run(cmd, check=False).returncode
    for extra in RAW.glob("tokenized_access_logs.csv"):
        extra.unlink()
    return code


if __name__ == "__main__":
    sys.exit(main())
