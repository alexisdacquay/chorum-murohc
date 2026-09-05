# Chorum-murohc — Project Plan

> **Status:** Planning

## Overview

Household chore management web app with a points economy, gamification, and creature evolution system.

## Implementation Track

- Django remains the required backend framework, with Python as the primary
  implementation language.
- The selected frontend, data, testing, and architectural choices are recorded
  in the [design document](design.md).
- Development begins locally, with containerised and distributed operation
  treated as a long-term evolution rather than an immediate requirement.

## Users & Auth

- Admin-configurable user accounts (username/password)
- Two roles: **admin/parent** and **child**
- Admin creates users and assigns roles
- Default household: 2 adults, 2 children (configurable)

## Chore Pool

- Adults create and manage a pool of chores
- Each chore has a name and a fixed point value (set by adults)
- All chores are always available — no scheduling, no disappearing after claim
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

- Unspent points earn 20% monthly interest
- Interest accrues daily
- Each creature level grants +30% to the interest rate
- Example: level 10 = base 20% + 300% = 320% monthly interest
- Intent: strongly incentivise saving over spending

### Spending — Rewards

- 1 point = 1 minute of video game time
- 200 points = £5 pocket money
- No other reward types

### Spending — Leveling Up

- Leveling consumes points (single currency, no separate XP)
- Level 1 costs 500 points
- Level 2 costs 510 additional points
- Mild escalation per level
- Approximately 30–40 levels total

## Creature System

### Selection

- Each child picks a creature line at signup

### Creature Lines (7)

1. Warhammer 40k Soldier
2. Warhammer Tyranid
3. Golem
4. Dragon
5. Pikachu
6. Lego Star Wars Stormtrooper
7. Playmobil Pirate

### Evolution Visual

- ~35 AI-generated images per creature line (~245 total)
- Gradual, smooth progression between levels
- Early levels: small, dull colours, minimal detail
- Late levels: massive, vivid colours, elaborate armour/features
- Each step shows a clear but small visual change from the previous
- Users can browse all their creature's previous forms to compare

## Admin Features

- Create/delete users
- Assign roles (admin or child)
- Create/edit/delete chores and their point values
- Approve or reject completed chore submissions
- View all users' point balances and levels
