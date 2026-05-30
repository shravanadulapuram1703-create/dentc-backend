import os
import pandas as pd
from dateutil.parser import parse

ROOT_FOLDER = r"./data_dump"   # change this
OUTPUT_FILE = "data_dictionary.csv"
SAMPLE_ROWS = 100


def infer_type(series):
    series = series.dropna().astype(str)

    if series.empty:
        return "UNKNOWN"

    def is_int(x):
        try:
            int(x)
            return True
        except:
            return False

    def is_float(x):
        try:
            float(x)
            return True
        except:
            return False

    def is_date(x):
        try:
            parse(x, fuzzy=False)
            return True
        except:
            return False

    if series.apply(is_int).all():
        return "INT"

    if series.apply(is_float).all():
        return "FLOAT"

    if series.apply(is_date).all():
        return "DATE"

    if series.str.lower().isin(["true", "false", "0", "1", "yes", "no"]).all():
        return "BOOLEAN"

    return f"VARCHAR({series.str.len().max()})"


def read_file(file_path):
    try:
        return pd.read_csv(file_path, sep=",", nrows=SAMPLE_ROWS)
    except Exception as e:
        print(f"❌ Failed to read {file_path}: {e}")
        return None


def scan(root_folder):
    tables = {}

    for root, _, files in os.walk(root_folder):
        is_root = os.path.abspath(root) == os.path.abspath(root_folder)

        for file in files:
            if not file.lower().endswith(".txt"):
                continue

            full_path = os.path.join(root, file)

            # 🔑 Table naming logic
            if is_root:
                table_name = os.path.splitext(file)[0]   # file name
            else:
                table_name = os.path.basename(root)      # folder name

            print(f"📄 Processing: {full_path} → table: {table_name}")

            df = read_file(full_path)
            if df is None:
                continue

            tables.setdefault(table_name, {})

            for col in df.columns:
                inferred = infer_type(df[col])
                existing = tables[table_name].get(col)

                if existing:
                    if existing.startswith("VARCHAR") or inferred.startswith("VARCHAR"):
                        tables[table_name][col] = max(existing, inferred, key=len)
                    elif existing != inferred:
                        tables[table_name][col] = "VARCHAR(255)"
                else:
                    tables[table_name][col] = inferred

    return tables


def build_dictionary(tables):
    rows = []
    for table, cols in tables.items():
        for col, dtype in cols.items():
            rows.append({
                "table_name": table,
                "column_name": col,
                "inferred_type": dtype
            })
    return pd.DataFrame(rows)


def main():
    ROOT_FOLDER = f"F:\Recon Dental Data\Data Migration\Data Migration" 
    tables = scan(ROOT_FOLDER)
    df = build_dictionary(tables)

    df.to_csv(OUTPUT_FILE, index=False)

    print("\n✅ Data dictionary generated")
    print(df.head(20))


if __name__ == "__main__":
    main()

