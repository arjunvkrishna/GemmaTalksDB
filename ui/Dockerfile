# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY ./requirements.txt /app/requirements.txt

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

# Copy the rest of the application code into the container
COPY . /app

# Expose the port Streamlit runs on
EXPOSE 8501

# Set up a healthcheck to see if the app is running
HEALTHCHECK CMD streamlit hello --server.port=8501

# Run the application
CMD ["streamlit", "run", "ui.py", "--server.port=8501", "--server.address=0.0.0.0"]