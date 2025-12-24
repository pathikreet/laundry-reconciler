import sys
from pathlib import Path
import pandas as pd

files = [
    Path(r"d:\Pathikreet\Workspace\Laundry-Reconciler\laundry-reconciler-docs\SalesAndDeliveryCRMExport-November.xlsx"),
    Path(r"d:\Pathikreet\Workspace\Laundry-Reconciler\laundry-reconciler-docs\DailyCashRegister.xlsx"),
]

for f in files:
    print("FILE:", f)
    if not f.exists():
        print("  Not found\n")
        continue
    try:
        xls = pd.ExcelFile(f)
    except Exception as e:
        print("  Failed to open:", e, "\n")
        continue
    print("  Sheets:", xls.sheet_names)
    for s in xls.sheet_names:
        try:
            df = pd.read_excel(xls, sheet_name=s, nrows=5)
        except Exception as e:
            print(f"  Sheet '{s}' read error: {e}")
            continue
        print(f"  --- Sheet: {s}")
        print("  Columns:", list(df.columns))
        print(df.to_csv(index=False))
    print()