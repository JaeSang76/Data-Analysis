#python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
api_client.py

한국농수산식품유통공사 일별 도소매 가격정보 API 수집 프로그램

수집 대상
---------
- 연도 : 2015 ~ 2024
- 부류 : 200 (채소류)
- 품목 : 211 (배추)
- 품종 : common_code에서 조회(01 봄배추/02여름배추(고랭지)/03(가을배추)/06(월동배추))
- 등급 : 04(상품)
- 시군구 : 1101(서울)
- 시장 : 0110211(가락도매)

API
---
https://apis.data.go.kr/B552845/perDay/price

주요 기능
---------
1. PostgreSQL에서 API 정의 조회
2. PostgreSQL에서 API Parameter 정의 조회
3. common_code에서API 공통코드(배추 품종코드 조회)
4. 2015~2024년까지 4가지 품종별 API 호출
5. Pagination 처리
6. API 원본 JSON 저장
7. API 응답 데이터를 PostgreSQL에 UPSERT
8. HTTP/API 오류 처리
9. 재시도 처리
10. Linux Cron 실행을 고려한 로그 및 종료코드 처리
"""

import json
import logging
import os
import sys
import time

from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import psycopg
import requests
from psycopg.rows import dict_row


# ============================================================
# 1. 기본 설정
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

LOG_DIR = BASE_DIR / "logs" # 로그데이터 저장 폴더 
RAW_DIR = BASE_DIR / "raw"  # API 응답값 저장 폴더

LOG_DIR.mkdir(
    parents=True,
    exist_ok=True
)

RAW_DIR.mkdir(
    parents=True,
    exist_ok=True
)

# ------------------------------------------------------------
# 수집 대상
# 2015년부터 2024년까지 서울 가락도매시장의 배추
# (품종: 봄/여름(고랭지)/가을/월동) 가격 데이터를 수집
# ------------------------------------------------------------

API_CODE = "API_KEY_AT_PRICE"

START_YEAR = 2015
END_YEAR = 2024

DEFAULT_PAGE_SIZE = 1000
REQUEST_TIMEOUT = 30
MAX_RETRY = 3
RETRY_WAIT_SECONDS = 2

# ============================================================
# 2. Logging
# ============================================================

logger = logging.getLogger("api_client")
logger.setLevel(logging.INFO)

formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(message)s"
)

file_handler = RotatingFileHandler(
    LOG_DIR / "api_client.log",
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8"
)

file_handler.setFormatter(formatter)

console_handler = logging.StreamHandler(
    sys.stdout
)

console_handler.setFormatter(
    formatter
)

logger.addHandler(
    file_handler
)

logger.addHandler(
    console_handler
)

# ============================================================
# 3. 환경변수
# ============================================================
"""
widnows 환경변수를 가져온다.
값이 없으면 프로그램을 중단한다.
"""

def get_required_env(name: str) -> str:

    value = os.getenv(name)

    if value is None or value.strip() == "":
        raise RuntimeError(
            f"필수 환경변수가 없습니다: {name}"
        )

    return value.strip()

# ============================================================
# 4. PostgreSQL 연결
# ============================================================
def get_db_connection():

    host = get_required_env(
        "db_host"
    )

    port = os.getenv(
        "db_port",
        "5432"
    )

    user = get_required_env(
        "db_user"
    )

    password = get_required_env(
        "db_pw"
    )

    dbname = os.getenv(
        "db_name",
        "postgres"
    )

    return psycopg.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        dbname=dbname
    )

# ============================================================
# 5. API Definition 조회
# ============================================================
"""
api_definition에서 사용할 API 정보를 조회한다.
"""

def get_api_definition(conn):

    sql = """
        SELECT
            api_id,
            api_code,
            api_name,
            base_url,
            http_method,
            success_code,
            response_state_code,
            response_format,
            encoding,
            timeout_seconds,
            page_size
        FROM api_definition
        WHERE api_code = %s
          AND active = TRUE
    """

    with conn.cursor(row_factory=dict_row) as cur:

        cur.execute(
            sql,
            (API_CODE,)
        )

        row = cur.fetchone()

    if row is None:
        raise RuntimeError(
            f"활성 API 정의가 없습니다: {API_CODE}"
        )

    return row

# ============================================================
# 6. API Parameter 조회
# ============================================================
"""
api_parameter 테이블에서
API 파라미터 정의를 조회한다.
"""
def get_api_parameters(
    conn,
    api_id
):

    sql = """
        SELECT
            parameter_name,
            location,
            source_type,
            source_ref,
            data_type,
            required,
            default_value,
            sequence_no,
            transform_rule
        FROM api_parameter
        WHERE api_id = %s
        ORDER BY sequence_no
    """

    with conn.cursor(row_factory=dict_row) as cur:

        cur.execute(
            sql,
            (api_id,)
        )

        rows = cur.fetchall()

    if not rows:
        raise RuntimeError(
            f"API Parameter가 없습니다. "
            f"api_id={api_id}"
        )

    return rows

# ============================================================
# 7. common_code에서 품종코드 조회
# ============================================================
"""
배추 품종코드 조회
class_cd = 200
item_cd  = 211
"""
def get_variety_codes(conn):

    sql = """
        SELECT DISTINCT
            variety_cd
        FROM common_code
        WHERE class_cd = '200'
          AND item_cd = '211'
          AND variety_cd IS NOT NULL
          AND TRIM(variety_cd) <> ''
        ORDER BY variety_cd
    """

    with conn.cursor() as cur:

        cur.execute(sql)
        rows = cur.fetchall()

    variety_codes = []

    for row in rows:

        code = str(
            row[0] # "variety_cd"
        ).strip()

        if code:
            variety_codes.append(code)

    if not variety_codes:
        raise RuntimeError(
            "common_code에서 "
            "배추 품종코드를 찾지 못했습니다."
        )

    return variety_codes

# ============================================================
# 8. API Parameter 생성
# ============================================================
"""
api_parameter 메타데이터를 이용하여
실제 REST API의 query parameter를 생성한다.

