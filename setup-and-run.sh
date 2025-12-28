#!/bin/bash
# Setup and run script for macOS Calendar Exporter
# This script sets up a virtual environment, installs dependencies,
# and runs the macOS Calendar Exporter

# Stop on errors
set -e

# Variables
VENV_DIR="venv"
CONFIG_FILE=".env"
INTERACTIVE=true

# Check if --no-interactive flag is present
for arg in "$@"; do
  if [ "$arg" == "--no-interactive" ]; then
    INTERACTIVE=false
    echo "Running in non-interactive mode"
  fi
done

# Terminal colors
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
BLUE="\033[0;34m"
NC="\033[0m" # No Color

echo -e "${BLUE}===== macOS Calendar Exporter Setup and Run =====${NC}"

# Function to check if a command exists
command_exists() {
  command -v "$1" >/dev/null 2>&1
}

# Check Python installation
if ! command_exists python3; then
  echo -e "${RED}Error: Python 3 not found. Please install Python 3 first.${NC}"
  exit 1
fi

echo -e "${GREEN}Python 3 found.${NC}"
python3 --version

# Swift's EventKit is now used for calendar access, external tools are no longer required

# Create virtual environment if it doesn't exist
echo -e "\n${BLUE}Setting up virtual environment...${NC}"
if [ -d "$VENV_DIR" ]; then
  echo -e "${GREEN}Virtual environment already exists.${NC}"
else
  echo -e "${YELLOW}Creating new virtual environment...${NC}"
  python3 -m venv "$VENV_DIR"
fi

# Activate virtual environment
echo -e "${BLUE}Activating virtual environment...${NC}"
source "$VENV_DIR/bin/activate"

# Verify activation
PYTHON_PATH=$(which python)
if [[ "$PYTHON_PATH" == *"$VENV_DIR"* ]]; then
  echo -e "${GREEN}Virtual environment activated: $PYTHON_PATH${NC}"
  
  # Install or upgrade pip
  echo -e "\n${BLUE}Upgrading pip...${NC}"
  pip install --upgrade pip
  
  # Install requirements
  echo -e "\n${BLUE}Installing dependencies...${NC}"
  pip install -r requirements.txt
  
  # Install the package in development mode
  echo -e "\n${BLUE}Installing macOS Calendar Exporter in development mode...${NC}"
  pip install -e .
else
  echo -e "${RED}Failed to activate virtual environment properly.${NC}"
  echo -e "${YELLOW}Trying fallback method...${NC}"
  
  # Fallback to direct paths
  echo -e "\n${BLUE}Upgrading pip...${NC}"
  "$VENV_DIR/bin/python" -m pip install --upgrade pip
  
  # Install requirements
  echo -e "\n${BLUE}Installing dependencies...${NC}"
  "$VENV_DIR/bin/python" -m pip install -r requirements.txt
  
  # Install the package in development mode
  echo -e "\n${BLUE}Installing macOS Calendar Exporter in development mode...${NC}"
  "$VENV_DIR/bin/python" -m pip install -e .
fi

# Check for config file
if [ ! -f "$CONFIG_FILE" ]; then
  echo -e "\n${YELLOW}Config file not found. Creating from example...${NC}"
  if [ -f ".env.example" ]; then
    cp .env.example "$CONFIG_FILE"
    echo -e "${GREEN}Created $CONFIG_FILE from example. Please edit it with your settings.${NC}"
  else
    echo -e "${RED}Error: .env.example not found.${NC}"
    touch "$CONFIG_FILE"
    echo "# macOS Calendar Exporter Configuration" > "$CONFIG_FILE"
    echo "CALENDAR_NAMES=Calendar" >> "$CONFIG_FILE"
    echo "DAYS_AHEAD=30" >> "$CONFIG_FILE"
    echo "ICS_FILE=./calendar_export.ics" >> "$CONFIG_FILE"
    echo "TITLE_LENGTH_LIMIT=36" >> "$CONFIG_FILE"
    echo "ENABLE_SFTP=false" >> "$CONFIG_FILE"
    echo -e "${GREEN}Created basic $CONFIG_FILE. Please edit it with your settings.${NC}"
  fi
else
  echo -e "\n${GREEN}Config file $CONFIG_FILE found.${NC}"
fi

# Run calendar access test
echo -e "\n${BLUE}Testing calendar access...${NC}"
"$VENV_DIR/bin/python" -c "
try:
    from mac_calendar_exporter.main import MacCalendarExporter
    exporter = MacCalendarExporter()
    calendar_accessor = exporter._get_calendar_accessor()
    if calendar_accessor:
        print('\033[0;32mCalendar accessor initialized successfully.\033[0m')
        calendars = calendar_accessor.list_calendars()
        print(f'Found {len(calendars)} calendars:')
        for cal in calendars:
            print(f'  - {cal[\"title\"]}')
    else:
        print('\033[0;33mUsing mock data.\033[0m')
except Exception as e:
    print(f'\033[0;31mError testing calendar access: {e}\033[0m')
"

# Ask user if they want to run the exporter (only in interactive mode)
if [ "$INTERACTIVE" = true ]; then
  echo -e "\n${BLUE}Do you want to run the macOS Calendar Exporter now? (y/n)${NC}"
  read -r run_exporter
  
  if [[ $run_exporter =~ ^[Yy]$ ]]; then
    run_it=true
  else
    run_it=false
    echo -e "\n${YELLOW}Skipping execution.${NC}"
    echo -e "You can run the exporter later with: python -m mac_calendar_exporter.main"
  fi
else
  # In non-interactive mode, always run the exporter
  run_it=true
fi

if [ "$run_it" = true ]; then
  echo -e "\n${BLUE}Running macOS Calendar Exporter...${NC}"
  "$VENV_DIR/bin/python" -m mac_calendar_exporter.main
  
  # Check exit status
  if [ $? -eq 0 ]; then
    echo -e "\n${GREEN}macOS Calendar Exporter completed successfully.${NC}"
  else
    echo -e "\n${RED}macOS Calendar Exporter encountered errors.${NC}"
    echo -e "Check the logs above for details."
  fi
else
  echo -e "\n${YELLOW}Skipping execution.${NC}"
  echo -e "You can run the exporter later with: python -m mac_calendar_exporter.main"
fi

echo -e "\n${BLUE}===== Setup Complete =====${NC}"
echo -e "To use the macOS Calendar Exporter in the future, activate the virtual environment:"
echo -e "  source $VENV_DIR/bin/activate"
echo -e "Then run:"
echo -e "  python -m mac_calendar_exporter.main"

# Deactivate virtual environment
deactivate

exit 0
