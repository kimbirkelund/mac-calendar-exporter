#!/usr/bin/env python3
"""
Configuration Manager Module.

This module handles reading and writing configuration for the CalDAV Exporter.
It supports configuration from files, environment variables, and secure storage.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import keyring
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Default config file location
DEFAULT_CONFIG_PATH = os.path.expanduser("~/.config/caldav-exporter/config.json")
DEFAULT_CONFIG_DIR = os.path.dirname(DEFAULT_CONFIG_PATH)

# Keyring service name for secure credential storage
KEYRING_SERVICE = "caldav-exporter"


class ConfigManager:
    """Manage configuration settings for CalDAV Exporter."""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the ConfigManager.
        
        Args:
            config_path: Path to configuration file (optional)
        """
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self.config = self._load_default_config()
        
        # Load configuration from file if it exists
        if os.path.isfile(self.config_path):
            self.load_config()
        
        # Load environment variables
        load_dotenv()
        self._apply_env_vars()

    def _load_default_config(self) -> Dict[str, Any]:
        """
        Load default configuration settings.
        
        Returns:
            Dict[str, Any]: Default configuration dictionary
        """
        return {
            "calendar": {
                "names": [],  # List of calendar names to export (empty means all)
                "days_ahead": 30,  # Number of days ahead to export
                "output_file": os.path.expanduser("~/calendar_export.ics"),
                "output_name": "Exported Calendar",
                "title_length_limit": 36  # Maximum length of event titles, 0 for unlimited
            },
            "sftp": {
                "hostname": "",
                "port": 22,
                "username": "",
                "key_file": "",
                "remote_path": "/calendar/calendar.ics",
                "create_dirs": True
            },
            "schedule": {
                "enabled": False,
                "interval": "daily",  # daily, hourly
                "time": "04:00"  # For daily schedule, time to run
            }
        }

    def load_config(self) -> Dict[str, Any]:
        """
        Load configuration from file.
        
        Returns:
            Dict[str, Any]: Loaded configuration
        """
        try:
            with open(self.config_path, "r") as f:
                loaded_config = json.load(f)
                
            # Update config with loaded values, preserving defaults for missing values
            self._update_nested_dict(self.config, loaded_config)
            logger.info(f"Loaded configuration from {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to load configuration from {self.config_path}: {e}")
        
        return self.config

    def save_config(self) -> bool:
        """
        Save configuration to file.
        
        Returns:
            bool: True if save was successful, False otherwise
        """
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            
            # Save non-sensitive configuration to file
            config_to_save = self._get_saveable_config()
            with open(self.config_path, "w") as f:
                json.dump(config_to_save, f, indent=2)
                
            logger.info(f"Saved configuration to {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save configuration to {self.config_path}: {e}")
            return False

    def _get_saveable_config(self) -> Dict[str, Any]:
        """
        Get a copy of the config without sensitive information.
        
        Returns:
            Dict[str, Any]: Config without sensitive info
        """
        # Create a deep copy
        import copy
        config_copy = copy.deepcopy(self.config)
        
        # Remove sensitive fields (don't save passwords to file)
        if "sftp" in config_copy and "password" in config_copy["sftp"]:
            del config_copy["sftp"]["password"]
            
        return config_copy

    def _update_nested_dict(self, target: Dict, source: Dict) -> None:
        """
        Update a nested dictionary with values from another dictionary.
        
        Args:
            target: Target dictionary to update
            source: Source dictionary with new values
        """
        for key, value in source.items():
            if isinstance(value, dict) and key in target and isinstance(target[key], dict):
                self._update_nested_dict(target[key], value)
            else:
                target[key] = value

    def _apply_env_vars(self) -> None:
        """Apply environment variables to configuration."""
        # Calendar type
        if os.environ.get("CALENDAR_TYPE"):
            self.config["calendar_type"] = os.environ.get("CALENDAR_TYPE")
        
        # Calendar names
        if os.environ.get("CALENDAR_NAMES"):
            # Convert comma-separated string to list
            calendar_names = [name.strip() for name in os.environ.get("CALENDAR_NAMES").split(",")]
            self.config["calendar_names"] = calendar_names
        elif os.environ.get("CALDAV_CALENDARS"):  # Backward compatibility
            # Convert comma-separated string to list
            calendar_names = [name.strip() for name in os.environ.get("CALDAV_CALENDARS").split(",")]
            self.config["calendar_names"] = calendar_names
            
        # Days ahead
        if os.environ.get("DAYS_AHEAD"):
            try:
                self.config["days_ahead"] = int(os.environ.get("DAYS_AHEAD"))
            except ValueError:
                pass
        elif os.environ.get("CALDAV_DAYS_AHEAD"):  # Backward compatibility
            try:
                self.config["days_ahead"] = int(os.environ.get("CALDAV_DAYS_AHEAD"))
            except ValueError:
                pass
        
        # ICS file path
        if os.environ.get("ICS_FILE"):
            self.config["ics_file"] = os.path.expanduser(os.environ.get("ICS_FILE"))
        elif os.environ.get("CALDAV_OUTPUT_FILE"):  # Backward compatibility
            self.config["ics_file"] = os.path.expanduser(os.environ.get("CALDAV_OUTPUT_FILE"))
            
        # ICS calendar name
        if os.environ.get("ICS_CALENDAR_NAME"):
            self.config["ics_calendar_name"] = os.environ.get("ICS_CALENDAR_NAME")
        elif os.environ.get("CALDAV_OUTPUT_NAME"):  # Backward compatibility
            self.config["ics_calendar_name"] = os.environ.get("CALDAV_OUTPUT_NAME")
        
        # Mock on failure setting
        if os.environ.get("USE_MOCK_ON_FAILURE"):
            self.config["use_mock_on_failure"] = os.environ.get("USE_MOCK_ON_FAILURE").lower() in ('true', 'yes', '1')
        
        # Include event details
        if os.environ.get("INCLUDE_DETAILS"):
            self.config["include_details"] = os.environ.get("INCLUDE_DETAILS").lower() in ('true', 'yes', '1')
            
        # Exclude declined / unanswered invites
        if os.environ.get("EXCLUDE_DECLINED"):
            self.config["exclude_declined"] = os.environ.get("EXCLUDE_DECLINED").lower() in ('true', 'yes', '1')
        
        # Email addresses that identify the user as an attendee
        if os.environ.get("MY_EMAILS"):
            self.config["my_emails"] = [e.strip() for e in os.environ.get("MY_EMAILS").split(',') if e.strip()]
            
        # Title length limit
        if os.environ.get("TITLE_LENGTH_LIMIT"):
            try:
                self.config["title_length_limit"] = int(os.environ.get("TITLE_LENGTH_LIMIT"))
            except ValueError:
                pass
        
        # Enable SFTP
        if os.environ.get("ENABLE_SFTP"):
            self.config["enable_sftp"] = os.environ.get("ENABLE_SFTP").lower() in ('true', 'yes', '1')
        
        # SFTP settings
        if os.environ.get("SFTP_HOST"):
            if "sftp" not in self.config:
                self.config["sftp"] = {}
            self.config["sftp"]["host"] = os.environ.get("SFTP_HOST")
            
        if os.environ.get("SFTP_PORT"):
            if "sftp" not in self.config:
                self.config["sftp"] = {}
            try:
                self.config["sftp"]["port"] = int(os.environ.get("SFTP_PORT"))
            except ValueError:
                pass
                
        if os.environ.get("SFTP_USERNAME"):
            if "sftp" not in self.config:
                self.config["sftp"] = {}
            self.config["sftp"]["username"] = os.environ.get("SFTP_USERNAME")
        elif os.environ.get("SFTP_USER"):  # Backward compatibility
            if "sftp" not in self.config:
                self.config["sftp"] = {}
            self.config["sftp"]["username"] = os.environ.get("SFTP_USER")
            
        if os.environ.get("SFTP_KEY_FILE"):
            if "sftp" not in self.config:
                self.config["sftp"] = {}
            self.config["sftp"]["key_file"] = os.path.expanduser(os.environ.get("SFTP_KEY_FILE"))
            
        if os.environ.get("SFTP_REMOTE_PATH"):
            if "sftp" not in self.config:
                self.config["sftp"] = {}
            self.config["sftp"]["remote_path"] = os.environ.get("SFTP_REMOTE_PATH")
        elif os.environ.get("SFTP_PATH"):  # Backward compatibility
            if "sftp" not in self.config:
                self.config["sftp"] = {}
            self.config["sftp"]["remote_path"] = os.environ.get("SFTP_PATH")
        
        # Password (only set in memory, not saved to file)
        if os.environ.get("SFTP_PASSWORD"):
            if "sftp" not in self.config:
                self.config["sftp"] = {}
            self.config["sftp"]["password"] = os.environ.get("SFTP_PASSWORD")
        elif os.environ.get("SFTP_PASS"):  # Backward compatibility
            if "sftp" not in self.config:
                self.config["sftp"] = {}
            self.config["sftp"]["password"] = os.environ.get("SFTP_PASS")

    def get_sftp_password(self) -> Optional[str]:
        """
        Get SFTP password from secure storage.
        
        Returns:
            Optional[str]: SFTP password or None if not set
        """
        if os.environ.get("SFTP_PASS"):
            return os.environ.get("SFTP_PASS")
            
        if not self.config["sftp"]["username"] or not self.config["sftp"]["hostname"]:
            return None
            
        # Create a keyring key using username and hostname
        key = f"{self.config['sftp']['username']}@{self.config['sftp']['hostname']}"
        
        try:
            return keyring.get_password(KEYRING_SERVICE, key)
        except Exception as e:
            logger.error(f"Failed to get SFTP password from keyring: {e}")
            return None

    def set_sftp_password(self, password: str) -> bool:
        """
        Set SFTP password in secure storage.
        
        Args:
            password: Password to store
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.config["sftp"]["username"] or not self.config["sftp"]["hostname"]:
            logger.error("Cannot set password: Username or hostname not configured")
            return False
            
        # Create a keyring key using username and hostname
        key = f"{self.config['sftp']['username']}@{self.config['sftp']['hostname']}"
        
        try:
            keyring.set_password(KEYRING_SERVICE, key, password)
            logger.info(f"Saved SFTP password for {key}")
            return True
        except Exception as e:
            logger.error(f"Failed to save SFTP password to keyring: {e}")
            return False

    def get_calendar_config(self) -> Dict[str, Any]:
        """
        Get calendar configuration.
        
        Returns:
            Dict[str, Any]: Calendar configuration
        """
        return self.config["calendar"]

    def get_sftp_config(self) -> Dict[str, Any]:
        """
        Get SFTP configuration including password from secure storage.
        
        Returns:
            Dict[str, Any]: SFTP configuration
        """
        config = dict(self.config["sftp"])
        password = self.get_sftp_password()
        if password:
            config["password"] = password
        return config

    def get_schedule_config(self) -> Dict[str, Any]:
        """
        Get scheduling configuration.
        
        Returns:
            Dict[str, Any]: Scheduling configuration
        """
        return self.config["schedule"]
        
    def get_config(self) -> Dict[str, Any]:
        """
        Get the complete configuration.
        
        Returns:
            Dict[str, Any]: Complete configuration dictionary
        """
        return self.config


if __name__ == "__main__":
    # Simple test when run directly
    logging.basicConfig(level=logging.INFO)
    
    # Create config manager with temporary path
    import tempfile
    temp_dir = tempfile.mkdtemp()
    temp_config = os.path.join(temp_dir, "config.json")
    
    cm = ConfigManager(temp_config)
    
    # Set some config values
    cm.config["calendar"]["names"] = ["Work", "Personal"]
    cm.config["sftp"]["hostname"] = "sftp.example.com"
    cm.config["sftp"]["username"] = "user"
    
    # Set a test password securely
    cm.set_sftp_password("test_password")
    
    # Save config
    cm.save_config()
    
    # Load config again
    cm2 = ConfigManager(temp_config)
    
    # Print config
    print(json.dumps(cm2.config, indent=2))
    
    # Print password
    print(f"Retrieved password: {cm2.get_sftp_password()}")
    
    # Clean up
    import shutil
    shutil.rmtree(temp_dir)
