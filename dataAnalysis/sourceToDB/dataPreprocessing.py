import os
import re
import json
from pathlib import Path

import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text


# ============================================================
# 1. 기본 설정
# ============================================================

# 프로젝트 홈
BASE_DIR = Path(__file__).resolve().parent

# 분석 대상 로컬 파일
FILE_PATH = Path(
    BASE_DIR/"common_code.txt"
)

# 환경 변수
DB_HOST = os.getenv("db_host")
DB_PORT = os.getenv("db_port")
DB_USER = os.getenv("db_user")
DB_PW = os.getenv("db_pw")


# ============================================================
# 2. DB 접속정보 확인
# ============================================================

def get_db_url():

    required = {
        "db_host": DB_HOST,
        "db_port": DB_PORT,
        "db_user": DB_USER,
        "db_pw": DB_PW
    }

    missing = [
        key for key, value in required.items()
        if not value
    ]

    if missing:
        raise RuntimeError(
            f"DB 접속 환경변수가 없습니다: {', '.join(missing)}"
        )

    # PostgreSQL 기본 DB명
    db_name = os.getenv("db_name", "postgres")

    return (
        f"postgresql://"
        f"{DB_USER}:{DB_PW}@{DB_HOST}:{DB_PORT}/{db_name}"
    )

# ============================================================
# 3. 테이블명 생성
# ============================================================

def get_table_name(file_path: Path):

    # 확장자를 제외한 파일명
    table_name = file_path.stem

    # PostgreSQL에서 안전하게 사용할 수 있도록
    # 앞뒤 공백 제거
    table_name = table_name.strip()

    if not table_name:
        raise ValueError("파일명으로부터 테이블명을 만들 수 없습니다.")

    return table_name


# ============================================================
# 4. 원본 데이터 읽기
# ============================================================

def load_source_file(file_path: Path):

    print("=" * 70)
    print("1. 원본 데이터 읽기")
    print("=" * 70)

    if not file_path.exists():
        raise FileNotFoundError(
            f"파일을 찾을 수 없습니다: {file_path}"
        )

    # 원본 파일이 EUC-KR/CP949 계열이므로
    # CP949로 읽는다.
    df = pd.read_csv(
        file_path,
        sep="\t",
        dtype=str,
        encoding="cp949"
    )

    print(f"파일 : {file_path}")
    print(f"행 수 : {len(df):,}")
    print(f"열 수 : {len(df.columns):,}")
    print(f"컬럼 : {list(df.columns)}")

    return df


# ============================================================
# 5. 데이터 프로파일링
# ============================================================

def profile_data(df):

    print("\n" + "=" * 70)
    print("2. 원본 데이터 프로파일링")
    print("=" * 70)

    profile = []

    for column in df.columns:

        series = df[column]

        non_null = series.dropna()

        profile.append({
            "column": column,
            "dtype_original": str(series.dtype),
            "row_count": len(series),
            "missing_count": int(series.isna().sum()),
            "missing_ratio": round(
                float(series.isna().mean()),
                6
            ),
            "unique_count": int(series.nunique(dropna=True)),
            "min_length": (
                int(non_null.astype(str).str.len().min())
                if len(non_null) > 0 else 0
            ),
            "max_length": (
                int(non_null.astype(str).str.len().max())
                if len(non_null) > 0 else 0
            ),
            "sample_values": (
                non_null.drop_duplicates()
                .head(10)
                .tolist()
            )
        })

    profile_df = pd.DataFrame(profile)

    print(profile_df.to_string(index=False))

    return profile_df


# ============================================================
# 6. 문자열 정제
# ============================================================

def clean_string_values(df):

    result = df.copy()

    for column in result.columns:

        # 문자열 앞뒤 공백 제거
        result[column] = (
            result[column]
            .astype("string")
            .str.strip()
        )

        # 빈 문자열 -> 결측값
        result[column] = (
            result[column]
            .replace("", pd.NA)
        )

    return result


