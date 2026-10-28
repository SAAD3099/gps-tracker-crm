CONCEPT TRACKING CRM - DESKTOP PROJECT
======================================

WHAT'S INCLUDED
- Navy-blue and white professional interface
- Light mode and dark mode (theme choice is remembered on this PC)
- Login and logout
- Dashboard with customer, vehicle, subscription and collection totals
- Customer directory with search (name, phone, CNIC, city or customer code)
- Customer create and edit forms
- Vehicle create and edit forms, including tracker IMEI, SIM, engine and chassis details
- Service subscriptions and renewal information
- Payment records and collection history
- Customer/vehicle document uploads (PDF/JPG/PNG/WEBP, max 10 MB)
- Editable service plans
- Tracker inventory by model: purchase price, sale price, units received, units installed, units remaining and stock value
- Purchase / stock-in ledger with date, reference and supplier notes
- Installation ledger with optional links to existing customers and vehicles; available stock is checked before a stock-out
- Stock adjustment with mandatory reason and non-negative stock protection
- First-run account setup to create your own username and password, plus later credential changes under Account Settings
- Reports for monthly collections, vehicle types and overdue subscriptions
- Windows desktop shortcut and application icon
- Local SQLite database

FIRST-TIME SETUP (WINDOWS)
1. Install Python 3.10 or newer from python.org if it is not installed.
2. Extract this entire folder to a normal writable location, e.g. Documents\ConceptTrackingCRM.
3. Double-click INSTALL_CRM.bat (or setup.bat) and let it finish. Internet may be needed to install Flask and pywebview the first time.
4. The installer creates a "Concept Tracking CRM" shortcut with the supplied navy-blue app icon on your Windows Desktop.
5. Open the desktop icon. On the first launch, a setup screen asks you to create your own username and password. There is no shared default password.
6. To change your credentials later, open Account Settings from the left menu.

SECURITY
Passwords are stored as salted password hashes in the local database. Keep your Windows login protected and back up sensitive customer documents carefully. This project is designed for local use on this computer, not public internet hosting.

DATA LOCATION & BACKUPS
- Customer, service, login and inventory database: data\concept_tracking.db
- Uploaded customer documents: uploads\
- Back up both items regularly. Do not delete the data folder while the app is in use.
- The original uploaded source included app.py and .gitignore, but no existing database or HTML templates. This package creates its own data folder and new database when first run. To carry over records from an earlier copy of the project, close both versions and copy that earlier data\concept_tracking.db into this package's data folder. Copy the matching uploads folder too if you need existing uploaded files.

NOTES
- The desktop window uses pywebview. If Windows WebView2 is unavailable, the launcher falls back to your default browser.
- The app binds only to 127.0.0.1 (this computer); it is not exposed on the local network.
- Uploaded ID documents are sensitive. Limit access to this PC and backups.
