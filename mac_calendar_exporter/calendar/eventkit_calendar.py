#!/usr/bin/env python3
"""
EventKit Calendar Access Module.

This module provides access to calendar data using Swift's EventKit framework.
It works by executing a Swift script that interfaces with EventKit and returns
JSON data with calendar information and events.
"""

import json
import logging
import os
import subprocess
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class EventKitCalendarAccess:
    """Access calendar data from macOS Calendar app using EventKit via Swift."""

    def __init__(self):
        """Initialize the EventKitCalendarAccess class."""
        logger.info("Initializing EventKit calendar access")
        self.script_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "eventkit_calendar.swift"
        )
        self.binary_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "eventkit_calendar"
        )
        
        # Compile Swift script to binary if needed
        self._ensure_binary_compiled()
        logger.info(f"Using EventKit binary at: {self.binary_path}")

    def _ensure_binary_compiled(self):
        """Compile the Swift script to a binary if it doesn't exist or is outdated."""
        needs_compile = False
        
        if not os.path.exists(self.binary_path):
            needs_compile = True
        elif os.path.exists(self.script_path):
            # Recompile if script is newer than binary
            script_mtime = os.path.getmtime(self.script_path)
            binary_mtime = os.path.getmtime(self.binary_path)
            if script_mtime > binary_mtime:
                needs_compile = True
        
        if needs_compile:
            logger.info("Compiling EventKit Swift script to binary...")
            try:
                import subprocess
                result = subprocess.run(
                    ["swiftc", self.script_path, "-o", self.binary_path, "-framework", "EventKit"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                logger.info("Successfully compiled EventKit binary")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to compile Swift script: {e.stderr}")
                raise RuntimeError(f"Failed to compile EventKit Swift script: {e.stderr}")

    def list_calendars(self) -> List[Dict[str, str]]:
        """
        Get a list of available calendars.
        
        Returns:
            List[Dict[str, str]]: List of dictionaries with calendar info
        """
        try:
            # Run the Swift script with --calendars operation
            result = self._run_script(["--calendars"])
            
            if not result or "error" in result:
                error_msg = result.get("error", "Unknown error") if result else "No result from script"
                logger.error(f"Failed to list calendars: {error_msg}")
                return []
            
            # Process the returned calendar list
            calendars_data = result.get("calendars", [])
            
            # Convert to the standard format used by other modules
            calendars = []
            for cal in calendars_data:
                calendar_dict = {
                    "title": cal.get("title", "Unknown"),
                    "id": cal.get("id", ""),
                    "type": cal.get("type", ""),
                    "source": cal.get("source", "")
                }
                calendars.append(calendar_dict)
                
            logger.info(f"Found {len(calendars)} calendars using EventKit")
            return calendars
        except Exception as e:
            logger.error(f"Failed to list calendars using EventKit: {e}")
            return []

    def get_events(
        self, 
        calendar_names: Optional[List[str]] = None, 
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        days_ahead: Optional[int] = 30
    ) -> List[Dict]:
        """
        Get events from specified calendars within the given date range.
        
        Args:
            calendar_names: List of calendar names to fetch events from. 
                           If None, all calendars are used.
            start_date: Start date for events. If None, today is used.
            end_date: End date for events. If None, calculated from days_ahead.
            days_ahead: Number of days ahead to fetch events if end_date is None.
            
        Returns:
            List[Dict]: List of event dictionaries
        """
        if start_date is None:
            start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            
        if end_date is None and days_ahead is not None:
            end_date = start_date + timedelta(days=days_ahead)
        
        try:
            # Prepare arguments for the Swift script
            args = ["--events"]
            
            # Add date range
            args.extend([
                "--start-date", start_date.strftime("%Y-%m-%d"),
                "--end-date", end_date.strftime("%Y-%m-%d")
            ])
            
            # Add calendar filter if provided
            if calendar_names and len(calendar_names) > 0:
                # Currently, the Swift script only supports filtering by a single calendar
                # If multiple calendars are provided, we'll query each and combine the results
                all_events = []
                
                for calendar_name in calendar_names:
                    logger.info(f"Getting events for calendar: {calendar_name}")
                    calendar_args = args + ["--calendar", calendar_name]
                    
                    result = self._run_script(calendar_args)
                    
                    if not result or "error" in result:
                        error_msg = result.get("error", "Unknown error") if result else "No result from script"
                        logger.warning(f"Failed to get events for calendar {calendar_name}: {error_msg}")
                        continue
                    
                    events_data = result.get("events", [])
                    all_events.extend(events_data)
                
                logger.info(f"Retrieved {len(all_events)} events from {len(calendar_names)} calendars")
                return all_events
            else:
                # Get events from all calendars
                logger.info("Getting events from all calendars")
                result = self._run_script(args)
                
                if not result or "error" in result:
                    error_msg = result.get("error", "Unknown error") if result else "No result from script"
                    logger.error(f"Failed to get events: {error_msg}")
                    return []
                
                events_data = result.get("events", [])
                logger.info(f"Retrieved {len(events_data)} events from all calendars")
                return events_data
                
        except Exception as e:
            logger.error(f"Failed to get events using EventKit: {e}")
            return []
            
    def _run_script(self, args: List[str]) -> Optional[Dict]:
        """
        Run the Swift script with provided arguments.
        
        Args:
            args: List of arguments to pass to the script
            
        Returns:
            Optional[Dict]: Parsed JSON output from the script, or None if failed
        """
        try:
            cmd = [self.binary_path] + args
            
            # Execute the Swift script
            logger.debug(f"Running: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                logger.error(f"Swift script returned error code {result.returncode}: {error_msg}")
                return None
            
            # Parse JSON output
            try:
                output = json.loads(result.stdout)
                return output
            except json.JSONDecodeError:
                logger.error("Failed to parse JSON output from Swift script")
                logger.debug(f"Raw output: {result.stdout}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to run Swift script: {e}")
            return None


if __name__ == "__main__":
    # Simple test function when run directly
    logging.basicConfig(level=logging.DEBUG)
    calendar = EventKitCalendarAccess()
    print("Available calendars:")
    calendars = calendar.list_calendars()
    for cal in calendars:
        print(f" - {cal['title']} ({cal.get('type', '')})")
        
    print("\nEvents for next 7 days:")
    events = calendar.get_events(days_ahead=7)
    for event in events:
        print(f" - {event['title']} ({event['start_date']})")
        if event.get('location'):
            print(f"   Location: {event['location']}")
