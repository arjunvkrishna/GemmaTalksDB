-- (The CREATE TABLE statements are the same)
CREATE TABLE departments (...);
CREATE TABLE employees (...);

-- (The INSERT for departments is the same)
INSERT INTO departments (department_name, manager) VALUES (...);

-- --- UPDATED: Employee data now includes a person in Marketing ---
INSERT INTO employees (first_name, last_name, email, hire_date, salary, department_id) VALUES
('John', 'Doe', 'john.doe@example.com', '2023-01-15', 90000.00, 1),
('Jane', 'Smith', 'jane.smith@example.com', '2022-03-20', 110000.00, 1),
('Peter', 'Jones', 'peter.jones@example.com', '2023-05-10', 65000.00, 2),
('Mary', 'Davis', 'mary.davis@example.com', '2021-08-01', 80000.00, 3),
('David', 'Wilson', 'david.wilson@example.com', '2023-11-22', 75000.00, 3),
('Susan', 'Taylor', 'susan.taylor@example.com', '2024-02-18', 95000.00, 1),
('Emily', 'White', 'emily.white@example.com', '2023-09-01', 72000.00, 4); -- <-- New Marketing Employee

-- (The user creation and grant statements are the same)
CREATE USER aisavvy WITH PASSWORD ...;
GRANT ...;