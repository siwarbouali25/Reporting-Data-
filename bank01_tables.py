import zipfile
import shutil
from pathlib import Path

import pandas as pd


BANK_ID = "BANK01"


def read_csvs(input_path: Path) -> dict:
    """
    Accepts either:
    - a folder containing CSV files
    - a ZIP file containing CSV files
    """

    work_dir = Path("temp_csv_extract")

    if work_dir.exists():
        shutil.rmtree(work_dir)

    work_dir.mkdir(parents=True, exist_ok=True)

    if input_path.is_file() and input_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(input_path, "r") as z:
            z.extractall(work_dir)
        csv_files = list(work_dir.rglob("*.csv"))

    elif input_path.is_dir():
        csv_files = list(input_path.rglob("*.csv"))

    else:
        raise ValueError("Input must be a CSV folder or a ZIP file.")

    tables = {}

    for csv_file in csv_files:
        table_name = csv_file.stem
        try:
            tables[table_name] = pd.read_csv(csv_file)
            print(f"Loaded {table_name}: {len(tables[table_name])} rows")
        except Exception as e:
            print(f"Skipped {csv_file.name}: {e}")

    return tables


def filter_bank01_tables(tables: dict) -> dict:
    filtered = {}

    # First pass: direct bank_id filtering
    for table_name, df in tables.items():
        if "bank_id" in df.columns:
            filtered[table_name] = df[df["bank_id"] == BANK_ID].copy()
        else:
            filtered[table_name] = df.copy()

    # Collect relationship keys from BANK01 data
    bank_exposures = filtered.get("exposures", pd.DataFrame())
    bank_investments = filtered.get("investments", pd.DataFrame())
    bank_collateral = filtered.get("collateral", pd.DataFrame())

    counterparty_ids = set()
    exposure_ids = set()

    if not bank_exposures.empty:
        if "counterparty_id" in bank_exposures.columns:
            counterparty_ids.update(bank_exposures["counterparty_id"].dropna().astype(str))

        if "exposure_id" in bank_exposures.columns:
            exposure_ids.update(bank_exposures["exposure_id"].dropna().astype(str))

    if not bank_investments.empty and "counterparty_id" in bank_investments.columns:
        counterparty_ids.update(bank_investments["counterparty_id"].dropna().astype(str))

    if not bank_collateral.empty:
        if "counterparty_id" in bank_collateral.columns:
            counterparty_ids.update(bank_collateral["counterparty_id"].dropna().astype(str))

        if "exposure_id" in bank_collateral.columns:
            exposure_ids.update(bank_collateral["exposure_id"].dropna().astype(str))

    # Second pass: relationship-based filtering for tables without reliable bank_id
    for table_name, df in tables.items():
        if table_name in filtered and "bank_id" in df.columns:
            continue

        if "counterparty_id" in df.columns and counterparty_ids:
            filtered[table_name] = df[
                df["counterparty_id"].astype(str).isin(counterparty_ids)
            ].copy()

        elif "exposure_id" in df.columns and exposure_ids:
            filtered[table_name] = df[
                df["exposure_id"].astype(str).isin(exposure_ids)
            ].copy()

        else:
            # Keep reference/system tables as-is
            filtered[table_name] = df.copy()

    return filtered


def save_filtered_tables(filtered: dict, output_folder: Path):
    if output_folder.exists():
        shutil.rmtree(output_folder)

    output_folder.mkdir(parents=True, exist_ok=True)

    for table_name, df in filtered.items():
        output_path = output_folder / f"{table_name}.csv"
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"Saved {output_path.name}: {len(df)} rows")


def zip_output(output_folder: Path):
    zip_path = output_folder.with_suffix(".zip")

    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for csv_file in output_folder.rglob("*.csv"):
            z.write(csv_file, arcname=csv_file.name)

    print(f"Created ZIP: {zip_path}")


if __name__ == "__main__":
    input_path = Path(r"C:\Users\HP\Documents\IFRS_Reporting\notebooks\gen_data\csv_patched")
    output_folder = Path(r"C:\Users\HP\Documents\IFRS_Reporting\notebooks\gen_data\csv_BANK01_only")

    tables = read_csvs(input_path)
    filtered = filter_bank01_tables(tables)
    save_filtered_tables(filtered, output_folder)
    zip_output(output_folder)

    print("Done.")