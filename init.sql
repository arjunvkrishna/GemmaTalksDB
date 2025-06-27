REATE TABLE employee (
    employee_id SERIAL PRIMARY KEY,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    role VARCHAR(50) NOT NULL, -- e.g., 'Head Chef', 'Waiter', 'Manager'
    hire_date DATE NOT NULL,
    phone_number VARCHAR(20)
);

COMMENT ON TABLE employee IS 'Stores information about all restaurant staff.';


-- =============================================================================
-- 2. Chef Table
-- Stores specific details for employees who are chefs.
-- =============================================================================
CREATE TABLE chef (
    chef_id SERIAL PRIMARY KEY,
    employee_id INT UNIQUE NOT NULL,
    specialty VARCHAR(100), -- e.g., 'Pastry', 'Italian Cuisine', 'Grill'
    certification VARCHAR(100),
    CONSTRAINT fk_chef_employee
        FOREIGN KEY(employee_id)
        REFERENCES employee(employee_id)
        ON DELETE CASCADE
);

COMMENT ON TABLE chef IS 'Stores additional details for employees with the role of Chef.';


-- =============================================================================
-- 3. Salary Table
-- Tracks salary payments to employees over time.
-- =============================================================================
CREATE TABLE salary (
    salary_id SERIAL PRIMARY KEY,
    employee_id INT NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    pay_date DATE NOT NULL,
    bonus NUMERIC(8, 2) DEFAULT 0.00,
    CONSTRAINT fk_salary_employee
        FOREIGN KEY(employee_id)
        REFERENCES employee(employee_id)
        ON DELETE CASCADE
);

COMMENT ON TABLE salary IS 'Tracks historical salary and bonus payments to employees.';


-- =============================================================================
-- 4. Kitchen Products (Inventory)
-- Tracks all inventory items in the kitchen.
-- =============================================================================
CREATE TABLE kitchen_products (
    product_id SERIAL PRIMARY KEY,
    product_name VARCHAR(100) NOT NULL,
    quantity_on_hand NUMERIC(10, 2) NOT NULL,
    unit VARCHAR(20) NOT NULL, -- e.g., 'kg', 'liters', 'units'
    supplier VARCHAR(100)
);

COMMENT ON TABLE kitchen_products IS 'Inventory of all products used in the kitchen.';


-- =============================================================================
-- 5. Purchase Table
-- Logs all incoming purchases of kitchen products.
-- =============================================================================
CREATE TABLE purchase (
    purchase_id SERIAL PRIMARY KEY,
    product_id INT NOT NULL,
    quantity_purchased NUMERIC(10, 2) NOT NULL,
    purchase_cost NUMERIC(10, 2) NOT NULL,
    purchase_date DATE NOT NULL,
    CONSTRAINT fk_purchase_product
        FOREIGN KEY(product_id)
        REFERENCES kitchen_products(product_id)
);

COMMENT ON TABLE purchase IS 'Logs all procurement of kitchen inventory.';


-- =============================================================================
-- 6. Sales Table
-- Logs all customer sales transactions.
-- =============================================================================
CREATE TABLE sales (
    sale_id SERIAL PRIMARY KEY,
    employee_id INT, -- Waiter/Cashier who made the sale (can be NULL)
    sale_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_amount NUMERIC(10, 2) NOT NULL,
    payment_method VARCHAR(20) CHECK (payment_method IN ('Cash', 'Credit Card', 'Online')),
    CONSTRAINT fk_sales_employee
        FOREIGN KEY(employee_id)
        REFERENCES employee(employee_id)
);

COMMENT ON TABLE sales IS 'Tracks all sales transactions made at the restaurant.';


-- =============================================================================
-- 7. Miscellaneous Expense Table
-- Tracks other operational expenses.
-- =============================================================================
CREATE TABLE miscellaneous_expense (
    expense_id SERIAL PRIMARY KEY,
    expense_name VARCHAR(100) NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    expense_date DATE NOT NULL,
    category VARCHAR(50),
    description TEXT
);

COMMENT ON TABLE miscellaneous_expense IS 'Logs non-inventory related operational expenses.';


-- =============================================================================
-- POPULATE TABLES WITH REALISTIC DATA
-- =============================================================================

-- Populate Employees
INSERT INTO employee (first_name, last_name, role, hire_date, phone_number) VALUES
('Arjun', 'Verma', 'Head Chef', '2022-01-15', '9876543210'),
('Priya', 'Sharma', 'Sous Chef', '2022-08-01', '9876543211'),
('Rohan', 'Singh', 'Manager', '2021-11-20', '9876543212'),
('Sneha', 'Gupta', 'Waiter', '2023-03-10', '9876543213'),
('Vikram', 'Patel', 'Waiter', '2023-03-10', '9876543214');

-- Populate Chefs
INSERT INTO chef (employee_id, specialty, certification) VALUES
(1, 'Continental Cuisine', 'Le Cordon Bleu'),
(2, 'Indian Cuisine', 'IHM');

-- Populate Salaries
INSERT INTO salary (employee_id, amount, pay_date, bonus) VALUES
(1, 80000.00, '2024-05-31', 5000.00),
(2, 60000.00, '2024-05-31', 2500.00),
(3, 75000.00, '2024-05-31', 0.00),
(4, 30000.00, '2024-05-31', 1000.00),
(5, 30000.00, '2024-05-31', 1500.00);

-- Populate Kitchen Products
INSERT INTO kitchen_products (product_name, quantity_on_hand, unit, supplier) VALUES
('Tomatoes', 20.5, 'kg', 'Local Farms Inc.'),
('Chicken Breast', 15.0, 'kg', 'Quality Meats'),
('Olive Oil', 10.0, 'liters', 'Imports & Co.'),
('Basmati Rice', 50.0, 'kg', 'Grain Traders');

-- Populate Purchases
INSERT INTO purchase (product_id, quantity_purchased, purchase_cost, purchase_date) VALUES
(1, 10.0, 500.00, '2024-06-20'),
(2, 20.0, 8000.00, '2024-06-19');

-- Populate Sales
INSERT INTO sales (employee_id, sale_date, total_amount, payment_method) VALUES
(4, '2024-06-25 20:30:00+05:30', 2550.50, 'Credit Card'),
(5, '2024-06-25 21:00:00+05:30', 1780.00, 'Cash'),
(4, '2024-06-26 13:15:00+05:30', 3200.00, 'Online');

-- Populate Miscellaneous Expenses
INSERT INTO miscellaneous_expense (expense_name, amount, expense_date, category, description) VALUES
('Cleaning Supplies', 3500.00, '2024-06-05', 'Maintenance', 'Monthly cleaning supplies order'),
('Gas Cylinder Refill', 2200.00, '2024-06-15', 'Utilities', 'Refill for main kitchen line');

-- Grant permissions to the read-only user
GRANT CONNECT ON DATABASE mydb TO aisavvy;
GRANT USAGE ON SCHEMA public TO aisavvy;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO aisavvy;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO aisavvy;

