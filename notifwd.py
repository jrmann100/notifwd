#!/usr/bin/env python3
# Notiforward for macOS
# Copyright Jordan Mann
# Last Updated 28 April 2020

__version__ = "0.3"

import subprocess, sqlite3
from datetime import datetime
from xml.etree.ElementTree import fromstring as parseXML
import sched, time
import requests
from sys import argv, maxsize, stdout
import argparse
from os import environ

# I have been writing a lot of Java and am probably not supposed to
# put everything into one class like this.
class Notification:
    
    @staticmethod
    def usage():
        print("""
notifwd
usage: notifwd [-h] [-s] [--api-key PROWL_API_KEY] [--frequency FREQ]

""")
    @staticmethod
    def setup(argv):
        # Parse the command-line arguments.
        parser = argparse.ArgumentParser(
            description="notifwd v%s - macOS notification forwarder" % __version__,
            prog="notifwd")
        parser.add_argument("--api-key", "-k",
                            help="Prowl API key",
                            default=environ.get("PROWL_API_KEY"))
        parser.add_argument("--frequency", "-f", type=int,
                            help="Frequency, in seconds, to check for new notifications.",
                            default=60)
        parser.add_argument("--version", action="store_true",
                            help="Get program version")
        parser.add_argument("--silent", "-s", action="store_true")
        args = parser.parse_args()
        if args.version:
            print("notifwd v%s" % __version__)
            raise SystemExit()
        if args.api_key is None:
            parser.error("no API key specified. Is $PROWL_API_KEY defined?")
        if args.frequency <= 0:
            parser.error("frequency must be a positive integer.")
        # Store command-line arguments in static fields.
        Notification.API_KEY = args.api_key
        Notification.FREQ = args.frequency
        Notification.SILENT = args.silent
        if not Notification.SILENT: print("""
  _   _       _   _ _____             _ 
 | \ | | ___ | |_(_)  ___|_      ____| |
 |  \| |/ _ \| __| | |_  \ \ /\ / / _` |
 | |\  | (_) | |_| |  _|  \ V  V / (_| |
 |_| \_|\___/ \__|_|_|     \_/\_/ \__,_|

notifwd by Jordan Mann. Starting up... """, end="")
        # Get the system temp directory macOS is caching to.
        tmp_path = subprocess.run(["getconf", "DARWIN_USER_DIR"], stdout=subprocess.PIPE).stdout
        # Locate the database; start SQLite.
        db_path = tmp_path.decode("utf-8").rstrip() + "com.apple.NotificationCenter/db2/db"
        Notification.connection = sqlite3.connect(db_path)
        Notification.cursor = Notification.connection.cursor()
        # Set the most recent notification ID to the ID of the last-displayed notification.
        Notification.last_id = Notification.get_notification_data(0)[0]
        if not Notification.SILENT: print("done.")

    @staticmethod
    def main(argv):
        Notification.setup(argv)
        s = sched.scheduler(time.time, time.sleep)
        def scheduled_update(s):
            if not Notification.SILENT: print(".", end="")
            stdout.flush() # Need this when running in thread because output is buffered. Not sure exactly why.
            Notification.check()
            # Schedule to run periodically.
            s.enter(Notification.FREQ, 1, scheduled_update, (s,))
        # Schedule to run on start.
        s.enter(0, 1, scheduled_update, (s,))
        try:
            print("Starting scheduler. Update frequency is %d second%s." % (Notification.FREQ, ("s" if Notification.FREQ != 1 else "")), end="")
            stdout.flush() # See note above.
            s.run()
        except KeyboardInterrupt:
            print("\nQuitting...")
            Notification.connection.close()
            raise SystemExit # Equivalent to quit() or exit()
        except Exception as e:
            raise(e)

    # Create current Cocoa Core Data Timestamp (seconds since Jan 1 2001)
    # and subtract notification date to find how many seconds ago it was.
    # https://www.epochconverter.com/coredata
    @staticmethod
    def coredata_now():
        return (datetime.utcnow() - datetime(2001,1,1)).total_seconds()

    # Fetch data for a specific notification from the database.
    @staticmethod
    def get_notification_data(n):
        #return Notification.cursor.execute("SELECT *, NTH_VALUE(rec_id,%d) OVER (ORDER BY rec_id DESC) FROM record LIMIT 1" % (n + 1)).fetchone()
        # I know there is a better way to do this, but I've spent an hour with my limited SQLite knowledge and it isn't enough.
        return Notification.cursor.execute("SELECT * FROM (SELECT * FROM record ORDER BY rec_id DESC LIMIT %d) ORDER BY rec_id LIMIT 1" % (n + 1)).fetchone()
    
    # Get the <key>, <value> pairs of an XML "dictionary".
    @staticmethod
    def iterate_dict(parsed_dict):
        pairs = list()
        for i in range(0, int(len(parsed_dict) / 2)):
            pair = [parsed_dict[i * 2], parsed_dict[i * 2 + 1]]
            pairs.append(pair)
        return pairs
    
    # Get an application name like "Messages" from an identifier like "com.apple.Messages"
    # that comes with the notification.
    @staticmethod
    def lookup_display_name(identifier):
        return subprocess.run(["mdfind", "kMDItemCFBundleIdentifier", "=",
                               identifier.strip(), "-attr", "kMDItemDisplayName"],
                              stdout=subprocess.PIPE).stdout.decode("utf-8").split(" = ")[-1].strip()

    # Inititialize nonstatic Notification attributes.
    def __init__(self):
        self.identifier = ""
        self.app = ""
        self.title = ""
        # Includes both subtitle and body. See check().
        self.subtitle = ""
        self.ago = 0
        self.date = 0
        self.xml = ""

    # Display notification info with non-ASCII characters removed, for logging.
    def __str__(self):
        return ("There was a notification %d minutes ago from %s: %s (%s...)" % (
            (int(self.ago/60)), self.app, self.title.strip().encode('ascii', 'ignore').decode('ascii'),
            self.subtitle.strip().encode('ascii', 'ignore').decode('ascii')[:15]))

    # Collect recent notifications.
    @staticmethod
    def check():
