INSERT INTO api_definition (
    api_code,
    api_name,
    base_url,
    http_method,
    response_format,
    encoding,
    timeout_seconds,
    page_size,
    active,
    description
)
VALUES (
    'API_KEY_AT_PRICE',
    '한국농수산식품유통공사 일별 도소매 가격정보 조회',
    'https://apis.data.go.kr/B552845/perDay/price',
    'GET',
    'JSON',
    'UTF-8',
    30,
    200,
    TRUE,
    '2015~2024년 배추 품종별 일별 가격정보 수집'
)
ON CONFLICT (api_code)
DO UPDATE SET
    api_name = EXCLUDED.api_name,
    base_url = EXCLUDED.base_url,
    http_method = EXCLUDED.http_method,
    response_format = EXCLUDED.response_format,
    encoding = EXCLUDED.encoding,
    timeout_seconds = EXCLUDED.timeout_seconds,
    page_size = EXCLUDED.page_size,
    active = EXCLUDED.active,
    description = EXCLUDED.description,
    updated_at = CURRENT_TIMESTAMP;
INSERT INTO api_parameter
(
    api_id,
    parameter_name,
    location,
    source_type,
    source_ref,
    data_type,
    required,
    default_value,
    sequence_no,
    transform_rule,
    description
)
SELECT
    api_id,
    p.parameter_name,
    p.location,
    p.source_type,
    p.source_ref,
    p.data_type,
    p.required,
    p.default_value,
    p.sequence_no,
    p.transform_rule,
    p.description
FROM api_definition a
CROSS JOIN (
    VALUES
    (
        'serviceKey',
        'QUERY',
        'ENV',
        'API_KEY_AT_PRICE',
        'STRING',
        TRUE,
        NULL,
        1,
        NULL,
        '공공데이터포털 인증키'
    ),
    (
        'pageNo',
        'QUERY',
        'SYSTEM',
        'PAGE_NO',
        'INTEGER',
        TRUE,
        '1',
        2,
        NULL,
        '페이지 번호'
    ),
    (
        'numOfRows',
        'QUERY',
        'CONST',
        NULL,
        'INTEGER',
        TRUE,
        '1000',
        3,
        NULL,
        '페이지당 조회 건수'
    ),
    (
        'returnType',
        'QUERY',
        'CONST',
        NULL,
        'STRING',
        TRUE,
        'JSON',
        4,
        NULL,
        '응답 형식'
    ),
    (
        'cond[exmn_ymd::GTE]',
        'QUERY',
        'LOOP_YEAR',
        'START_DATE',
        'STRING',
        TRUE,
        NULL,
        5,
        'YYYY0101',
        '조회 시작일'
    ),
    (
        'cond[exmn_ymd::LTE]',
        'QUERY',
        'LOOP_YEAR',
        'END_DATE',
        'STRING',
        TRUE,
        NULL,
        6,
        'YYYY1231',
        '조회 종료일'
    ),
    (
        'cond[se_cd::EQ]',
        'QUERY',
        'CONST',
        NULL,
        'STRING',
        TRUE,
        '02',
        7,
        NULL,
        '구분코드'
    ),
    (
        'cond[ctgry_cd::EQ]',
        'QUERY',
        'CONST',
        NULL,
        'STRING',
        TRUE,
        '200',
        8,
        NULL,
        '부류코드'
    ),
    (
        'cond[item_cd::EQ]',
        'QUERY',
        'CONST',
        NULL,
        'STRING',
        TRUE,
        '211',
        9,
        NULL,
        '품목코드'
    ),
    (
        'cond[grd_cd::EQ]',
        'QUERY',
        'CONST',
        NULL,
        'STRING',
        TRUE,
        '04',
        10,
        NULL,
        '등급코드'
    ),
    (
        'cond[sgg_cd::EQ]',
        'QUERY',
        'CONST',
        NULL,
        'STRING',
        TRUE,
        '1101',
        11,
        NULL,
        '시군구코드'
    ),
    (
        'cond[mrkt_cd::EQ]',
        'QUERY',
        'CONST',
        NULL,
        'STRING',
        TRUE,
        '0110211',
        12,
        NULL,
        '시장코드'
    ),
    (
        'cond[vrty_cd::EQ]',
        'QUERY',
        'DB_COLUMN',
        'variety_cd',
        'STRING',
        TRUE,
        NULL,
        13,
        NULL,
        'common_code 품종코드'
    )
) AS p(
    parameter_name,
    location,
    source_type,
    source_ref,
    data_type,
    required,
    default_value,
    sequence_no,
    transform_rule,
    description
)
WHERE a.api_code = 'AT_PRICE_PER_DAY'
ON CONFLICT (
    api_id,
    parameter_name
)
DO UPDATE SET
    location = EXCLUDED.location,
    source_type = EXCLUDED.source_type,
    source_ref = EXCLUDED.source_ref,
    data_type = EXCLUDED.data_type,
    required = EXCLUDED.required,
    default_value = EXCLUDED.default_value,
    sequence_no = EXCLUDED.sequence_no,
    transform_rule = EXCLUDED.transform_rule,
    description = EXCLUDED.description;