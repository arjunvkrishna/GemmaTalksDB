#!/bin/bash

# ==============================================================================
# GemmaTalksDB Deployment Script
#
# This script automates the setup and deployment of the GemmaTalksDB application.
# It builds and starts all necessary Docker containers, downloads the required
# LLM model, and provides the access URL for the user interface.
#
# Usage:
#   ./deploy.sh
# ==============================================================================

# --- Configuration: Define colors for user-friendly output ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# --- Main Script ---

echo -e "${YELLOW}Starting the GemmaTalksDB deployment...${NC}"

# Step 1: Build and start the Docker containers in detached mode
echo -e "\n${YELLOW}[1/3] Building and starting all services (Postgres, Ollama, API, UI)...${NC}"
docker-compose up --build -d

# Check if the last command was successful
if [ $? -ne 0 ]; then
    echo -e "\n${RED}------------------------------------------------------------------${NC}"
    echo -e "${RED}Error: Docker Compose failed to start the services.${NC}"
    echo -e "${RED}Please check for errors by running 'docker-compose logs'${NC}"
    echo -e "${RED}------------------------------------------------------------------${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Services started successfully in the background!${NC}"

# Step 2: Pull the Gemma LLM model
echo -e "\n${YELLOW}[2/3] Downloading the Gemma LLM model from Ollama...${NC}"
echo -e "${YELLOW}This may take a few minutes depending on your internet connection.${NC}"
docker-compose exec ollama ollama pull gemma:2b

# Check if the model pull was successful
if [ $? -ne 0 ]; then
    echo -e "\n${RED}------------------------------------------------------------------${NC}"
    echo -e "${RED}Error: Failed to download the Gemma model.${NC}"
    echo -e "${RED}Please check your internet connection and try running the command manually:${NC}"
    echo -e "${YELLOW}docker-compose exec ollama ollama pull gemma:2b${NC}"
    echo -e "${RED}------------------------------------------------------------------${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Gemma model downloaded successfully!${NC}"

# Step 3: Announce completion and provide the URL
echo -e "\n${YELLOW}[3/3] Deployment complete!${NC}"
echo -e "\n${GREEN}=====================================================${NC}"
echo -e "${GREEN}  🚀 Your GemmaTalksDB application is ready! 🚀  ${NC}"
echo -e "${GREEN}=====================================================${NC}"
echo -e "\nAccess the web UI at the following URL:"
echo -e "${YELLOW}👉 http://localhost:8501 ${NC}\n"
