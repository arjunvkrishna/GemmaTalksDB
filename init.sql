-- Create Departments Table
CREATE TABLE departments (
    department_id SERIAL PRIMARY KEY,
    department_name VARCHAR(100) NOT NULL UNIQUE,
    manager VARCHAR(100)
);

-- Create Employees Table
CREATE TABLE employees (
    employee_id SERIAL PRIMARY KEY,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    email VARCHAR(100) UNIQUE,
    hire_date DATE,
    salary NUMERIC(10, 2),
    department_id INT,
    CONSTRAINT fk_department
      FOREIGN KEY(department_id)
      REFERENCES departments(department_id)
);

-- Insert Data into Departments
INSERT INTO departments (department_name, manager) VALUES
('Engineering', 'Alice Johnson'),
('Human Resources', 'Bob Williams'),
('Sales', 'Charlie Brown'),
('Marketing', 'Diana Miller');

-- Insert Data into Employees
INSERT INTO employees (first_name, last_name, email, hire_date, salary, department_id) VALUES
('John', 'Doe', 'john.doe@example.com', '2023-01-15', 90000.00, 1),
('Jane', 'Smith', 'jane.smith@example.com', '2022-03-20', 110000.00, 1),
('Peter', 'Jones', 'peter.jones@example.com', '2023-05-10', 65000.00, 2),
('Mary', 'Davis', 'mary.davis@example.com', '2021-08-01', 80000.00, 3),
('David', 'Wilson', 'david.wilson@example.com', '2023-11-22', 75000.00, 3),
('Susan', 'Taylor', 'susan.taylor@example.com', '2024-02-18', 95000.00, 1);