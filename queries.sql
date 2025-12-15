-- Capstone Analytics Queries
-- Database: gold_jsanghvi
-- All 5 required queries for the homework assignment

-- Query 1: Conversion Funnel
-- For each product, calculate view → add_to_cart → purchase conversion rates
SELECT 
    product_id,
    category,
    SUM(CASE WHEN event_type = 'page_view' THEN 1 ELSE 0 END) AS views,
    SUM(CASE WHEN event_type = 'add_to_cart' THEN 1 ELSE 0 END) AS add_to_carts,
    SUM(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END) AS purchases,
    ROUND(CAST(SUM(CASE WHEN event_type = 'add_to_cart' THEN 1 ELSE 0 END) AS DOUBLE) / 
          NULLIF(SUM(CASE WHEN event_type = 'page_view' THEN 1 ELSE 0 END), 0) * 100, 2) AS view_to_cart_rate,
    ROUND(CAST(SUM(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END) AS DOUBLE) / 
          NULLIF(SUM(CASE WHEN event_type = 'add_to_cart' THEN 1 ELSE 0 END), 0) * 100, 2) AS cart_to_purchase_rate
FROM silver_jsanghvi.events_cleaned
WHERE product_id IS NOT NULL
GROUP BY product_id, category
ORDER BY views DESC
LIMIT 100
;

-- Query 2: Hourly Revenue
-- Total revenue by hour (price × quantity for purchases)
SELECT 
    event_date,
    event_hour,
    total_revenue,
    transaction_count
FROM gold_jsanghvi.hourly_revenue
ORDER BY event_date, event_hour
;

-- Query 3: Top 10 Products
-- Most frequently viewed products with view counts
SELECT 
    product_id,
    category,
    COUNT(*) AS view_count
FROM silver_jsanghvi.events_cleaned
WHERE event_type = 'page_view' AND product_id IS NOT NULL
GROUP BY product_id, category
ORDER BY view_count DESC
LIMIT 10
;

-- Query 4: Category Performance
-- Daily event counts (all types) grouped by category
SELECT 
    event_date,
    category,
    COUNT(*) AS event_count,
    SUM(CASE WHEN event_type = 'page_view' THEN 1 ELSE 0 END) AS page_views,
    SUM(CASE WHEN event_type = 'add_to_cart' THEN 1 ELSE 0 END) AS add_to_carts,
    SUM(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END) AS purchases
FROM silver_jsanghvi.events_cleaned
WHERE category IS NOT NULL
GROUP BY event_date, category
ORDER BY event_date, event_count DESC
;

-- Query 5: User Activity
-- Count of unique users and sessions per day
SELECT 
    event_date,
    COUNT(DISTINCT user_id) AS unique_users,
    COUNT(DISTINCT session_id) AS unique_sessions,
    COUNT(*) AS total_events
FROM silver_jsanghvi.events_cleaned
GROUP BY event_date
ORDER BY event_date
;