# I have seen this new method, on one occasion, run back through hundreds of
# previous notifications. I have not fully identified why yet.
        n = 0
        sql_data = Notification.get_notification_data(n)
        newest_id = sql_data[0]
        while sql_data[0] != Notification.last_id:
            Notification.send(Notification.parse_notification(sql_data[3]))
            n += 1
            sql_data = Notification.get_notification_data(n)
        Notification.last_id = newest_id

    # Create a notification from raw plist data. The returned notification can then be sent.
    @staticmethod
    def parse_notification(raw_plist):
        # Create a notification from raw plist data. This can then be sent.
        this = Notification()
        # Parse raw database data, which is an Apple plist, into XML. Then parse the XML.
        xml = subprocess.run(["plutil", "-convert", "xml1", "-", "-o", "-"],
                             check=True, input=raw_plist, stdout=subprocess.PIPE).stdout
        this.xml = xml.decode('utf-8')
        # Iterate through nested dictionaries in the notification data to find the values we need.
        for [key, value] in Notification.iterate_dict(parseXML(xml)[0]):
            if key.text == "app":
                this.identifier = value.text
                this.app = Notification.lookup_display_name(this.identifier)
            elif key.text == "date":
                this.date = float(value.text)
                this.ago = Notification.coredata_now() - float(value.text)
            elif key.text == "req":
                for [subkey, subvalue] in Notification.iterate_dict(value):
                    if subkey.text == "titl" and subvalue.text != None:
                        this.title = subvalue.text
                    # Merge subtitle and body - yes, notifications have three lines.
                    if (subkey.text == "subt" or subkey.text == "body") and subvalue.text != None:
                        this.subtitle += subvalue.text
        return this

    # Send a notification to the Prowl API.
    def send(self):
        if not Notification.SILENT: print("\nSending new notification!", self)
        r = requests.post("https://api.prowlapp.com/publicapi/add",
                          data={"apikey": Notification.API_KEY, "application": self.app,
                                "event": self.title, "description": self.subtitle})
        
        if r.status_code != 200:
            print("Received unexpected status code", r.status_code, r.reason, "response:\n", r.text)

if __name__ == "__main__":
    Notification.main(argv)
