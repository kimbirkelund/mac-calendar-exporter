#!/usr/bin/swift

import Foundation
import EventKit

// Command line arguments
let args = CommandLine.arguments
var operation = "calendars"  // Default operation
var calendarName: String? = nil
var startDateStr: String? = nil
var endDateStr: String? = nil

// Parse arguments
var i = 1
while i < args.count {
    switch args[i] {
    case "--calendars":
        operation = "calendars"
    case "--events":
        operation = "events"
    case "--calendar":
        i += 1
        if i < args.count {
            calendarName = args[i]
        }
    case "--start-date":
        i += 1
        if i < args.count {
            startDateStr = args[i]
        }
    case "--end-date":
        i += 1
        if i < args.count {
            endDateStr = args[i]
        }
    default:
        break
    }
    i += 1
}

// Setup date formatter
let dateFormatter = DateFormatter()
dateFormatter.dateFormat = "yyyy-MM-dd"
dateFormatter.timeZone = TimeZone.current

// Parse dates
let startDate: Date
if let dateStr = startDateStr, let date = dateFormatter.date(from: dateStr) {
    startDate = date
} else {
    startDate = Date() // Today
}

let endDate: Date
if let dateStr = endDateStr, let date = dateFormatter.date(from: dateStr) {
    endDate = date
} else {
    // Default to 30 days ahead
    endDate = Calendar.current.date(byAdding: .day, value: 30, to: startDate)!
}

// Output date formatter (for event dates)
let outputDateFormatter = DateFormatter()
outputDateFormatter.dateFormat = "yyyy-MM-dd HH:mm:ss"
outputDateFormatter.timeZone = TimeZone.current

// EventKit store
let eventStore = EKEventStore()

// Group for waiting for async permission request
let group = DispatchGroup()
group.enter()

// Function to handle calendar access once granted
func handleCalendarAccess() {
    do {
        // Prepare output JSON
        var outputDict: [String: Any] = [:]
        
        switch operation {
        case "calendars":
            let calendars = eventStore.calendars(for: .event)
            var calendarList: [[String: Any]] = []
            
            for calendar in calendars {
                let calendarDict: [String: Any] = [
                    "title": calendar.title,
                    "id": calendar.calendarIdentifier,
                    "type": calendar.type.rawValue,
                    "source": calendar.source.title
                ]
                calendarList.append(calendarDict)
            }
            outputDict["calendars"] = calendarList
            
        case "events":
            var targetCalendars: [EKCalendar]?
            
            if let name = calendarName {
                // Filter calendars by name
                targetCalendars = eventStore.calendars(for: .event).filter { $0.title == name }
                if targetCalendars?.isEmpty ?? true {
                    print("Error: Calendar '\(name)' not found")
                    exit(1)
                }
            }
            
            let predicate = eventStore.predicateForEvents(withStart: startDate, end: endDate, calendars: targetCalendars)
            let events = eventStore.events(matching: predicate)
            
            var eventList: [[String: Any]] = []
            for event in events {
                var eventDict: [String: Any] = [
                    "event_id": event.eventIdentifier ?? UUID().uuidString,
                    "calendar_name": event.calendar.title,
                    "title": event.title ?? "(No Title)",
                    "start_date": outputDateFormatter.string(from: event.startDate),
                    "end_date": outputDateFormatter.string(from: event.endDate),
                    "all_day": event.isAllDay
                ]
                
                if let loc = event.location, !loc.isEmpty {
                    eventDict["location"] = loc
                }
                
                if let notes = event.notes, !notes.isEmpty {
                    eventDict["description"] = notes
                }
                
                if let url = event.url?.absoluteString {
                    eventDict["url"] = url
                }
                
                eventList.append(eventDict)
            }
            
            outputDict["events"] = eventList
            outputDict["start_date"] = outputDateFormatter.string(from: startDate)
            outputDict["end_date"] = outputDateFormatter.string(from: endDate)
            if let name = calendarName {
                outputDict["calendar_name"] = name
            }
        default:
            outputDict["error"] = "Unknown operation"
        }
        
        // Convert to JSON and print
        let jsonData = try JSONSerialization.data(withJSONObject: outputDict, options: .prettyPrinted)
        if let jsonString = String(data: jsonData, encoding: .utf8) {
            print(jsonString)
        }
    } catch {
        print("Error: \(error.localizedDescription)")
    }
    
    group.leave()
}

// Request access to calendar using the appropriate API based on macOS version
if #available(macOS 14.0, *) {
    eventStore.requestFullAccessToEvents { (granted, error) in
        if granted {
            handleCalendarAccess()
        } else {
            print("Error: Access denied or error: \(String(describing: error))")
            group.leave()
        }
    }
} else {
    eventStore.requestAccess(to: .event) { (granted, error) in
        if granted {
            handleCalendarAccess()
        } else {
            print("Error: Access denied or error: \(String(describing: error))")
            group.leave()
        }
    }
}

// Wait for the async operation to complete
group.wait()
