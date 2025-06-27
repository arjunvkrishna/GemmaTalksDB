# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /bot

# Install system dependencies needed for Matplotlib
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    libffi-dev \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY ./requirements.txt /bot/requirements.txt

# Install Python packages
RUN pip install --no-cache-dir --upgrade -r /bot/requirements.txt

# Copy the bot code into the container
COPY ./bot.py /bot/bot.py

# Run the bot when the container launches
CMD ["python", "bot.py"]