#!/bin/bash

# ==============================================================================
# AISavvy Deployment Script
#
# This script automates the setup and deployment of the AISavvy application.
# It builds and starts all necessary Docker containers, provides status updates,
# and displays the final access URLs for the user interface and monitoring.
#
# Last Updated: 29 June 2025
# ==============================================================================

# --- Configuration: Define colors and symbols for user-friendly output ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Symbols
CHECKMARK="✅"
CROSSMARK="❌"
SPINNER_CHARS="/-\\|"

# --- Helper Functions for Logging and Status ---

# Function to log a major step
log_step() {
    echo -e "\n${BLUE}▸ $1${NC}"
}

# Function to execute a command with a spinner and error handling
execute() {
    local cmd="$1"
    local msg="$2"
    local log_file="/tmp/deploy_log.txt"

    # Start the command in the background, redirecting output to a log file
    eval "$cmd" > "$log_file" 2>&1 &
    local pid=$!

    # Show spinner
    printf "${YELLOW}  %s${NC} %s" " " "$msg"
    local i=0
    while ps -p $pid > /dev/null; do
        i=$(( (i+1) % 4 ))
        printf "\r${YELLOW}  %s${NC} %s" "${SPINNER_CHARS:$i:1}" "$msg"
        sleep 0.1
    done
    wait $pid
    local exit_code=$?

    # Check exit code and report status
    if [ $exit_code -eq 0 ]; then
        printf "\r${GREEN}${CHECKMARK}${NC} %s... Done!${NC}\n" "$msg"
    else
        printf "\r${RED}${CROSSMARK}${NC} %s... Failed!${NC}\n" "$msg"
        echo -e "\n${RED}------------------------- ERROR LOG -------------------------${NC}"
        cat "$log_file"
        echo -e "${RED}-----------------------------------------------------------${NC}"
        echo -e "${RED}Deployment aborted due to an error.${NC}\n"
        rm -f "$log_file"
        exit 1
    fi
    rm -f "$log_file"
}

# --- Main Deployment Logic ---

# Clean up log file on exit
trap 'rm -f /tmp/deploy_log.txt' EXIT

clear
echo -e "${YELLOW}🚀 Starting the AISavvy (Gemini Edition) Deployment...${NC}"

log_step "[1/5] Building and starting main services (Postgres, API, UI)..."
execute "docker compose up --build -d" "Launching main containers"

log_step "[2/5] Pulling LLM model (llama3)..."
echo -e "${YELLOW}  ℹ️  This may take several minutes depending on your internet connection.${NC}"
execute "docker compose exec ollama ollama pull llama3" "Downloading Llama 3 model via Ollama"

log_step "[3/5] Starting monitoring service..."
(cd monitoring && execute "docker compose up -d" "Launching Netdata")

log_step "[4/5] Starting reverse proxy service..."
(cd web_server && execute "docker compose up -d" "Launching Nginx Proxy")

log_step "[5/5] Verifying service status..."
docker compose ps
echo -e "${GREEN}All services have been initiated.${NC}"

# --- Final Announcement ---
echo -e "\n${GREEN}=====================================================${NC}"
echo -e "${GREEN}    🎉 Deployment Complete! Your application is ready. 🎉    ${NC}"
echo -e "${GREEN}=====================================================${NC}"
echo -e "\nAccess the web UI at the following URL:"
echo -e "${YELLOW}👉 http://localhost:8501 ${NC}"
echo -e "\nAccess the Netdata real-time monitoring dashboard at:"
echo -e "${YELLOW}👉 http://localhost:19999 ${NC}\n"