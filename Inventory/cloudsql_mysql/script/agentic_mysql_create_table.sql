CREATE TABLE IF NOT EXISTS products (
  sku              VARCHAR(100) PRIMARY KEY,
  title            VARCHAR(255) NOT NULL,
  description      TEXT,
  category         VARCHAR(100),
  embedding        VECTOR(768) USING VARBINARY,
  last_embedded_at TIMESTAMP NULL,
  created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stores (
  store_id   INT AUTO_INCREMENT PRIMARY KEY,
  code       VARCHAR(50) UNIQUE NOT NULL,
  name       VARCHAR(255) NOT NULL,
  region     VARCHAR(100),
  timezone   VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS suppliers (
  supplier_id     INT AUTO_INCREMENT PRIMARY KEY,
  name            VARCHAR(255) NOT NULL,
  lead_time_days  INT NOT NULL DEFAULT 7,
  moq             INT NOT NULL DEFAULT 1,
  email           VARCHAR(255),
  terms           TEXT
);

CREATE TABLE IF NOT EXISTS product_suppliers (
  sku             VARCHAR(100) NOT NULL,
  supplier_id     INT NOT NULL,
  preferred       TINYINT(1) DEFAULT 0,
  cost            DECIMAL(12,4) NOT NULL,
  lead_time_days  INT,
  moq             INT,
  PRIMARY KEY (sku, supplier_id),
  FOREIGN KEY (sku) REFERENCES products(sku) ON DELETE CASCADE,
  FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS stock_levels (
  store_id        INT NOT NULL,
  sku             VARCHAR(100) NOT NULL,
  on_hand         DECIMAL(12,2) NOT NULL DEFAULT 0,
  in_transit      DECIMAL(12,2) NOT NULL DEFAULT 0,
  safety_stock    DECIMAL(12,2) NOT NULL DEFAULT 0,
  reorder_point   DECIMAL(12,2),
  updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (store_id, sku),
  FOREIGN KEY (store_id) REFERENCES stores(store_id),
  FOREIGN KEY (sku) REFERENCES products(sku)
);

CREATE TABLE IF NOT EXISTS transactions (
  transaction_id  BIGINT AUTO_INCREMENT PRIMARY KEY,
  order_id        VARCHAR(100),
  order_ts        TIMESTAMP NOT NULL,
  store_id        INT,
  channel         VARCHAR(50),
  sku             VARCHAR(100),
  quantity        INT NOT NULL,
  unit_price      DECIMAL(12,2) NOT NULL,
  country         VARCHAR(100),
  FOREIGN KEY (store_id) REFERENCES stores(store_id),
  FOREIGN KEY (sku) REFERENCES products(sku)
);

CREATE OR REPLACE VIEW mv_daily_demand AS
SELECT store_id, sku, DATE(order_ts) AS day, SUM(quantity) AS qty
FROM transactions
GROUP BY store_id, sku, DATE(order_ts);

CREATE TABLE IF NOT EXISTS purchase_orders (
  po_id        BIGINT AUTO_INCREMENT PRIMARY KEY,
  supplier_id  INT NOT NULL,
  status       ENUM('draft','pending_approval','approved','sent','received','closed','cancelled') NOT NULL DEFAULT 'draft',
  created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  created_by   VARCHAR(100),
  approved_by  VARCHAR(100),
  expected_at  DATE,
  total_amount DECIMAL(14,2) DEFAULT 0,
  FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
);

CREATE TABLE IF NOT EXISTS purchase_order_lines (
  po_line_id   BIGINT AUTO_INCREMENT PRIMARY KEY,
  po_id        BIGINT NOT NULL,
  sku          VARCHAR(100) NOT NULL,
  qty          INT NOT NULL,
  unit_cost    DECIMAL(12,4),
  promised_at  DATE,
  FOREIGN KEY (po_id) REFERENCES purchase_orders(po_id) ON DELETE CASCADE,
  FOREIGN KEY (sku) REFERENCES products(sku)
);

CREATE TABLE IF NOT EXISTS docs (
  doc_id      BIGINT AUTO_INCREMENT PRIMARY KEY,
  sku         VARCHAR(100),
  doc_type    VARCHAR(50),
  source_url  TEXT,
  body        TEXT NOT NULL,
  embedding   VECTOR(768) USING VARBINARY,
  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (sku) REFERENCES products(sku)
);

CREATE TABLE IF NOT EXISTS product_images (
    image_id INT AUTO_INCREMENT PRIMARY KEY,
    sku VARCHAR(100) REFERENCES products(sku) ON DELETE CASCADE,
    image_url TEXT,
    image_data LONGBLOB,
    is_default TINYINT(1) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);