CREATE TABLE IF NOT EXISTS api_definition (
    api_id              BIGSERIAL PRIMARY KEY,
    api_code            VARCHAR(50) NOT NULL UNIQUE,
    api_name            VARCHAR(200) NOT NULL,
    base_url             TEXT NOT NULL,
    http_method          VARCHAR(10) NOT NULL DEFAULT 'GET',
    success_code         INTEGER NOT NULL DEFAULT 200,
    response_state_code  VARCHAR(10) NOT NULL DEFAULT '0',
    response_format      VARCHAR(20) NOT NULL DEFAULT 'JSON',
    encoding             VARCHAR(30),
    timeout_seconds      INTEGER NOT NULL DEFAULT 30,
    page_size            INTEGER NOT NULL DEFAULT 1000,
    active               BOOLEAN NOT NULL DEFAULT TRUE,
    description          TEXT,
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS api_parameter (
    parameter_id       BIGSERIAL PRIMARY KEY,
    api_id             BIGINT NOT NULL
                       REFERENCES api_definition(api_id)
                       ON DELETE CASCADE,
    parameter_name     VARCHAR(200) NOT NULL,
    location           VARCHAR(20) NOT NULL DEFAULT 'QUERY',
    source_type        VARCHAR(30) NOT NULL,
    source_ref         VARCHAR(200),
    data_type          VARCHAR(30) NOT NULL DEFAULT 'STRING',
    required           BOOLEAN NOT NULL DEFAULT FALSE,
    default_value      VARCHAR(500),
    sequence_no        INTEGER NOT NULL,
    transform_rule     VARCHAR(100),
    description        TEXT,
    created_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(api_id, parameter_name)
);


CREATE TABLE IF NOT EXISTS daily_price (
    exmn_ymd             DATE NOT NULL,
    se_cd                VARCHAR(20),
    se_nm                VARCHAR(100),
    ctgry_cd             VARCHAR(20),
    ctgry_nm             VARCHAR(100),
    item_cd              VARCHAR(20),
    item_nm              VARCHAR(100),
    vrty_cd              VARCHAR(20),
    vrty_nm              VARCHAR(100),
    grd_cd               VARCHAR(20),
    grd_nm               VARCHAR(100),
    sgg_cd               VARCHAR(20),
    sgg_nm               VARCHAR(100),
    unit                 VARCHAR(100),
    unit_sz              VARCHAR(100),
    mrkt_cd              VARCHAR(30),
    mrkt_nm              VARCHAR(100),
    exmn_dd_prc          NUMERIC(15, 2),
    exmn_dd_cnvs_prc     NUMERIC(15, 2),
    orgnl_reg_dt         TIMESTAMPTZ,
    collected_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (
        exmn_ymd,
        se_cd,
        ctgry_cd,
        item_cd,
        vrty_cd,
        grd_cd,
        sgg_cd,
        mrkt_cd
    )
);