# ============================================================
# 7. 코드 컬럼 검증
# ============================================================

def validate_code_columns(df):

    result = df.copy()

    code_columns = [
        column
        for column in result.columns
        if column.endswith("코드")
    ]

    invalid_rows = []

    for column in code_columns:

        invalid_mask = (
            result[column].notna()
            &
            ~result[column].str.fullmatch(r"\d+")
        )

        count = int(invalid_mask.sum())

        print(
            f"{column:15s} "
            f"비정상 값 : {count:,}건"
        )

        if count > 0:
            invalid_rows.append(
                result.loc[invalid_mask].copy()
            )

            # 숫자 코드가 아닌 경우 제거
            result = result.loc[~invalid_mask]

    return result, invalid_rows


# ============================================================
# 8. 결측치 처리
# ============================================================

def remove_missing_rows(df):

    print("\n결측치 검사")

    missing_before = df.isna().sum()

    print(missing_before)

    # 이 데이터는 코드 기준 데이터이므로
    # 핵심 컬럼 결측 행은 제거한다.
    before = len(df)

    result = df.dropna(
        how="any"
    ).copy()

    after = len(result)

    print(
        f"결측치 행 제거 : "
        f"{before - after:,}건"
    )

    return result


# ============================================================
# 9. 중복 데이터 처리
# ============================================================

def remove_duplicates(df):

    before = len(df)

    duplicate_count = int(
        df.duplicated().sum()
    )

    print(
        f"중복 행 : {duplicate_count:,}건"
    )

    result = df.drop_duplicates().copy()

    after = len(result)

    print(
        f"중복 행 제거 : "
        f"{before - after:,}건"
    )

    return result


# ============================================================
# 10. 자료형 분석
# ============================================================

def determine_postgresql_types(df):

    print("\n" + "=" * 70)
    print("3. PostgreSQL 컬럼 속성 분석")
    print("=" * 70)

    column_info = []

    for column in df.columns:

        series = df[column].dropna().astype(str)

        max_length = (
            int(series.str.len().max())
            if len(series) > 0
            else 1
        )

        # 코드 컬럼
        if column.endswith("CD"):

            postgres_type = f"VARCHAR({max_length})"
            reason = "코드값이며 선행 0 보존 필요"

        # 문자열
        else:

            postgres_type = f"VARCHAR({max_length})"
            reason = "문자열/분류명"

        column_info.append({
            "column": column,
            "postgres_type": postgres_type,
            "max_length": max_length,
            "reason": reason
        })

    result = pd.DataFrame(column_info)

    print(result.to_string(index=False))

    return result


# ============================================================
# 11. SQL 식별자 안전 처리
# ============================================================

def quote_identifier(identifier):

    # PostgreSQL 식별자 내부의 "를 ""
    escaped = identifier.replace('"', '""')

    return f'"{escaped}"'


# ============================================================
# 12. CREATE TABLE SQL 생성
# ============================================================

def generate_create_table_sql(
    table_name,
    column_info
):

    columns = []

    for _, row in column_info.iterrows():

        column_name = quote_identifier(
            row["column"]
        )

        data_type = row["postgres_type"]

        columns.append(
            f"    {column_name} {data_type}"
        )

    table_identifier = quote_identifier(
        table_name
    )

    sql = (
        f"CREATE TABLE {table_identifier} (\n"
        + ",\n".join(columns)
        + "\n);"
    )

    return sql


# ============================================================
# 13. 데이터 정제
# ============================================================

def clean_data(df):

    print("\n" + "=" * 70)
    print("4. 데이터 정제")
    print("=" * 70)

    # 문자열 정리
    result = clean_string_values(df)

    # 결측치 처리
    result = remove_missing_rows(result)

    # 코드값 검증
    result, invalid_rows = validate_code_columns(result)

    # 중복 제거
    result = remove_duplicates(result)

    print(
        f"\n최종 정제 데이터 : "
        f"{len(result):,}건"
    )

    return result


