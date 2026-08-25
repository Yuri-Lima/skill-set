# 213 · Transactions next-due stays stale after repayment

**Project:** acme/ledger  
**State:** open  
**Labels:** bug, web

## Done when

- After a repayment posts, the transactions list shows the new next-due
  date on that row (not the previous cycle).
- Empty / missing next-due is still rendered as an empty cell, not a
  leftover date from the last fetch.

## Notes

API computes `next_due` from the loan clock. The list on `/finances/transactions`
reads `row.nextDue` from the last payload. Users report the badge still
says `12 Aug` after they pay the August installment.
