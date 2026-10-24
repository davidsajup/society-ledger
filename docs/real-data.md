# Setting up a real society

How to go from an empty database to a real society with its flats, people and logins. Follow the steps in order: the order is part of the safety.

> **Not ready for residents over the internet yet.** This app has no HTTPS or production server configuration (see [PLAN.md](../PLAN.md), milestone M5). Until that is done, run it on your own computer only. Do not give residents a link.

## Who does what

| Person | Does |
|---|---|
| **Super admin** (you, the platform operator) | Creates the society and its first president's login. Cannot see any money. |
| **President** | Logs in, chooses a password, uploads the sheet of flats and people, hands out the login slips. Then runs the society. |
| Secretary, treasurer, residents | Log in with the slips. The president can add or change them later from the People page. |

The super admin is a Django superuser with no membership in any society. Every society page answers 404 to them, so they cannot read ledgers, balances, expenses or the audit log. This is deliberate and tested (`apps/societies/tests/test_cross_tenant.py`).

## 0. Before you start

- **Take a backup.** The ledger is append-only: a wrong import cannot be deleted, only corrected. Dump the database first and keep the file out of git (`backups/` is ignored):
  ```bash
  set -a && . ./.env && set +a
  pg_dump "$DATABASE_URL" -Fc -f backups/society-ledger-$(date +%Y%m%d).dump
  ```
  `pg_dump` comes with the PostgreSQL client tools; if you do not have them, use the backup in the Supabase dashboard instead. This reads the connection string from `.env` without printing it. Never paste it, or any password, into a chat or a commit.
- **Keep `DEMO_MODE` unset and `DJANGO_DEBUG` false** in the environment you run against the real database. Demo mode lets anyone in without a password.
- **Real files stay out of git.** Put your sheet in a folder named `data/` (ignored by git).

## 1. Prepare the database

```bash
.venv/Scripts/python.exe manage.py migrate --plan   # see what will run
.venv/Scripts/python.exe manage.py migrate
```

## 2. Create your super admin

```bash
.venv/Scripts/python.exe manage.py createsuperuser
```

It asks for a username, an email (optional) and a password, in your own terminal. Choose a long password you do not use elsewhere.

## 3. Start the app and onboard the society

Run the API and the UI as in the README, then open the UI and log in with the super admin. You land on **Societies**.

**New society** asks for:

| Field | Notes |
|---|---|
| Society name | As residents know it. |
| Short name | Lower-case letters, numbers and dashes. Used in usernames (`ravi.a-101@green-meadows`). Cannot be changed later. |
| President's full name | They get the first login. |
| Billed every | 3 months (quarterly) or 1 month. A starting value: the president can change it on **People → Billing** until the first billing run. |
| Automatic billing starts on | The first day of a cycle, today or later. For quarterly billing: 1 January, 1 April, 1 July or 1 October. Nothing is billed before this date, so you can set up flats first. The president can move it, until the first billing run. |

The app shows the president's username and a one-time temporary password **once**. Copy them and give them to the president privately. If they are lost, use **New password** on that society's card.

## 4. The president logs in

They sign in with the temporary password, are asked to choose their own, and then land on the Overview. The society has no flats yet.

## 5. Prepare the sheet

One row per person. Save from Excel as **CSV UTF-8** or keep it as `.xlsx`.

| Column | Required | Notes |
|---|---|---|
| Flat | yes | Flat number or label, at most 20 characters (`A-101`). |
| Name | yes | The person's full name. |
| Phone | no | 7 to 15 digits; spaces and dashes are fine. |
| Email | no | Stored, not used yet (the app sends no email). |
| Maintenance | yes | The amount for **one billing cycle** for the whole flat (for a quarterly society, the amount for the quarter). Digits only, `4500` or `4500.50`. |
| Role | no | `resident` by default. Use `treasurer`, `secretary` or `president` for office-bearers who live in a flat. |

- If two people share a flat, give each their own row with the same flat and the same amount.
- Flats that already exist are **not changed**: an existing flat label is an error. Edit those on the Flats page.
- Limits: 1 MB, 300 rows, first sheet only. Excel formulas are not calculated: paste values, not formulas.
- The template download on the Import tab shows the headings.

## 6. Import

**People → Import**:

1. Choose the file and **Check the file**. Nothing is created yet.
2. Fix every problem in the list (each names its row and column) in your sheet and upload again. **Create** stays disabled until there are none.
3. **Create N flats and M logins.** It is all-or-nothing: if anything is wrong, nothing is created.
4. **Print the slips** and/or **download the file**. The passwords are shown only now; the server keeps only hashes. Hand each slip to its owner privately.
5. **I have saved them** (you are asked once more, because it cannot be undone).

Anyone who loses their slip gets a new password from **People → New password**.

## 7. First billing

On or after the billing start date the daily job charges every flat once for the cycle. The job needs Redis and Celery beat. If you are not running them, bill by hand once:

```bash
.venv/Scripts/python.exe manage.py run_billing
```

It bills each society's current cycle and skips cycles already billed, so it is safe to run twice. It refuses, with a message, to bill any cycle before the society's billing start date, so running it early cannot create charges. Check the **Dues** page.

Payments are recorded by the president, secretary or treasurer (never for the flat they live in). A flat may pay its quarter in **any number of installments**; it cannot pay more than it owes, and cannot pay in advance.

### Changing the schedule

The president opens **People → Billing** to change how often the society is billed and when billing starts. The secretary and treasurer can read it (the treasurer reaches it from the link on the Dues page). It can be changed only until the first billing run exists; after that it is fixed. Changing the cycle asks the president to confirm that every flat's amount has been checked, because each amount is for one cycle.

## 8. Check it against your Excel

Compare the Overview totals (billed, collected, outstanding) with your sheet for the first cycle before relying on it.

## If something goes wrong

| Problem | What to do |
|---|---|
| Wrong amount on a flat, **before** billing | Edit the flat on the Flats page. |
| Wrong amount, **after** billing | The ledger cannot be edited. Reverse the charge (only possible if nothing was paid against it) and correct the flat. |
| Wrong role or flat for a person | People → Change role. |
| A resident lost their password | People → New password. |
| The import was wrong and nothing has been billed | Restore the backup, or leave the society and onboard a fresh one. A flat or login cannot be deleted. |

## What this does not do yet

Paying in advance (credit), due dates and late fees, changing a society's billing cycle later, editing a person's phone or email after import, emailing logins, and deployment with HTTPS. See [PLAN.md](../PLAN.md).
