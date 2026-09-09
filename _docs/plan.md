# Chorum-murohc - Project Plan

> **Status:** Built. Every requirement below is implemented and driven end
> to end in a browser; `_docs/plan-verification.md` holds the evidence, and
> `README.md` says how to run it.

## Overview

Household chore management web app with a points economy, gamification, and creature evolution system.

## Implementation Track

- Django remains the required backend framework, with Python as the primary
  implementation language.
- The selected frontend, data, testing, and architectural choices are recorded
  in the [design document](design.md).
- The application runs as one container next to PostgreSQL, started with a
  single `docker compose` command on one small machine (`README.md`).
  Distributed operation across more than one machine remains a long-term
  possibility rather than a requirement.

## Users & Auth

- Admin-configurable user accounts (username/password)
- Two roles: **admin/parent** and **child**
- Admin creates users and assigns roles
- Default household: 2 adults, 2 children (configurable)

## Chore Pool

- Adults create and manage a pool of chores
- Each chore has a name and a fixed point value (set by adults)
- All chores are always available - no scheduling, no disappearing after claim
- Any child can pick any chore at any time
- Frequency policing is manual (adults approve or reject)

## Task Completion Flow

1. Child selects a chore from the pool and marks it as done
2. Child submits the completed chore for approval
3. Parent approves via one of two methods:
   - On the child's device: parent enters their 4+ digit PIN
   - On their own device: parent sees pending approval, enters their PIN
4. On approval, points are credited to the child
5. Children cannot approve tasks or create chores
6. Submitting a task for approval before completion is forbidden

## Points Economy

### Earning

- Points awarded per approved chore (flat rate per chore type)

### Interest

Approved in [issue #49](https://github.com/alexisdacquay/chorum-murohc/issues/49)
and stated exactly in `_docs/interest-policy.md`, which replaced this plan's
original monthly, daily-accruing, level-scaled draft before anything was
built.

- Unspent points earn 2% once a week, against the balance held when the
  accrual runs. No compounding within the week.
- Floored to whole points, and capped at 20 points from one accrual.
- A balance of zero or less earns nothing.
- No level bonus: every child earns the same rate.
- Intent, unchanged: incentivise saving over spending.

### Spending - Rewards

Approved in [issue #55](https://github.com/alexisdacquay/chorum-murohc/issues/55),
which replaced this plan's two fixed conversions with a catalogue the
household writes itself.

- Parents define the rewards: each one has a name and a point cost. Game
  time and pocket money are two rows a parent can add, not the only two
  possibilities.
- A child redeems a reward when their balance covers it, and the ledger is
  debited at redemption.
- A parent then fulfils the reward off-app, or cancels it and returns the
  points.

### Leveling Up

Approved in [issue #61](https://github.com/alexisdacquay/chorum-murohc/issues/61),
which replaced this plan's bought levels with earned ones, so that spending
points on a reward no longer costs a child their progress.

- A level is earned from lifetime points, never bought with them. Spending
  never demotes anyone.
- Ten levels, at 50, 150, 300, 500, 750, 1050, 1400, 1800, 2250 and 2750
  lifetime points.
- Points remain a single currency; there is no separate experience score.

## Creature System

### Selection

- Each child picks a creature line at signup

### Selection timing

- A child picks their line at first sign-in, after their account exists, so
  account creation never waits on the chooser
- The choice is kept: a creature cannot be swapped for another one later

### Creature Lines (7)

All seven are original renderings of public-domain mythological archetypes.
The project uses no third-party intellectual property; the lines this plan
originally named (Warhammer 40k Soldier, Warhammer Tyranid, Pikachu, Lego
Star Wars Stormtrooper, Playmobil Pirate) are dropped, and `_docs/creature-catalogue-policy.md`
records that decision.

1. Dragon
2. Golem
3. Griffin
4. Phoenix
5. Kraken
6. Treant
7. Sphinx

### Evolution Visual

- 4 forms per creature line (28 total), one per evolution stage
- Original flat SVG drawn for this repository and committed to it; no
  downloaded asset and no external image host
- Forms are reached at levels 1, 4, 7 and 10
- Early forms: small, muted, minimal detail
- Late forms: large, vivid, elaborate wings, crests and armour
- Each step shows a clear visual change from the previous
- Children can browse every form of their line; the ones still to come show
  as silhouettes with the level that reveals them

## Admin Features

- Create/delete users
- Assign roles (admin or child)
- Create/edit/delete chores and their point values
- Approve or reject completed chore submissions
- View all users' point balances and levels
