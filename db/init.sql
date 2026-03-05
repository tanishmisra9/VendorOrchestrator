CREATE DATABASE IF NOT EXISTS vendor_master_db;
USE vendor_master_db;

CREATE TABLE IF NOT EXISTS vendor_master (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    vendor_name     VARCHAR(255) NOT NULL,
    address         VARCHAR(500),
    city            VARCHAR(100),
    state           VARCHAR(100),
    zip             VARCHAR(20),
    country         VARCHAR(100) DEFAULT 'US',
    tax_id          VARCHAR(20),
    status          ENUM('active', 'inactive', 'duplicate') DEFAULT 'active',
    cluster_id      INT,
    source          VARCHAR(100),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_vendor_name (vendor_name),
    INDEX idx_tax_id (tax_id),
    INDEX idx_cluster_id (cluster_id),
    INDEX idx_status (status)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    agent_name      VARCHAR(50) NOT NULL,
    action          VARCHAR(100) NOT NULL,
    vendor_id       INT,
    details_json    JSON,
    confidence      FLOAT,
    timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (vendor_id) REFERENCES vendor_master(id) ON DELETE SET NULL,
    INDEX idx_agent (agent_name),
    INDEX idx_timestamp (timestamp)
);

CREATE TABLE IF NOT EXISTS analyst_overrides (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    vendor_id       INT NOT NULL,
    original_action VARCHAR(100) NOT NULL,
    override_action VARCHAR(100) NOT NULL,
    reason          TEXT,
    analyst_name    VARCHAR(100),
    timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (vendor_id) REFERENCES vendor_master(id) ON DELETE CASCADE,
    INDEX idx_vendor (vendor_id),
    INDEX idx_analyst (analyst_name)
);
