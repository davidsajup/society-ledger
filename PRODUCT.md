# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
- **Residents** of a housing society, mostly on phones. Many are older and not technical. They check what they owe, see their statement, and open or print receipts.
- **Office-bearers** (president, secretary, treasurer), mostly on a laptop and sometimes on a phone. They record payments and expenses, see who is behind, manage flats and logins, and review the audit trail. Each office-bearer is also a resident who pays their own dues.
- A real society will use it. The treasurer currently tracks payment status in Excel sheets.

## Product Purpose
Society Ledger is a multi-tenant finance and management platform for housing societies. Each society has isolated data for flats, residents and money. It replaces the treasurer's spreadsheet with a ledger that cannot be quietly rewritten: dues are billed automatically each month, payments are appended and corrected only by reversal, and every money action is audited. Success is residents trusting their balance and a treasurer who can show where every rupee went.

It is also the author's learning project and proof of backend readiness. Backend correctness comes before UI breadth.

## Positioning
The books are tamper-evident and segregated by design: append-only ledger, derived balances, audit trail written atomically, and nobody can record a payment for the flat they live in. A spreadsheet cannot truthfully make those claims.

## Operating Context
- Society roles: president, secretary, treasurer, resident. One role per person. President and secretary manage flats, people and logins; president, secretary and treasurer record payments; only the treasurer records expenses.
- Logins are issued by the president or secretary (random one-time password, shown once, changed at first login). There is no self-sign-up and no email.
- Payments are made outside the app (cash or bank) and recorded by an office-bearer. There is no online payment processing.
- Money is in rupees, shown with Indian formatting. Receipts are printable.

## Capabilities and Constraints
- Frontend is limited to three areas: resident dashboard (dues, balance, statement, receipts), treasurer dashboard (collections vs outstanding, record payments and expenses, dues grid, activity), and the people/admin pages (flats, people, roles, logins).
- Stack: React, TypeScript, Vite, TanStack Query, Mantine; Django/DRF backend. Money is always handled as exact decimal strings, never floats.
- Phone-first: the bottom navigation holds at most five items.
- Out of scope for now: complaints, online payments, social features, automatic (scheduled) reminders. Real-user onboarding for a single society run locally and an on-demand reminder email button are in scope; public deployment is still open. AI features come only after the main build.

## Brand Commitments
Name: Society Ledger. Voice: plain, calm and trustworthy. No hype, no jargon, no jokes about money. Wording must make sense to a non-technical resident.

## Evidence on Hand
Only fake demo data (the seeded "Green Meadows" and "Sunrise Heights" societies). There are no real testimonials, customers or society branding to reference; do not invent any.

## Product Principles
- Trust before delight: a number on screen must be exactly right and explainable.
- Show people only what concerns them; hide actions they are not allowed to take, while the server stays the real control.
- Plain words and big, clear targets for older residents; never rely on colour alone.
- Fast and light on low-end phones and slow connections.
- Corrections are visible, not erased: reversals and receipts say what happened.

## Accessibility & Inclusion
- Many residents are older and non-technical: large tap targets, high contrast, plain wording, few steps per task.
- Low-end phones and slow connections: keep pages and assets light.
- Multiple languages were not requested; not a current requirement.
