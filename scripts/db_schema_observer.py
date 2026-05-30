import os
import pandas as pd
import re

# Root folder containing your .txt files and subfolders
ROOT_FOLDER = r"F:\Recon Dental Data\Data Migration\Data Migration"

# Output Excel file
OUTPUT_EXCEL = r"C:\Users\Sravan\Desktop\dentc-backend\data\schema_details.xlsx"

results = []


def is_numeric_filename(filename):
    """
    Check if filename is numeric like:
    1.txt, 22.txt, 100.txt
    """
    name_without_ext = os.path.splitext(filename)[0]
    return re.fullmatch(r"\d+", name_without_ext) is not None


# Traverse all folders and subfolders
for root, dirs, files in os.walk(ROOT_FOLDER):

    for file in files:

        if file.lower().endswith(".txt"):

            file_path = os.path.join(root, file)

            try:
                # If file name is numeric, use parent folder name
                if is_numeric_filename(file):
                    display_name = os.path.basename(root)
                else:
                    display_name = os.path.splitext(file)[0]

                # Read first row only
                df = pd.read_csv(file_path, nrows=1)

                # Extract columns
                columns = list(df.columns)

                # Extract first row values
                first_row = (
                    df.iloc[0].to_dict()
                    if not df.empty else {}
                )

                results.append({
                    "Schema Name": display_name,
                    "Original File": file,
                    "Folder": root,
                    "Full Path": file_path,
                    "Columns": ", ".join(columns),
                    "First Row Values": str(first_row)
                })

                print(f"Processed: {file_path}")

            except Exception as e:

                results.append({
                    "Schema Name": display_name if 'display_name' in locals() else file,
                    "Original File": file,
                    "Folder": root,
                    "Full Path": file_path,
                    "Columns": "ERROR",
                    "First Row Values": str(e)
                })

                print(f"Error processing {file_path}: {e}")


# Create dataframe
output_df = pd.DataFrame(results)

# Save to Excel
output_df.to_excel(OUTPUT_EXCEL, index=False)

