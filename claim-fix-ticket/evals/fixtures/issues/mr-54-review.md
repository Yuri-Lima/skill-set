# !54 review comments (no issue IID)

1. `/invoices` empty state hides the **New invoice** button. New tenants
   cannot create the first invoice.
2. Invoice **#8821** is overdue and has no overdue badge on the row.
3. `.gitlab-ci.yml` migrate job does not mention Alembic revision `004`.
   Lockfile / CI only.

Please fix all three on this MR.
