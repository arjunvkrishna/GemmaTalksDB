-- =============================================================================
-- AISavvy Restaurant Database Initialization Script (Corrected)
-- =============================================================================

-- To make this script re-runnable, we drop existing tables first.
DROP TABLE IF EXISTS miscellaneous_expense CASCADE;
DROP TABLE IF EXISTS sales CASCADE;
DROP TABLE IF EXISTS purchase CASCADE;
DROP TABLE IF EXISTS kitchen_products CASCADE;
DROP TABLE IF EXISTS salary CASCADE;
DROP TABLE IF EXISTS chef CASCADE;
DROP TABLE IF EXISTS employee CASCADE;


-- =============================================================================
-- 1. Create Tables
-- =============================================================================
CREATE TABLE employee (
    employee_id SERIAL PRIMARY KEY,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    role VARCHAR(50) NOT NULL,
    hire_date DATE NOT NULL,
    phone_number VARCHAR(20)
);

CREATE TABLE chef (
    chef_id SERIAL PRIMARY KEY,
    employee_id INT UNIQUE NOT NULL,
    specialty VARCHAR(100),
    certification VARCHAR(100),
    CONSTRAINT fk_chef_employee FOREIGN KEY(employee_id) REFERENCES employee(employee_id) ON DELETE CASCADE
);

CREATE TABLE salary (
    salary_id SERIAL PRIMARY KEY,
    employee_id INT NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    pay_date DATE NOT NULL,
    bonus NUMERIC(8, 2) DEFAULT 0.00,
    CONSTRAINT fk_salary_employee FOREIGN KEY(employee_id) REFERENCES employee(employee_id) ON DELETE CASCADE
);

CREATE TABLE kitchen_products (
    product_id SERIAL PRIMARY KEY,
    product_name VARCHAR(100) NOT NULL,
    quantity_on_hand NUMERIC(10, 2) NOT NULL,
    unit VARCHAR(20) NOT NULL,
    supplier VARCHAR(100)
);

CREATE TABLE purchase (
    purchase_id SERIAL PRIMARY KEY,
    product_id INT NOT NULL,
    quantity_purchased NUMERIC(10, 2) NOT NULL,
    purchase_cost NUMERIC(10, 2) NOT NULL,
    purchase_date DATE NOT NULL,
    CONSTRAINT fk_purchase_product FOREIGN KEY(product_id) REFERENCES kitchen_products(product_id)
);

CREATE TABLE sales (
    sale_id SERIAL PRIMARY KEY,
    employee_id INT,
    sale_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_amount NUMERIC(10, 2) NOT NULL,
    payment_method VARCHAR(20) CHECK (payment_method IN ('Cash', 'Credit Card', 'Online')),
    CONSTRAINT fk_sales_employee FOREIGN KEY(employee_id) REFERENCES employee(employee_id)
);

CREATE TABLE miscellaneous_expense (
    expense_id SERIAL PRIMARY KEY,
    expense_name VARCHAR(100) NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    expense_date DATE NOT NULL,
    category VARCHAR(50),
    description TEXT
);


-- =============================================================================
-- 2. Populate Tables with Data
-- =============================================================================
INSERT INTO employee (first_name, last_name, role, hire_date, phone_number) VALUES
('Arjun', 'Verma', 'Head Chef', '2022-01-15', '9876543210'),
('Priya', 'Sharma', 'Sous Chef', '2022-08-01', '9876543211'),
('Rohan', 'Singh', 'Manager', '2021-11-20', '9876543212'),
('Sneha', 'Gupta', 'Waiter', '2023-03-10', '9876543213'),
('Vikram', 'Patel', 'Waiter', '2023-03-10', '9876543214'),
('Emily', 'White', 'Marketing Head', '2023-09-01', '9876543215');

INSERT INTO chef (employee_id, specialty, certification) VALUES
(1, 'Continental Cuisine', 'Le Cordon Bleu'),
(2, 'Indian Cuisine', 'IHM');

INSERT INTO salary (employee_id, amount, pay_date, bonus) VALUES
(1, 80000.00, '2024-05-31', 5000.00),
(2, 60000.00, '2024-05-31', 2500.00),
(3, 75000.00, '2024-05-31', 0.00),
(4, 30000.00, '2024-05-31', 1000.00),
(5, 30000.00, '2024-05-31', 1500.00),
(6, 72000.00, '2024-05-31', 3000.00);

INSERT INTO kitchen_products (product_name, quantity_on_hand, unit, supplier) VALUES
('Tomatoes', 20.5, 'kg', 'Local Farms Inc.'),
('Chicken Breast', 15.0, 'kg', 'Quality Meats'),
('Olive Oil', 10.0, 'liters', 'Imports & Co.'),
('Basmati Rice', 50.0, 'kg', 'Grain Traders');

INSERT INTO purchase (product_id, quantity_purchased, purchase_cost, purchase_date) VALUES
(1, 10.0, 500.00, '2024-06-20'),
(2, 20.0, 8000.00, '2024-06-19');

INSERT INTO sales (employee_id, sale_date, total_amount, payment_method) VALUES
(4, '2024-06-25 20:30:00+05:30', 2550.50, 'Credit Card'),
(5, '2024-06-25 21:00:00+05:30', 1780.00, 'Cash'),
(4, '2024-06-26 13:15:00+05:30', 3200.00, 'Online');

INSERT INTO miscellaneous_expense (expense_name, amount, expense_date, category, description) VALUES
('Cleaning Supplies', 3500.00, '2024-06-05', 'Maintenance', 'Monthly cleaning supplies order'),
('Gas Cylinder Refill', 2200.00, '2024-06-15', 'Utilities', 'Refill for main kitchen line');


-- =============================================================================
-- 3. Create Read-Only User and Grant Permissions
-- This section now comes AFTER table creation and data insertion.
-- =============================================================================

-- Use your preferred password here. This must match the password in your .env file.
CREATE USER aisavvy WITH PASSWORD 'my_password';

-- Grant permission for the user to connect to the database.
GRANT CONNECT ON DATABASE mydb TO aisavvy;

-- Grant permission to use the 'public' schema where tables reside.
GRANT USAGE ON SCHEMA public TO aisavvy;

-- Grant ONLY SELECT (read) permissions on all current tables in the schema.
GRANT SELECT ON ALL TABLES IN SCHEMA public TO aisavvy;

-- Ensure that any tables created in the future will also be readable.
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO aisavvy;

