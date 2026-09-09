# Dependency Approvals

Ask before adding a direct dependency. Say the package, what it is for and the
version range, get the product owner's yes on the issue, then add a row below
and change the manifest. Transitive packages arrive through the lockfile and
need no row. A major-version change to a direct dependency needs a new row.
`_docs/design.md` records technical intent; it is not an installation approval.

## Approved

| Package(s) | For | Range | Issue |
| --- | --- | --- | --- |
| `pytest`, `pytest-django` | Backend test baseline | `pytest>=9.1.1,<10`, `pytest-django>=4.14,<5` | [#1](https://github.com/alexisdacquay/chorum-murohc/issues/1#issuecomment-5555010370) |
| `ruff` | One backend formatter and linter | `>=0.16.6,<0.17` | [#3](https://github.com/alexisdacquay/chorum-murohc/issues/3#issuecomment-5555495792) |
| `psycopg[binary]` | Django's PostgreSQL driver | `>=3.3.5,<3.4` | [#5](https://github.com/alexisdacquay/chorum-murohc/issues/5#issuecomment-5555796197) |
| `djangorestframework` | API dispatch, JSON, negotiation, errors | `>=3.18.1,<3.19` | [#10](https://github.com/alexisdacquay/chorum-murohc/issues/10#issuecomment-5576002924) |
| `react`, `react-dom` | Frontend runtime | `>=19.2.8,<20` | [#11](https://github.com/alexisdacquay/chorum-murohc/issues/11#issuecomment-5560573600) |
| `typescript`, `vite`, `@vitejs/plugin-react`, `vitest`, `jsdom`, `@testing-library/react`, `@testing-library/dom`, `@types/node`, `@types/react`, `@types/react-dom` | Frontend build and test toolchain | as locked in `frontend/package.json` | [#11](https://github.com/alexisdacquay/chorum-murohc/issues/11#issuecomment-5560573600) |
| `tailwindcss`, `@tailwindcss/vite` | Tailwind v4 tokens and utilities, no PostCSS adapter | `>=4.3.3,<4.4` | [#12](https://github.com/alexisdacquay/chorum-murohc/issues/12#issuecomment-5576277632) |
| `@radix-ui/react-dialog`, `@radix-ui/react-slot`, `class-variance-authority`, `clsx`, `tailwind-merge` | Accessible dialog, slot composition, variant and class contracts | `>=1.1.23,<1.2`, `>=1.3.3,<1.4`, `>=0.7.1,<0.8`, `>=2.1.1,<3`, `>=3.6,<4` | [#13](https://github.com/alexisdacquay/chorum-murohc/issues/13#issuecomment-5576815474) |
| `@tanstack/react-query` | Query client, request state, retry | `>=5.102.8,<6` | [#16](https://github.com/alexisdacquay/chorum-murohc/issues/16#issuecomment-5581263288) |

Deliberately excluded so far: the shadcn CLI and the aggregate `radix-ui`
package, lucide, animation and motion libraries, the Tailwind PostCSS adapter,
form and data libraries beyond the ones above, MSW, and Axios, ky or SWR.

## Not yet asked for

React Hook Form and Zod (forms) and Motion (only if CSS is demonstrably
insufficient). Each still needs a proposal and an approval before it is
installed.

Playwright was on this list for the end-to-end journeys and is no longer
needed. The browser harness in `browser_journeys/` drives the real product in
headless Chrome using the standard library and the browser alone, on the same
pinned-container shape as the layout probe, so no package was added. See
`browser_journeys/README.md`.
