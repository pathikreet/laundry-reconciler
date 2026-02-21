import sys
import argparse
from pathlib import Path
import pandas as pd

# ANSI color codes
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_header(msg):
    print(f"{Colors.HEADER}{Colors.BOLD}{msg}{Colors.ENDC}")

def print_info(msg):
    print(f"{Colors.CYAN}{msg}{Colors.ENDC}")

def print_success(msg):
    print(f"{Colors.GREEN}{msg}{Colors.ENDC}")

def print_error(msg):
    print(f"{Colors.FAIL}{msg}{Colors.ENDC}")

def inspect_file(filepath: Path, nrows: int):
    print_header(f"\n📂 Inspecting: {filepath}")

    if not filepath.exists():
        print_error(f"  ❌ File not found: {filepath}")
        return

    try:
        xls = pd.ExcelFile(filepath)
    except Exception as e:
        print_error(f"  ❌ Failed to open file: {e}")
        return

    print_info(f"  📄 Sheets found: {xls.sheet_names}")

    for s in xls.sheet_names:
        print(f"\n  {Colors.BLUE}--- Sheet: {s} ---{Colors.ENDC}")
        try:
            df = pd.read_excel(xls, sheet_name=s, nrows=nrows)
        except Exception as e:
            print_error(f"    ❌ Error reading sheet '{s}': {e}")
            continue

        print(f"    {Colors.BOLD}Columns:{Colors.ENDC} {list(df.columns)}")
        print(f"    {Colors.BOLD}Preview ({nrows} rows):{Colors.ENDC}")
        # Print the dataframe as a string but indent it
        df_str = df.to_string(index=False)
        for line in df_str.split('\n'):
            print(f"      {line}")

def main():
    parser = argparse.ArgumentParser(
        description="🎨 Palette's Excel Inspector: A friendly tool to peek into Excel files without opening Excel.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example:\n  python tools/inspect_xlsx.py sample/data.xlsx --rows 10"
    )

    parser.add_argument('files', metavar='FILE', type=Path, nargs='+', help='Excel file(s) to inspect')
    parser.add_argument('--rows', '-n', type=int, default=5, help='Number of rows to preview (default: 5)')

    args = parser.parse_args()

    for f in args.files:
        inspect_file(f, args.rows)

if __name__ == "__main__":
    main()
