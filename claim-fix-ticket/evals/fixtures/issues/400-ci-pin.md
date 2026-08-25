# 400 · CI migrate job pin

**State:** open

The migrate job in `.gitlab-ci.yml` still installs `alembic==1.13.0` and
does not run revision `004`. No UI. Lockfile / pipeline yaml only.

## Done when

- The job installs the repo’s Alembic and upgrades through `004`.
