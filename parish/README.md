# Matuu Parish Church Website (Flask + MySQL)
1. **Create a fresh database** (schema changed): `DROP DATABASE IF EXISTS matuu_parish;` then `mysql -u root -p < schema.sql`
2. `pip install -r requirements.txt`
3. Set DB: `DB_URI=mysql+pymysql://USER:PASS@localhost/matuu_parish` (or edit app.py)
4. Optional email (reset passwords, replies, staff logins): set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM. Without it, emails are printed in the console.
5. `python app.py` -> http://127.0.0.1:5000 . Admin login: /admin/login  username `admin`, password `admin123` (change it under "My Password").
Staff: Admin > Staff > Add. A 6-digit temporary password is generated, shown in the Staff list, and emailed if an email is given. Username = staff phone number.
Sermon payments (PayHero): set the price on each sermon (0 = free). In `.env` fill PAYHERO_API_USERNAME, PAYHERO_API_PASSWORD, PAYHERO_CHANNEL_ID, PAYHERO_PROVIDER (m-pesa) and PAYHERO_CALLBACK_URL (https://your-domain/payhero/callback). Restart after editing `.env`.
The member gets the M-Pesa prompt on their phone; the page shows "Check your phone" and unlocks the sermon automatically. The Donate tab is manual (no PayHero).
Errors are never shown to visitors; they are written to logs/app.log. Members can change their password and add a cropped profile picture under Menu > My Profile & Password.
Admin profile: Admin panel > My Profile (change username, password, and add a face-cropped picture).
Password help: Admin > Users > key button creates a temporary password; members who used "Forgot password" appear under Admin > Password Resets (send manually via the WhatsApp button).
Insights: Admin > Insights & Tips shows where to improve and which members have not attended church.
Church admins: Admin > Users > Edit a member > Role "Church admin" + pick their Church. They log in at /admin/login and see only their church (members, attendance charts, tips, tithes & offerings).
Tithes: church admin records each Sunday; it is added to the system only when the parish admin presses "Arrived" under Admin > Church Remittances.
Notes: Admin (super) > Notes.
Church admin extras: Add Member (members without smartphones; username = phone, temp password shown once), reset passwords for own-church members, Announcements (message + PDF/Word, shown only to that church's members), Notices (private messages with the super admin, both directions, PDF/Word attachments).
Super admin: Notices tab to message one church or all churches.
Church ministries: church admins add their own church's leaders under Church Ministries; everyone sees them on the website (public). Super admin: Giving Reports (per church: month, half year, whole year or custom dates; confirmed money only; CSV download).
