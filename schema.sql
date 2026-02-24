-- EPWinViewer MySQL Schema
-- Bio-Logic EPWin database migration

CREATE DATABASE IF NOT EXISTS epwin CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE epwin;

-- Patients (from BLPatients.mdb)
CREATE TABLE IF NOT EXISTS patients (
  id INT AUTO_INCREMENT PRIMARY KEY,
  blsc_id VARCHAR(100) NOT NULL UNIQUE,
  patient_id VARCHAR(100),
  first_name VARCHAR(200),
  last_name VARCHAR(200),
  birthdate DATE,
  sex VARCHAR(20),
  last_test DATETIME,
  INDEX idx_patient_id (patient_id),
  INDEX idx_blsc (blsc_id)
) ENGINE=InnoDB;

-- Sessions (logical grouping by date)
CREATE TABLE IF NOT EXISTS sessions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  patient_id INT NOT NULL,
  session_date DATE,
  first_start DATETIME,
  FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
  INDEX idx_patient (patient_id),
  INDEX idx_date (session_date)
) ENGINE=InnoDB;

-- Records (from EPWinData.mdb Records table)
CREATE TABLE IF NOT EXISTS records (
  id INT AUTO_INCREMENT PRIMARY KEY,
  session_id INT NOT NULL,
  record_id VARCHAR(100) NOT NULL UNIQUE,
  blsc_id VARCHAR(100) NOT NULL,
  test_id VARCHAR(100),
  test_type INT,
  test_type_name VARCHAR(50),
  start_time DATETIME,
  stop_time DATETIME,
  comments TEXT,
  channels INT,
  epoch_ms DOUBLE,
  points INT,
  pre_post_points INT,
  blocked_points INT,
  ad_bits INT DEFAULT 16,
  collection_rate_hz DOUBLE,
  max_of_averages INT,
  u_v_per_count DOUBLE,
  data_hex LONGTEXT,
  FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
  INDEX idx_record_id (record_id),
  INDEX idx_blsc (blsc_id),
  INDEX idx_test_type (test_type_name),
  INDEX idx_start (start_time)
) ENGINE=InnoDB;

-- EPData (metadata per channel/bank)
CREATE TABLE IF NOT EXISTS ep_data (
  id INT AUTO_INCREMENT PRIMARY KEY,
  record_id VARCHAR(100) NOT NULL,
  channel_number INT,
  bank_number INT,
  averages VARCHAR(50),
  rejected VARCHAR(50),
  low_analysis_filter VARCHAR(50),
  high_analysis_filter VARCHAR(50),
  dc_offset_counts INT,
  has_dc_offset_counts BOOLEAN DEFAULT FALSE,
  FOREIGN KEY (record_id) REFERENCES records(record_id) ON DELETE CASCADE,
  INDEX idx_record (record_id),
  INDEX idx_chan_bank (record_id, channel_number, bank_number),
  UNIQUE KEY unique_chan_bank (record_id, channel_number, bank_number)
) ENGINE=InnoDB;

-- Amplifier calibration
CREATE TABLE IF NOT EXISTS amplifier_calibration (
  id INT AUTO_INCREMENT PRIMARY KEY,
  record_id VARCHAR(100) NOT NULL,
  uv_per_count DOUBLE,
  full_scale_uv DOUBLE,
  amplifier_gain INT,
  FOREIGN KEY (record_id) REFERENCES records(record_id) ON DELETE CASCADE,
  INDEX idx_record (record_id),
  UNIQUE KEY unique_record (record_id)
) ENGINE=InnoDB;

-- Stimulus metadata (ear, stimulus, rate, intensity, delay)
CREATE TABLE IF NOT EXISTS stimulus_data (
  id INT AUTO_INCREMENT PRIMARY KEY,
  record_id VARCHAR(100) NOT NULL,
  ear VARCHAR(50),
  stimulus VARCHAR(500),
  stim_rate VARCHAR(50),
  stim_intensity VARCHAR(50),
  insert_delay_ms DOUBLE,
  FOREIGN KEY (record_id) REFERENCES records(record_id) ON DELETE CASCADE,
  INDEX idx_record (record_id),
  UNIQUE KEY unique_record (record_id)
) ENGINE=InnoDB;
