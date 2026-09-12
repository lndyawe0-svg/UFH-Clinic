UFH CLINIC & HEALTHCARE TRIAGE SYSTEM
=====================================

This is a student-project upgrade of the working HealthcareTriageWebsite.
It uses Flask + SQLite so it runs locally without MySQL configuration.

WORKFLOW
--------
Patient registration/login -> digital triage -> health screening -> consultation appointment -> nurse review -> consultation -> treatment/dispensary record -> check-up/referral.

FEATURES
--------
- Patient, Nurse and Admin accounts
- Digital patient records
- Triage priority queue
- Consultation booking with service, nurse and time
- BP, glucose, temperature and HIV test recording
- Nurse consultation notes and treatment recommendation
- Treatment/dispensary records and refill dates
- Transfer of ongoing treatment from a local clinic
- Follow-up check-ups
- Referrals
- Admin statistics and activity logs

RUN
---
1. Open terminal in this folder.
2. python -m venv venv
3. venv\Scripts\activate
4. pip install -r requirements.txt
5. python app.py
6. Open http://127.0.0.1:5000

IMPORTANT
---------
This is a software engineering demonstration, not an official University of Fort Hare clinical system. Clinical values and HIV results are handled as demonstration data and require qualified clinical review in a real deployment.