Source      Type
----------------------------
ENV         환경변수
CONST       고정값
LOOP_YEAR   현재 반복 연도
DB_COLUMN   PostgreSQL 조회값
SYSTEM      프로그램 실행 중 생성되는 값
"""
def build_parameters(
    parameter_definitions,
    year,
    variety_code,
    page_no
):

    params = {}

    for definition in parameter_definitions:

        parameter_name = (
            definition["parameter_name"]
        )
        source_type = (
            definition["source_type"]
        )
        source_ref = (
            definition["source_ref"]
        )
        default_value = (
            definition["default_value"]
        )
        transform_rule = (
            definition["transform_rule"]
        )

        # ----------------------------------------------------
        # ENV(로컬 환경변수값)
        # ----------------------------------------------------
        if source_type == "ENV":

            value = get_required_env(
                source_ref
            )

        # ----------------------------------------------------
        # CONST(API 고정값)
        # ----------------------------------------------------
        elif source_type == "CONST":

            value = default_value

        # ----------------------------------------------------
        # LOOP_YEAR
        # ----------------------------------------------------
        elif source_type == "LOOP_YEAR":

            if source_ref == "START_DATE":

                value = f"{year}0101"

            elif source_ref == "END_DATE":

                value = f"{year}1231"

            else:

                raise ValueError(
                    f"지원하지 않는 LOOP_YEAR: "
                    f"{source_ref}"
                )

        # ----------------------------------------------------
        # SYSTEM
        # ----------------------------------------------------
        elif source_type == "SYSTEM":

            if source_ref == "PAGE_NO":
                value = page_no

            else:
                raise ValueError(
                    f"지원하지 않는 SYSTEM 값: "
                    f"{source_ref}"
                )

        # ----------------------------------------------------
        # DB_COLUMN
        # ----------------------------------------------------
        elif source_type == "DB_COLUMN":

            if source_ref == "variety_cd":
                value = variety_code

            else:
                raise ValueError(
                    f"지원하지 않는 DB_COLUMN: "
                    f"{source_ref}"
                )

        else:
            raise ValueError(
                f"지원하지 않는 source_type: "
                f"{source_type}"
            )

        # ----------------------------------------------------
        # Transform Rule
        # ----------------------------------------------------
        if transform_rule == "YYYY0101":
            value = f"{year}0101"

        elif transform_rule == "YYYY1231":
            value = f"{year}1231"

        params[
            parameter_name
        ] = value

    return params


# ============================================================
# 9. 로그용 Parameter Masking
# ============================================================
"""
인증키가 로그에 노출되지 않도록 한다.
"""
def mask_parameters(params):

    safe_params = dict(params)

    for key in (
        "serviceKey",
        "service_key",
        "apiKey",
        "api_key"
    ):

        if key in safe_params:
            safe_params[key] = "***MASKED***"

    return safe_params

# ============================================================
# 10. API 호출
# ============================================================
"""
<REST API 호출>
    HTTP응답값이 success_code가 아니면 오류 처리한다.
    일시적 오류는 최대 3회 재시도한다.
