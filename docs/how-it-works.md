# How the RSC tool works (plain English)

Example names and addresses in this repo are made up.

## The idea in one sentence
Pops's computer reads his email, spots receipts, payments and new customers, and puts each one in a **To Review** pile. He taps a green button to approve. That's it.

## The screens

1. **Home** ([home.png](home.png)): "3 to review", his open jobs with money paid / still owed / profit, and payments he's waiting on.
2. **To Review**: one card per email. The app fills in the vendor, amount and which job it belongs to. He fixes anything wrong, then taps **Add expense**, **Mark paid** or **Start estimate**. **Skip** throws it away.
3. **Jobs** ([jobs.png](jobs.png)) and a **job page** ([job.png](job.png)): contract total, payment schedule (1002-SMI-1, -2...), expenses on that job. Payment IDs double as QuickBooks invoice numbers.
4. **Expenses** ([expenses.png](expenses.png)): every cost goes to a job number or an RSC code. **RSC Codes** ([codes.png](codes.png)) lists the business-cost codes.
5. **Room model**: type wall sizes, windows and doors; get a dimensioned plan, a spinnable 3D view, and text to paste into ChatGPT for a pretty picture.

## What happens behind the scenes
Every 30 minutes: Gmail (read-only) -> keyword filter drops junk -> the AI model on his Mac reads what's left -> plain rules pick the job (a "1002-SMI" on the receipt, or the address, or the client name) -> a card appears in To Review.

## What you do to try it
Nothing runs on your laptop yet. The screenshots came from a copy running here with fake emails. To try it for real, say yes to the "install on your Mac" card in this thread.