# ============================================================
# 14. DB 생성 및 데이터 적재
# ============================================================

def load_to_postgresql(
    df,
    table_name,
    column_info,
    engine
):

    print("\n" + "=" * 70)
    print("5. PostgreSQL 테이블 생성")
    print("=" * 70)

    create_sql = generate_create_table_sql(
        table_name,
        column_info
    )

    print("\n생성 SQL:")
    print(create_sql)

    with engine.begin() as connection:

        # 기존 테이블 제거
        connection.execute(
            text(
                f"DROP TABLE IF EXISTS "
                f"{quote_identifier(table_name)}"
            )
        )

        # 테이블 생성
        connection.execute(
            text(create_sql)
        )

    print(
        f"\n테이블 생성 완료 : {table_name}"
    )

    print("\n데이터 적재 중...")

    # pandas -> PostgreSQL
    df.to_sql(
        name=table_name,
        con=engine,
        if_exists="append",
        index=False,
        method="multi"
    )

    print(
        f"데이터 적재 완료 : "
        f"{len(df):,}건"
    )


# ============================================================
# 15. 데이터 품질 보고서 저장
# ============================================================

def save_profile_report(
    file_path,
    original_df,
    cleaned_df,
    column_info
):

    report_path = (
        file_path.parent
        / f"{file_path.stem}_profile.json"
    )

    report = {

        "source_file": file_path.name,

        "original": {
            "rows": int(len(original_df)),
            "columns": int(len(original_df.columns)),
            "column_names": list(
                original_df.columns
            )
        },

        "cleaned": {
            "rows": int(len(cleaned_df)),
            "removed_rows": int(
                len(original_df)
                - len(cleaned_df)
            )
        },

        "columns": column_info.to_dict(
            orient="records"
        )
    }

    with open(
        report_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            report,
            file,
            ensure_ascii=False,
            indent=2
        )

    print(
        f"\n프로파일 보고서 저장 : "
        f"{report_path}"
    )


# ============================================================
# 16. Main Pipeline
# ============================================================

def main():

    print("\n")
    print("=" * 70)
    print(" DATA ANALYSIS DATA PIPELINE")
    print("=" * 70)

    # --------------------------------------------------------
    # Step 1. 원본 읽기
    # --------------------------------------------------------

    original_df = load_source_file(
        FILE_PATH
    )

    # --------------------------------------------------------
    # Step 2. 원본 데이터 특성 분석
    # --------------------------------------------------------

    profile_data(
        original_df
    )

    # --------------------------------------------------------
    # Step 3. 정제
    # --------------------------------------------------------

    cleaned_df = clean_data(
        original_df
    )

    # --------------------------------------------------------
    # Step 4. DB 컬럼 속성 결정
    # --------------------------------------------------------

    column_info = determine_postgresql_types(
        cleaned_df
    )

    # --------------------------------------------------------
    # Step 5. DB 연결
    # --------------------------------------------------------

    database_url = get_db_url()

    engine = create_engine(
        database_url,
        pool_pre_ping=True
    )

    # --------------------------------------------------------
    # Step 6. 테이블명 = 파일명
    # --------------------------------------------------------

    table_name = get_table_name(
        FILE_PATH
    )

    print(
        f"\nDB 테이블명 : {table_name}"
    )

    # --------------------------------------------------------
    # Step 7. PostgreSQL 적재
    # --------------------------------------------------------

    load_to_postgresql(
        cleaned_df,
        table_name,
        column_info,
        engine
    )

    # --------------------------------------------------------
    # Step 8. 분석 기준점 보고서
    # --------------------------------------------------------

    save_profile_report(
        FILE_PATH,
        original_df,
        cleaned_df,
        column_info
    )

    print("\n")
    print("=" * 70)
    print(" PIPELINE COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()