"""
def call_api(
    session,
    url,
    params,
    success_code,
    timeout
):
    logger.info(
        "API 호출: url=%s params=%s",
        url,
        mask_parameters(params)
    )

    last_exception = None

    for attempt in range(
        1,
        MAX_RETRY + 1
    ):

        try:
            response = session.get(
                url,
                params=params,
                timeout=timeout
            )

            # ------------------------------------------------
            # HTTP Response Code 검사
            # ------------------------------------------------
            if response.status_code != success_code:
                raise RuntimeError(
                    f"HTTP 오류: "
                    f"status_code={response.status_code}"
                )

            # ------------------------------------------------
            # JSON 변환
            # ------------------------------------------------
            try:
                data = response.json()

            except ValueError as exc:
                raise RuntimeError(
                    "응답 데이터를 JSON으로 "
                    "변환할 수 없습니다."
                ) from exc

            return data

        except (
            requests.RequestException,
            RuntimeError
        ) as exc:
            last_exception = exc
            logger.warning(
                "API 호출 실패 "
                "(attempt=%s/%s): %s",
                attempt,
                MAX_RETRY,
                exc
            )

            if attempt < MAX_RETRY:
                wait_seconds = (
                    RETRY_WAIT_SECONDS
                    * attempt
                )

                time.sleep(
                    wait_seconds
                )

    raise RuntimeError(
        f"API 호출 최종 실패: "
        f"{last_exception}"
    )


# ============================================================
# 11. API Response Header 검사
# ============================================================
"""
실제 API 응답 구조

