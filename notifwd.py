#!/usr/bin/env python3
# Notiforward for macOS
# Copyright Jordan Mann
# Last Updated 28 April 2020

__version__ = "0.2"

import subprocess, sqlite3
from datetime import datetime
from xml.etree.ElementTree import fromstring as parseXML
import sched, time
import requests
from sys import argv, maxsize, stdout
import argparse, os

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
        parser = argparse.ArgumentParser(
            description="notifwd v%s - macOS notification forwarder" % __version__,
            prog="notifwd")
        parser.add_argument("--api-key", "-k",
                            help="Prowl API key",
                            default=os.environ.get("PROWL_API_KEY"))
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

# Need error handling for freq, and to incorporate silent.

        print("""
  _   _       _   _ _____             _ 
 | \ | | ___ | |_(_)  ___|_      ____| |
 |  \| |/ _ \| __| | |_  \ \ /\ / / _` |
 | |\  | (_) | |_| |  _|  \ V  V / (_| |
 |_| \_|\___/ \__|_|_|     \_/\_/ \__,_|

notifwd by Jordan Mann. Starting up... """, end="")
        Notification.API_KEY = args.api_key
        Notification.FREQ = args.frequency
        # Get the system temp directory macOS is caching to.
        tmp_path = subprocess.run(["getconf", "DARWIN_USER_DIR"], stdout=subprocess.PIPE).stdout
        # Locate the database; start SQLite.
        db_path = tmp_path.decode("utf-8").rstrip() + "com.apple.NotificationCenter/db2/db"
        Notification.connection = sqlite3.connect(db_path)
        Notification.cursor = Notification.connection.cursor()
        # Initialize a list of the last few notifications.
        Notification.recents = list()
        # Set the most recent notification date to the time of the last-displayed notification.
        Notification.last_sent_date = Notification.update_recents()[-1].date
        print("done.")

    @staticmethod
    def main(argv):
        Notification.setup(argv)
        s = sched.scheduler(time.time, time.sleep)
        def check_recents(s):
            print(".", end="")
            for notification in Notification.update_recents():
                # If the notification is new, send it.
                if notification.date > Notification.last_sent_date:
                    notification.send()
                    Notification.last_sent_date = notification.date
            stdout.flush() # Need this when running in thread.
            # Schedule to run periodically.
            s.enter(Notification.FREQ, 1, check_recents, (s,))
        # Schedule to run on start.
        s.enter(0, 1, check_recents, (s,))
        try:
            print("Starting scheduler. Update frequency is", Notification.FREQ, "seconds and checking last", 5, "notifications...", end="")
            stdout.flush() # Need this when running in thread.
            s.run()
        except KeyboardInterrupt:
            print("\nQuitting...")
            Notification.close_db()
            raise SystemExit # Equivalent to quit() or exit()
        except Exception as e:
            raise(e)

    # Create current Cocoa Core Data Timestamp (seconds since Jan 1 2001)
    # and subtract notification date to find how many seconds ago it was.
    # https://www.epochconverter.com/coredata
    @staticmethod
    def coredata_now():
        return (datetime.utcnow() - datetime(2001,1,1)).total_seconds()

    @staticmethod
    def time_ago(coredatatimestamp):
        return Notification.coredata_now() - coredatatimestamp

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
        # Includes both subtitle and body. See update_recents().
        self.subtitle = ""
        self.ago = 0
        self.date = 0
        self.xml = ""
        # Sort by least recent, so we can scan through to see which we have not seen yet.
# This needs to be looked at. We should collect all new, then break scanning. I can't puzzle my way through this right now, it's late.
        Notification.recents.insert(0, self)

    # Display notification info with non-ASCII characters removed, for logging.
    def __str__(self):
        return "There was a notification " + str(int(self.ago/60)) + " minutes ago from " + self.app + ": " + \
            self.title.strip().encode('ascii', 'ignore').decode('ascii') + \
            " (" + self.subtitle.strip().encode('ascii', 'ignore').decode('ascii') + ")"

    # Collect recent notifications.
    @staticmethod
    def update_recents():
        Notification.recents.clear()
        # Find most recent notifications.
        Notification.cursor.execute("SELECT data FROM (SELECT * FROM record ORDER BY delivered_date DESC LIMIT " +
                                    str(5) + ")")
        results = Notification.cursor.fetchall()
        # Iterate over returned SQL data.
        for result in results:
            # Create new blank notification, which is added to the recents list.
            this = Notification()
            # Parse raw database data, which is an Apple plist, into XML. Then parse the XML.
            xml = subprocess.run(["plutil", "-convert", "xml1", "-", "-o", "-"],
                                 check=True, input=result[0], stdout=subprocess.PIPE).stdout
            this.xml = xml.decode('utf-8')
            # Iterate through nested dictionaries in the notification data to find the values we need.
            for [key, value] in Notification.iterate_dict(parseXML(xml)[0]):
                if key.text == "app":
                    this.identifier = value.text
                    this.app = Notification.lookup_display_name(this.identifier)
                elif key.text == "date":
                    this.date = float(value.text)
                    this.ago = Notification.time_ago(float(value.text))
                elif key.text == "req":
                    for [subkey, subvalue] in Notification.iterate_dict(value):
                        if subkey.text == "titl" and subvalue.text != None:
                            this.title = subvalue.text
                        # Merge subtitle and body - yes, notifications have three lines.
                        if (subkey.text == "subt" or subkey.text == "body") and subvalue.text != None:
                            this.subtitle += subvalue.text
        # This lets you iterate over the new notifications where you call it.
        return Notification.recents

    # Send a notification to the Prowl API.
    def send(self):
        print("\nSending new notification!", self)
        r = requests.post("https://api.prowlapp.com/publicapi/add",
                          data={"apikey": Notification.API_KEY, "application": self.app,
                                "event": self.title, "description": self.subtitle})
        
        if r.status_code != 200:
            print("Received unexpected status code", r.status_code, r.reason, "response:\n", r.text)
        

    # This needs to be called somewhere (probably)!     
    def close_db():
        Notification.connection.close()

if __name__ == "__main__":
    Notification.main(argv)
