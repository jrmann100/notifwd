# notifwd
Notification forwarder for macOS by Jordan Mann
## Purpose: Why did you make this?
I'm glad you asked! Consider these four facts:

 1. I have a Pebble smartwatch that receives notifications from my phone.
 2. At the time of writing, I don't use my iPhone at all, besides to sync with my Pebble. It's old and slow, and I have no dependency on it.
 3. I receive all of my notifications (primarily from iMessages) on my Mac, then.
 4. The app that was used to send (and forward) macOS app notifications, Growl, was replaced by Apple's Notification Center.
 
 I want my macOS notifications to show up on my watch. So I made **notifwd**, which forwards them to an app on my iPhone that the Pebble can pick up.
  
## Prerequisites: What do I need to install notifwd?
You're very fortunate; you only need this script, a macOS computer, and an iPhone app called Prowl.
Prowl is $2.99 at the time of writing this, but I promise it's worth it. Using their API (I cannot vouch for its security), you'll be able to send push notifications to your iPhone, even via email.

You don't need Prowl to use this script. If you want to log notifications or forward them somewhere else, just replace the sending component.

Oh, and this script was written in Python 3.7. You need Python 3. That's important.

## Functionality: What does notifwd do?
Notifwd periodically checks macOS' Notification Center database for newly-recorded notifications. (Notifications are recorded after their popups disappear). It parses those notifications, additionally determining the application's name and how long ago the notification was sent, and sends them to the Prowl API. 

## Installation and Configuration: How do I set up notifwd?
I'm making this non-developer-friendly. At some point I may bundle the application and add a GUI.

Open the macOS Terminal app, located at `/Applications/Utilities/` in the Finder.
`cd ~/Desktop` or wherever you want to download the script to.
`git clone https://github.com/jrmann100/notifwd.git` to download this repository and `cd notifwd`
Run `./notifwd.py` in the cloned repository.
Create your Prowl API key by going to [Prowl's API Settings page](https://www.prowlapp.com/api_settings.php).
Copy the key, and make it visible to the script by running `export PROWL_API_KEY=[your key here]`
Alternatively pass the key to the script by running `./notifwd.py --api-key [your key here]`

Run the script with `--silent` to disable verbose outputs and that fancy splash screen.
Run the script with `--frequency [seconds]` to specify how often the script should check for new notifications.
Run the script with `--version` to get its version. You can always `git pull` for the newest version.
## Contributing: I love notifwd, but I have a problem with it!
I'm so sorry, and I hope I can help. Please submit any issues or suggestions you have for this script on GitHub.

I acknowledge my code is not perfect, but it suits my needs. If you think your code is more pretty or efficient, please let me know.
