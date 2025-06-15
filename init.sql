-- init.sql

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE,
    email VARCHAR(255) UNIQUE,
    email_verified BOOLEAN DEFAULT FALSE,
    phone_number VARCHAR(20) UNIQUE,
    phone_verified BOOLEAN DEFAULT FALSE,
    free_until TIMESTAMP,
    subscription_until TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    last_active TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ads (
    id SERIAL PRIMARY KEY,
    external_id VARCHAR(255) UNIQUE NOT NULL,
    property_type VARCHAR(50) NOT NULL,
    price NUMERIC NOT NULL,
    rooms_count INTEGER NOT NULL,
    city BIGINT NOT NULL,
    insert_time TIMESTAMP,
    address TEXT,
    square_feet NUMERIC,
    floor INTEGER,
    total_floors INTEGER,
    description TEXT,
    resource_url TEXT,
    original_currency VARCHAR(10) DEFAULT 'UAH'
);

CREATE TABLE IF NOT EXISTS ad_images (
  id SERIAL PRIMARY KEY,
  ad_id BIGINT REFERENCES ads(id) ON DELETE CASCADE,
  image_url TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS user_filters (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    property_type VARCHAR(50),
    city BIGINT,
    rooms_count INTEGER[],
    price_min NUMERIC,
    price_max NUMERIC,
    is_paused BOOLEAN DEFAULT FALSE,
    floor_max INTEGER,
    is_not_first_floor BOOLEAN,
    is_not_last_floor BOOLEAN,
    is_last_floor_only BOOLEAN,
    pets_allowed BOOLEAN,
    without_broker BOOLEAN
);

-- Drop the unique constraint
ALTER TABLE user_filters
  DROP CONSTRAINT IF EXISTS user_filters_user_id_unique;

CREATE TABLE subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    property_type VARCHAR(50),
    city BIGINT,
    rooms_count INTEGER[],
    price_min NUMERIC,
    price_max NUMERIC,
    created_at TIMESTAMP DEFAULT NOW()
);


CREATE TABLE favorite_ads (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    ad_id BIGINT REFERENCES ads(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Possibly you add a unique constraint so user cannot favorite the same ad multiple times
ALTER TABLE favorite_ads
  ADD CONSTRAINT unique_favorite_per_user UNIQUE (user_id, ad_id);


CREATE TABLE IF NOT EXISTS ad_phones (
    id SERIAL PRIMARY KEY,
    ad_id BIGINT REFERENCES ads(id) ON DELETE CASCADE,
    phone TEXT,          -- For phone numbers (e.g., "tel: +380663866058")
    viber_link TEXT      -- For a Viber chat link if available
);

CREATE TABLE IF NOT EXISTS payment_orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    order_id VARCHAR(255) UNIQUE NOT NULL,
    amount NUMERIC NOT NULL,
    period VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS payment_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    order_id VARCHAR(255) UNIQUE NOT NULL,
    amount NUMERIC NOT NULL,
    payment_date TIMESTAMP DEFAULT NOW(),
    subscription_period VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    transaction_id VARCHAR(255),
    card_mask VARCHAR(50),
    payment_details JSONB
);

-- Create tables for verification
CREATE TABLE verification_codes (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    phone_number VARCHAR(20) NOT NULL,
    code VARCHAR(6) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,
    attempts INT DEFAULT 0
);

CREATE TABLE email_verification_tokens (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    token VARCHAR(64) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,
    attempts INT DEFAULT 0
);

-- Create a function to sanitize phone numbers
CREATE OR REPLACE FUNCTION sanitize_phone_number(phone TEXT)
RETURNS TEXT AS $$
DECLARE
    sanitized TEXT;
BEGIN
    -- Remove all non-digit characters except '+'
    sanitized := regexp_replace(phone, '[^0-9+]', '', 'g');

    -- Ensure it starts with '+'
    IF NOT sanitized LIKE '+%' THEN
        sanitized := '+' || sanitized;
    END IF;

    RETURN sanitized;
END;
$$ LANGUAGE plpgsql;

-- Create trigger function for updating users.updated_at
CREATE OR REPLACE FUNCTION update_users_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for users table
CREATE TRIGGER update_users_updated_at_trigger
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_users_updated_at();

-- High-priority indexes
CREATE INDEX IF NOT EXISTS idx_ads_resource_url ON ads (resource_url);
CREATE INDEX IF NOT EXISTS idx_ad_images_ad_id ON ad_images (ad_id);
CREATE INDEX IF NOT EXISTS idx_ad_phones_ad_id ON ad_phones (ad_id);
CREATE INDEX IF NOT EXISTS idx_ads_insert_time ON ads (insert_time DESC);
CREATE INDEX IF NOT EXISTS idx_favorite_ads_created_at ON favorite_ads (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_verification_codes_phone_number ON verification_codes (phone_number);
CREATE INDEX IF NOT EXISTS idx_email_verification_tokens_email ON email_verification_tokens (email);
CREATE INDEX IF NOT EXISTS idx_users_phone_number ON users (phone_number);
CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

-- Query-specific indexes
CREATE INDEX IF NOT EXISTS idx_ads_filter_query ON ads (city, property_type, price, rooms_count, insert_time DESC);
CREATE INDEX IF NOT EXISTS idx_user_filters_active ON user_filters (user_id, city, property_type)
WHERE is_paused = FALSE;

-- Grant appropriate permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON verification_codes TO current_user;
GRANT USAGE, SELECT ON SEQUENCE verification_codes_id_seq TO current_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON email_verification_tokens TO current_user;
GRANT USAGE, SELECT ON SEQUENCE email_verification_tokens_id_seq TO current_user;