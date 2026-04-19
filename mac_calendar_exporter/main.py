#!/usr/bin/env python3
"""
macOS Calendar Exporter Main Module.

This module is the main entry point for the macOS Calendar exporter application,
which exports calendar events to ICS files and uploads them to an SFTP server.
"""

import os
import sys
import logging
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from mac_calendar_exporter.calendar.eventkit_calendar import EventKitCalendarAccess
from mac_calendar_exporter.calendar.mock_calendar import MockCalendarData  # Keeping mock data for fallback
from mac_calendar_exporter.ics.ics_generator import ICSGenerator
from mac_calendar_exporter.sftp.sftp_uploader import SFTPUploader
from mac_calendar_exporter.config.config_manager import ConfigManager


class MacCalendarExporter:
    """Main macOS Calendar exporter class that orchestrates the export process."""
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize the CalDAV exporter.
        
        Args:
            config: Optional configuration dictionary to override defaults
        """
        # Set up logging
        self._setup_logging()
        
        # Load configuration
        self.config_manager = ConfigManager()
        self.config = self.config_manager.get_config()
        
        # Override with any provided config
        if config:
            self.config.update(config)
            
        self.logger = logging.getLogger(__name__)
        self.logger.info("macOS Calendar Exporter initialized")
        
    def _setup_logging(self):
        """Configure logging for the application."""
        log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
        logging.basicConfig(
            level=getattr(logging, log_level),
            format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
            handlers=[logging.StreamHandler()]
        )
        
    def _get_calendar_accessor(self):
        """
        Get the calendar accessor using EventKit.
        
        Returns:
            An EventKitCalendarAccess instance
        """
        self.logger.info("Using Swift EventKit for calendar access")
        try:
            return EventKitCalendarAccess()
        except Exception as e:
            self.logger.error(f"Failed to initialize EventKit calendar accessor: {e}")
            return None

    def _apply_exclude_list(self, events: List[Dict], exclude_file: str) -> List[Dict]:
        """
        Filter out events whose event_id appears in the exclude list file.

        Args:
            events: List of event dictionaries
            exclude_file: Path to a text file containing one UUID per line

        Returns:
            Filtered list of events
        """
        self.logger.info(f"Exclude list path: {os.path.abspath(exclude_file)} — {'found' if os.path.exists(exclude_file) else 'not found'}")
        if not os.path.exists(exclude_file):
            return events

        with open(exclude_file) as f:
            excluded_ids = {line.strip() for line in f if line.strip() and not line.startswith('#')}

        if not excluded_ids:
            return events

        filtered = []
        for e in events:
            if e.get('event_id') in excluded_ids:
                self.logger.info(f"Excluding event id={e.get('event_id')} title={e.get('title')!r}")
            else:
                filtered.append(e)

        removed = len(events) - len(filtered)
        if removed:
            self.logger.info(f"Excluded {removed} event(s) via {exclude_file}")
        return filtered

    def export_calendar(self):
        """
        Export calendar events to an ICS file.
        
        Returns:
            str: Path to the generated ICS file, or None if export failed
        """
        try:
            # Get calendar accessor
            calendar_accessor = self._get_calendar_accessor()
            
            # Get calendar configuration
            calendar_names = self.config.get('calendar_names', ['Calendar'])
            days_ahead = self.config.get('days_ahead', 30)
            output_file = self.config.get('ics_file', './calendar_export.ics')
            
            # Calculate date range
            start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=days_ahead)
            
            self.logger.info(f"Exporting events from {start_date.strftime('%Y-%m-%d')} to "
                           f"{end_date.strftime('%Y-%m-%d')} for calendars: {', '.join(calendar_names)}")
            
            # Get events
            events = []
            if calendar_accessor is None:
                # Use mock data
                self.logger.info("Using mock calendar data")
                events = MockCalendarData.get_mock_events(
                    calendar_names=calendar_names,
                    start_date=start_date,
                    end_date=end_date
                )
            else:
                # Get events from real calendar
                events = calendar_accessor.get_events(
                    calendar_names=calendar_names,
                    start_date=start_date,
                    end_date=end_date
                )
            
            self.logger.info(f"Retrieved {len(events)} events")

            # Apply exclude list filter
            exclude_file = self.config.get('exclude_list_file', 'exclude-list.txt')
            events = self._apply_exclude_list(events, exclude_file)

            # Generate ICS file
            if events:
                ics_generator = ICSGenerator()
                calendar_name = self.config.get('ics_calendar_name', 'Exported Calendar')
                include_details = self.config.get('include_details', False)
                title_length_limit = self.config.get('title_length_limit', 36)
                ics_file = ics_generator.generate_ics(
                    events=events,
                    calendar_name=calendar_name,
                    output_file=output_file,
                    include_details=include_details,
                    title_length_limit=title_length_limit
                )
                self.logger.info(f"Generated ICS file: {ics_file}")
                return ics_file
            else:
                self.logger.warning("No events found, skipping ICS generation")
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to export calendar: {e}", exc_info=True)
            return None
            
    def upload_to_sftp(self, file_path: str):
        """
        Upload a file to an SFTP server.
        
        Args:
            file_path: Path to the file to upload
            
        Returns:
            bool: True if upload succeeded, False otherwise
        """
        if not file_path or not os.path.exists(file_path):
            self.logger.error(f"File does not exist: {file_path}")
            return False
            
        try:
            # Get SFTP configuration
            sftp_config = self.config.get('sftp', {})
            if not sftp_config:
                self.logger.error("SFTP configuration not provided")
                return False
                
            hostname = sftp_config.get('host')  # The config uses 'host' but SFTPUploader expects 'hostname'
            port = sftp_config.get('port', 22)
            username = sftp_config.get('username')
            remote_path = sftp_config.get('remote_path', '/')
            
            if not hostname or not username:
                self.logger.error("SFTP host and username are required")
                return False
                
            # Get password or key file
            password = sftp_config.get('password')
            key_file = sftp_config.get('key_file')
            
            if not password and not key_file:
                self.logger.error("Either SFTP password or key file is required")
                return False
                
            # Upload file
            uploader = SFTPUploader(
                hostname=hostname,
                port=port,
                username=username,
                password=password,
                key_file=key_file
            )
            
            success = uploader.upload_file(file_path, remote_path)
            
            if success:
                self.logger.info(f"Successfully uploaded {file_path} to {hostname}:{remote_path}")
                return True
            else:
                self.logger.error(f"Failed to upload {file_path}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to upload to SFTP: {e}", exc_info=True)
            return False
            
    def run(self):
        """
        Run the export and upload process.
        
        Returns:
            bool: True if the process succeeded, False otherwise
        """
        try:
            # Export calendar to ICS file
            ics_file = self.export_calendar()
            
            if not ics_file:
                self.logger.error("Calendar export failed")
                return False
                
            # Check if SFTP upload is enabled
            if self.config.get('enable_sftp', False):
                # Upload ICS file to SFTP server
                return self.upload_to_sftp(ics_file)
            else:
                self.logger.info("SFTP upload disabled")
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to run export process: {e}", exc_info=True)
            return False


def main():
    """Run the macOS Calendar exporter from the command line."""
    parser = argparse.ArgumentParser(description="Export calendar events to ICS and upload to SFTP")
    parser.add_argument("--config", help="Path to custom config file")
    args = parser.parse_args()
    
    config = None
    if args.config:
        try:
            config_manager = ConfigManager(config_path=args.config)
            config = config_manager.get_config()
        except Exception as e:
            print(f"Error loading config file: {e}")
            return 1
    
    exporter = MacCalendarExporter(config=config)
    success = exporter.run()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
