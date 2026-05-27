from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = {"time", "open", "high", "low", "close", "volume"}


def load_json_data(file_path: str | Path) -> pd.DataFrame:
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    df = pd.read_json(file_path)

    validate_columns(df, file_path)
    df = convert_types(df)
    df = clean_data(df)

    return df


def validate_columns(df: pd.DataFrame, file_path: Path) -> None:
    missing = REQUIRED_COLUMNS - set(df.columns)

    if missing:
        raise ValueError(f"Missing columns in {file_path}: {missing}")


def convert_types(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["time"] = pd.to_datetime(df["time"], utc=True)

    for column in ["open", "high", "low", "close", "volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    return df


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df = df.dropna(subset=["time", "open", "high", "low", "close"])
    df = df.sort_values("time")
    df = df.drop_duplicates(subset=["time"])
    df = df.reset_index(drop=True)

    return df


def filter_date_range(
    df: pd.DataFrame,
    start_date: str | None,
    end_date: str | None,
) -> pd.DataFrame:
    df = df.copy()

    if start_date:
        start = pd.to_datetime(start_date, utc=True)
        df = df[df["time"] >= start]

    if end_date:
        end = pd.to_datetime(end_date, utc=True)
        df = df[df["time"] <= end]

    return df.reset_index(drop=True)