{
  "response": {
        {
        "header": {
            "resultCode": "...",
            "resultMsg": "..."
        },
        "body": {
            "items": {
                "item": [...]
            },
            "dataType": "...",
            "numOfRows": 0,
            "pageNo": 0,
            "totalCount": 0
        }
    }
}
"""
def validate_response(data, response_state_code):

    if not isinstance(
        data,
        dict
    ):
        raise RuntimeError(
            "API 응답이 JSON Object가 아닙니다."
        )
        
    response = data.get(
        "response"
    )
    
    if not isinstance(
        response,
        dict
    ):
        raise RuntimeError(
            "API 응답에 response가 없습니다."
        )
    
    header = response.get(
        "header"
    )

    if not isinstance(
        header,
        dict
    ):
        raise RuntimeError(
            "API 응답에 header가 없습니다."
        )

    result_code = str(
        header.get(
            "resultCode",
            ""
        )
    ).strip()

    result_msg = str(
        header.get(
            "resultMsg",
            ""
        )
    ).strip()

    # --------------------------------------------------------
    # API 성공 코드 : 0 
    # 실제 운영에서는 API의 resultCode 정의에 따라
    # 조정할 수 있도록 작성한다.
    # --------------------------------------------------------

    if result_code != response_state_code:
        raise RuntimeError(
            f"API 오류: "
            f"resultCode={result_code}, "
            f"resultMsg={result_msg}"
        )

    body = response.get(
        "body"
    )

    if not isinstance(
        body,
        dict
    ):
        raise RuntimeError(
            "API 응답에 body가 없습니다."
        )

    return body


# ============================================================
# 12. API Item 추출
# ============================================================
"""
실제 API 응답 구조에서 item 배열을 추출한다.
"""
def extract_items(data, response_state_code):

    body = validate_response(
        data, response_state_code
    )

    items = body.get(
        "items",
        {}
    )

    if not isinstance(
        items,
        dict
    ):
        return [], 0, 0, 0

    item_list = items.get(
        "item",
        []
    )

    # -----------------------------------------------
    # 데이터가 하나일 경우 API가 Object로 반환하는
    # 경우까지 대비한다.
    # -----------------------------------------------
    if item_list is None:
        item_list = []

    elif isinstance(
        item_list,
        dict
    ):
        item_list = [
            item_list
        ]
        
    elif not isinstance(
        item_list,
        list
    ):
        raise RuntimeError(
            "items.item의 데이터 형식이 JSON형식이 아닙니다."
        )

    num_of_rows = body.get(
        "numOfRows",
        0
    )

    page_no = body.get(
        "pageNo",
        0
    )

    total_count = body.get(
        "totalCount",
        0
    )

    try:
        num_of_rows = int(
            num_of_rows
        )
    except (
        TypeError,
        ValueError
    ):
        num_of_rows = 0

    try:
        page_no = int(
            page_no
        )
    except (
        TypeError,
        ValueError
    ):
        page_no = 0

    try:
        total_count = int(
            total_count
        )
    except (
        TypeError,
        ValueError
    ):
        total_count = 0

    return (
        item_list,
        num_of_rows,
        page_no,
        total_count
    )


# ============================================================
# 13. Raw JSON 저장
# ============================================================
"""
API 원본 응답을 JSON 파일로 저장한다.

Raw 데이터를 보존하는 이유:
- 재현성
- API 변경 추적
- 데이터 오류 분석
- 감사/검증
"""
def save_raw_json(
    data,
    year,
    variety_code,
    page_no
):

    year_dir = (
        RAW_DIR
        / str(year)
    )

    year_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    filename = (
        f"{year}_"
        f"{variety_code}_"
        f"page_{page_no}.json"
    )

    path = (
        year_dir
        / filename
    )

    with path.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )

    return path


# ============================================================
# 14. 숫자 변환
# ============================================================
def to_number(value):
    """
    가격 문자열을 NUMERIC 저장용 값으로 변환한다.
    """

    if value is None:
        return None

    value = str(
        value
    ).strip()

    if not value:
        return None

    # 천 단위 콤마 제거
    value = value.replace(
        ",",
        ""
    )

    try:
        return float(
            value
        )

    except (
        TypeError,
        ValueError
    ):
        logger.warning(
            "숫자 변환 실패: value=%s",
            value
        )

        return None

# ============================================================
# 15. 날짜 변환
# ============================================================
"""
exmn_ymd

예:
    20150101
"""
def to_date(value):

    if value is None:
        return None

    value = str(
        value
    ).strip()

    if not value:
        return None

    formats = [
        "%Y%m%d",
        "%Y-%m-%d"
    ]

    for fmt in formats:

        try:
            return datetime.strptime(
                value,
                fmt
            ).date()

        except ValueError:
            continue

    logger.warning(
        "날짜 변환 실패: value=%s",
        value
    )

    return None

# ============================================================
# 16. Timestamp 변환
# ============================================================
"""
orgnl_reg_dt를 TIMESTAMP로 변환한다.
"""
def to_timestamp(value):
    if value is None:
        return None

    value = str(
        value
    ).strip()

    if not value:
        return None

    formats = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y%m%d%H%M%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f"
    ]

    for fmt in formats:

        try:
            return datetime.strptime(
                value,
                fmt
            )

        except ValueError:
            continue

    logger.warning(
        "Timestamp 변환 실패: value=%s",
        value
    )

    return None

# ============================================================
# 17. API Item → PostgreSQL Row
# ============================================================
"""
실제 API 응답 필드명을 PostgreSQL 컬럼에 매핑한다.

실제 API 응답
-------------
exmn_ymd
se_cd
se_nm
ctgry_cd
ctgry_nm
item_cd
item_nm
vrty_cd
vrty_nm
grd_cd
grd_nm
sgg_cd
sgg_nm
unit
unit_sz
mrkt_cd
mrkt_nm
exmn_dd_prc
exmn_dd_cnvs_prc
orgnl_reg_dt
"""

def convert_item(item):

    return (
        # 조사일자
        to_date(
            item.get("exmn_ymd")
        ),

        # 구분
        item.get("se_cd"),
        item.get("se_nm"),

        # 부류
        item.get("ctgry_cd"),
        item.get("ctgry_nm"),

        # 품목
        item.get("item_cd"),
        item.get("item_nm"),

        # 품종
        item.get("vrty_cd"),
        item.get("vrty_nm"),

        # 등급
        item.get("grd_cd"),
        item.get("grd_nm"),

        # 시군구
        item.get("sgg_cd"),
        item.get("sgg_nm"),

        # 단위
        item.get("unit"),
        item.get("unit_sz"),

        # 시장
        item.get("mrkt_cd"),
        item.get("mrkt_nm"),

        # 가격
        to_number(
            item.get("exmn_dd_prc")
        ),

        to_number(
            item.get("exmn_dd_cnvs_prc")
        ),

        # 원본 등록일시
        to_timestamp(
            item.get("orgnl_reg_dt")
        )
    )


# ============================================================
# 18. PostgreSQL 저장
# ============================================================
"""
API 데이터를 PostgreSQL에 저장한다.
동일한 데이터가 다시 수집되어도
중복 INSERT가 발생하지 않도록 UPSERT 한다.
"""
def save_items(
    conn,
    items
):

    if not items:
        return 0

    rows = []

    for item in items:
        rows.append(
            convert_item(item)
        )

    sql = """
        INSERT INTO daily_price (
            exmn_ymd,
            se_cd,
            se_nm,
            ctgry_cd,
            ctgry_nm,
            item_cd,
            item_nm,
            vrty_cd,
            vrty_nm,
            grd_cd,
            grd_nm,
            sgg_cd,
            sgg_nm,
            unit,
            unit_sz,
            mrkt_cd,
            mrkt_nm,
            exmn_dd_prc,
            exmn_dd_cnvs_prc,
            orgnl_reg_dt
        )
        VALUES (
            %s,
            %s, %s,
            %s, %s,
            %s, %s,
            %s, %s,
            %s, %s,
            %s, %s,
            %s, %s,
            %s, %s,
            %s, %s,
            %s
        )
        ON CONFLICT (
            exmn_ymd,
            se_cd,
            ctgry_cd,
            item_cd,
            vrty_cd,
            grd_cd,
            sgg_cd,
            mrkt_cd
        )
        DO UPDATE SET
            se_nm =
                EXCLUDED.se_nm,
            ctgry_nm =
                EXCLUDED.ctgry_nm,
            item_nm =
                EXCLUDED.item_nm,
            vrty_nm =
                EXCLUDED.vrty_nm,
            grd_nm =
                EXCLUDED.grd_nm,
            sgg_nm =
                EXCLUDED.sgg_nm,
            unit =
                EXCLUDED.unit,
            unit_sz =
                EXCLUDED.unit_sz,
            mrkt_nm =
                EXCLUDED.mrkt_nm,
            exmn_dd_prc =
                EXCLUDED.exmn_dd_prc,
            exmn_dd_cnvs_prc =
                EXCLUDED.exmn_dd_cnvs_prc,
            orgnl_reg_dt =
                EXCLUDED.orgnl_reg_dt,
            collected_at =
                CURRENT_TIMESTAMP
    """

    with conn.cursor() as cur:
        cur.executemany(
            sql,
            rows
        )

    conn.commit()

    return len(rows)

# ============================================================
# 19. 연도 + 품종별 수집
# ============================================================
"""
특정 연도 + 특정 품종의 데이터를
pagination을 적용하여 모두 수집한다.
"""
def collect_year_variety(
    conn,
    session,
    api_definition,
    parameter_definitions,
    year,
    variety_code
):

    base_url = (
        api_definition["base_url"]
    )
    
    success_code = (
        api_definition["success_code"]
    )

    response_state_code = (
        api_definition["response_state_code"]
    )
    
    timeout = (
        api_definition[
            "timeout_seconds"
        ]
        or REQUEST_TIMEOUT
    )

    page_size = (
        api_definition["page_size"]
        or DEFAULT_PAGE_SIZE
    )

    page_no = 1

    total_saved = 0

    logger.info(
        "수집 시작: "
        "year=%s variety=%s",
        year,
        variety_code
    )

    while True:

        # ----------------------------------------------------
        # API Parameter 생성
        # ----------------------------------------------------
        params = build_parameters(
            parameter_definitions,
            year,
            variety_code,
            page_no
        )

        # api_definition의 page_size 사용
        params["numOfRows"] = (
            page_size
        )

        # ----------------------------------------------------
        # API 호출
        # ----------------------------------------------------
        data = call_api(
            session,
            base_url,
            params,
            success_code,
            timeout
        )

        # ----------------------------------------------------
        # Raw JSON 저장
        # ----------------------------------------------------
        raw_path = save_raw_json(
            data,
            year,
            variety_code,
            page_no
        )

        # ----------------------------------------------------
        # 응답 데이터 추출
        # ----------------------------------------------------
        (
            item_list,
            num_of_rows,
            response_page_no,
            total_count
        ) = extract_items(
            data, response_state_code
        )
        
        # logger.info(
        #     "API 응답: "
        #     "year=%s variety=%s "
        #     "page=%s item=%s "
        #     "page_no=%s total_count=%s",
        #     year,
        #     variety_code,
        #     item_list,
        #     num_of_rows,
        #     response_page_no,
        #     total_count
        # )
        
        # ----------------------------------------------------
        # PostgreSQL 저장
        # ----------------------------------------------------
        if item_list:

            saved_count = save_items(
                conn,
                item_list
            )

            total_saved += (
                saved_count
            )

        # ----------------------------------------------------
        # Pagination 종료 조건
        # ----------------------------------------------------
        # 데이터가 없으면 종료
        if not item_list:
            break

        # 전체 데이터 건수가 있는 경우
        if total_count > 0:

            if (
                page_no * page_size
                >= total_count
            ):
                break

        # totalCount가 없는 경우
        elif len(item_list) < page_size:
            break

        page_no += 1

    logger.info(
        "수집 완료: "
        "year=%s variety=%s saved=%s",
        year,
        variety_code,
        total_saved
    )

    return total_saved

# ============================================================
# 20. Main
# ============================================================
def main():

    logger.info(
        "=" * 70
    )
    logger.info(
        "농산물 가격 API 수집 시작"
    )
    logger.info(
        "수집기간: %s ~ %s",
        START_YEAR,
        END_YEAR
    )
    logger.info(
        "=" * 70
    )

    conn = None
    success_count = 0
    fail_count = 0

    try:

        # ----------------------------------------------------
        # DB 연결
        # ----------------------------------------------------
        conn = get_db_connection()
        logger.info(
            "PostgreSQL 연결 성공"
        )

        # ----------------------------------------------------
        # API Definition
        # ----------------------------------------------------
        api_definition = (
            get_api_definition(
                conn
            )
        )
        logger.info(
            "API 선택: %s",
            api_definition["api_name"]
        )

        # ----------------------------------------------------
        # API Parameter
        # ----------------------------------------------------
        parameter_definitions = (
            get_api_parameters(
                conn,
                api_definition["api_id"]
            )
        )
        logger.info(
            "API Parameter 수: %s",
            len(parameter_definitions)
        )

        # ----------------------------------------------------
        # 품종코드
        # ----------------------------------------------------
        variety_codes = (
            get_variety_codes(
                conn
            )
        )
        logger.info(
            "배추 품종코드: %s",
            variety_codes
        )

        # ----------------------------------------------------
        # HTTP Session
        # ----------------------------------------------------
        session = requests.Session()

        # ----------------------------------------------------
        # 연도 × 품종
        # ----------------------------------------------------
        for year in range(
            START_YEAR,
            END_YEAR + 1
        ):

            for variety_code in (
                variety_codes
            ):

                try:
                    collect_year_variety(
                        conn,
                        session,
                        api_definition,
                        parameter_definitions,
                        year,
                        variety_code
                    )
                    success_count += 1

                except Exception:
                    fail_count += 1
                    
                    logger.exception(
                        "수집 실패: "
                        "year=%s variety=%s",
                        year,
                        variety_code
                    )
                    
                    # 하나의 조건이 실패해도 전체 수집은 계속 진행
                    continue

    except Exception:
        logger.exception(
            "프로그램 실행 중 치명적 오류 발생"
        )
        return 1

    finally:
        if conn:
            conn.close()
            logger.info(
                "PostgreSQL 연결 종료"
            )

    # --------------------------------------------------------
    # 결과
    # --------------------------------------------------------
    logger.info(
        "=" * 70
    )
    logger.info(
        "수집 종료"
    )
    logger.info(
        "성공: %s / 실패: %s",
        success_count,
        fail_count
    )
    logger.info(
        "=" * 70
    )
    
    # Cron에서 실패 여부를 판단할 수 있도록
    # 실패가 있으면 exit code 1
    if fail_count > 0:

        return 1

    return 0

# ============================================================
# 21. Program Entry Point
# ============================================================
if __name__ == "__main__":

    sys.exit(
        main()
    )
#```
