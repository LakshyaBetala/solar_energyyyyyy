# Recording: "Apply for Solar Rooftop" on the live consumer login

Recorded 13 Nov 2026 in the built-in browser, signed in by the owner (OTP and CAPTCHA typed by them).
Customer data was Solara's synthetic customer SS-2045 (Vaishali Pawar). Nothing was submitted: the
dialog was cancelled at the end and Next was never pressed.

| # | Step | What the page did | Timing |
|---|---|---|---|
| 1 | Home → click the **Apply for Solar Rooftop** card | opens the "Start a new Application" dialog | under 1 s |
| 2 | Click **State**, pick `MAHARASHTRA` | PrimeNG single-select, 36 entries, has a search box | 0.4 s |
| 3 | Click **District**, pick `NASHIK` | locked until State is chosen; then 36 entries, mixed case (`Ahilyanagar`, `BEED`, `Bhandara`) | wait about 9 s in the first manual run, 1.8 s scripted |
| 4 | Click **Electricity Distribution Company / Utility**, pick the company | with a district chosen: 1 option; with none: 37 options. Shown without the final full stop: `...Distribution Co. Ltd` | 0.4 s |
| 5 | Type the **Consumer Account Number (CA No.)** | the Fetch Details button becomes enabled | instant |
| 6 | Click **Fetch Details** | spinner, then either the customer's details or **"Data not Available"** | about 3 s |
| 7 | **Next** | stays disabled until Fetch Details returns data | not pressed |

## What this told us
- A made-up CA number returns "Data not Available" and Next stays disabled. The co-pilot must tell the
  owner to check the CA number rather than carry on.
- Option text differs from Solara's wording (trailing full stop, upper case), so matching is by the
  normalised text, accepted only when exactly one option matches. Otherwise the choices go to the owner.
- Solara had no district for these customers. That is the fallback case: the district list is shown
  in the popup at the bottom.

## Replay
`tools/portal/apply_new_application.js` runs steps 1 to 6 from the values in `window.SOLARA_VALUES`
and returns what the owner still has to do. It was replayed live from the home page: State and the
company filled by themselves, and the missing district was reported.
