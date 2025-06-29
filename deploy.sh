#!/bin/bash

# ==============================================================================
# AISavvy Deployment Script (Gemini API Edition)
#
# This script automates the setup and deployment of the AISavvy application.
# It builds and starts all necessary Docker containers and provides the
# access URL for the user interface.
# ==============================================================================

# --- Configuration: Define colors for user-friendly output ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Starting the AISavvy (Gemini Edition) deployment...${NC}"

# Step 1: Build and start the Docker containers in detached mode
echo -e "\n${YELLOW}[1/2] Building and starting all services (Postgres, API, UI, Telegram)...${NC}"
docker compose up --build -d
docker compose exec ollama ollama pull llama3
cd monitoring 
docker compose up -d
cd ../web_server
docker compose up -d
# Check if the last command was successful
if [ $? -ne 0 ]; then
    echo -e "\n${RED}------------------------------------------------------------------${NC}"
    echo -e "${RED}Error: Docker Compose failed to start the services.${NC}"
    echo -e "${RED}Please check for errors by running 'docker compose logs'${NC}"
    echo -e "${RED}------------------------------------------------------------------${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Services started successfully in the background!${NC}"

# Step 2: Announce completion and provide the URL
echo -e "\n${YELLOW}[2/2] Deployment complete!${NC}"
echo -e "\n${GREEN}=====================================================${NC}"
echo -e "${GREEN}    🚀 Your AISavvy application is ready! 🚀    ${NC}"
echo -e "${GREEN}=====================================================${NC}"
echo -e "\nAccess the web UI at the following URL:"
echo -e "${YELLOW}👉 http://localhost:8501 ${NC}\n"
