---
name: Solara
description: The installer's back office, from the customer's documents to the agreement uploaded on PM Surya Ghar.
colors:
  teal-dark: "#35D0BA"
  teal-light: "#067F70"
  amber-dark: "#F2A63B"
  amber-light: "#AE6B06"
  warn-dark: "#FBBF24"
  warn-light: "#9A6207"
  ok-dark: "#4ADE80"
  ok-light: "#17803D"
  bad-dark: "#F8716A"
  bad-light: "#C32F26"
  info-dark: "#6AA8FA"
  info-light: "#1D5FBF"
  bg-dark: "#0C0E11"
  panel-dark: "#12151A"
  panel-2-dark: "#171B21"
  line-dark: "#272D36"
  fg-dark: "#E7EEF4"
  fg-dim-dark: "#93A2B2"
  bg-light: "#EEF1F4"
  panel-light: "#FFFFFF"
  panel-2-light: "#F6F8FA"
  line-light: "#D2DAE2"
  fg-light: "#111820"
  fg-dim-light: "#53646F"
typography:
  display:
    fontFamily: "Saira Condensed, Archivo, system-ui, sans-serif"
    fontSize: "28px"
    fontWeight: 600
    lineHeight: 1.1
  title:
    fontFamily: "Archivo, Helvetica Neue, system-ui, sans-serif"
    fontSize: "16.5px"
    fontWeight: 650
    lineHeight: 1.3
  body:
    fontFamily: "Archivo, Helvetica Neue, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "Archivo, Helvetica Neue, system-ui, sans-serif"
    fontSize: "13.5px"
    fontWeight: 600
    lineHeight: 1.4
  hint:
    fontFamily: "Archivo, Helvetica Neue, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.45
  mono:
    fontFamily: "JetBrains Mono, ui-monospace, monospace"
    fontSize: "12.5px"
    fontWeight: 400
rounded:
  sm: "3px"
  md: "6px"
  pill: "999px"
spacing:
  xs: "6px"
  sm: "12px"
  md: "18px"
  lg: "22px"
components:
  button-primary:
    backgroundColor: "{colors.teal-light}"
    textColor: "{colors.panel-light}"
    rounded: "{rounded.sm}"
    padding: "11px 20px"
  button:
    backgroundColor: "{colors.panel-2-light}"
    textColor: "{colors.fg-light}"
    rounded: "{rounded.sm}"
    padding: "8px 14px"
  next-step-bar:
    backgroundColor: "rgba(6,127,112,.1)"
    textColor: "{colors.fg-light}"
    rounded: "{rounded.md}"
    padding: "16px 18px"
  field-input:
    backgroundColor: "{colors.panel-2-light}"
    textColor: "{colors.fg-light}"
    rounded: "{rounded.sm}"
    padding: "9px 11px"
  pill:
    rounded: "{rounded.pill}"
    padding: "3px 9px"
---

# Design System: Solara

## 1. Overview

**Creative North Star: "The Office Register"**

Solara should feel like a well-kept office register. It opens on the customer, says the one thing to do next, and keeps everything else one click away.

The owner uses it on a laptop between site visits and phone calls, often in daylight. So the text is large enough to read at arm's length, the labels read like sentences, and colour is spent on the next action and on doubts, not on decoration.

It rejects:
- the control-room look of glowing tiles and big numbers;
- SaaS stat strips;
- the density of the government portals it fills.

The system has a light and a dark theme. Both are first class: the owner switches between them with the switch in the top bar, and every token is defined for both.

The Registration screen (`web/app.js`, `VIEWS.reg`; styles under `.rgv` in `web/styles.css`) is the reference implementation. Other screens still use the older, denser console style (13.5px text, small capitals labels, card grids). They move to this system screen by screen.

**Key characteristics:**
- One tinted "Next step" bar per screen. Filled teal marks the next action only.
- Sections divided by thin rules. The section for the current step comes first, and finished ones fold.
- 15px body, 13.5px sentence-case labels, 13px hints in a readable grey.
- Restrained colour: tinted neutrals, teal for action and progress, amber-yellow for "check this", red for errors.

## 2. Colors

The palette is cool, tinted neutrals with one action colour (teal) and one doubt colour (warn).

### Primary
- **Portal Teal** (#067F70 light / #35D0BA dark): the primary button, the Next step bar (at 10–12% as a tint, with a 30–34% border), the progress track and completed step marks, and focus rings. Nothing decorative.

### Secondary
- **Ledger Amber** (#AE6B06 light / #F2A63B dark): the brand mark and the current item in the side navigation. Not used for buttons on the Registration screen.

### Neutral
- **Desk Grey** (#EEF1F4 light / #0C0E11 dark): the page background behind the panels.
- **Sheet** (#FFFFFF light / #12151A dark): the panel surface, one per pane.
- **Sheet Shade** (#F6F8FA light / #171B21 dark): inputs, rows on hover, the idle Next bar.
- **Rule** (#D2DAE2 light / #272D36 dark): borders and section dividers.
- **Ink** (#111820 light / #E7EEF4 dark): body text, labels and values.
- **Ink Dim** (#53646F light / #93A2B2 dark): hints, meta text and secondary lines. It passes AA on Sheet in both themes.

### Status
- **Warn** (#9A6207 / #FBBF24): values to confirm, missing fields, and "from the vendor's quote" flags. It always comes with a word ("Missing", "Not sure", "Differs").
- **OK** (#17803D / #4ADE80): "on file", "Done", verified.
- **Bad** (#C32F26 / #F8716A): validation errors under a field, and the required star.
- **Info** (#1D5FBF / #6AA8FA): "waiting for e-sign" in the customer list.

### Named Rules
**The One Teal Rule.** Filled teal marks the next action and nothing else. Usually that is the Next step button. When the next step is to confirm a value, the Confirm beside each value is filled and the Next button turns plain. Save, Upload, Replace and the portal links are always plain buttons.

**The Faint-Is-Not-Text Rule.** `--fg-faint` (#7E8C98 on white is about 3.4:1) is never used for text the owner has to read. Hints and meta use Ink Dim.

## 3. Typography

**Display font:** Saira Condensed (with Archivo, system-ui).
**Body font:** Archivo (with Helvetica Neue, system-ui).
**Mono font:** JetBrains Mono, for customer IDs only.

**Character:** a condensed display face for the customer's name gives each record a clear title. Everything the owner reads or types is set in one humanist grotesque.

### Hierarchy
- **Display** (600, 28px, 1.1): the customer's name at the top of the pane. Only there.
- **Title** (650, 16.5px, Archivo): section headings ("Documents", "Details for the portal").
- **Body** (400, 15px, 1.55): sentences, values, and the Next step text, at most 68–72ch.
- **Label** (600, 13.5px, sentence case, no letter-spacing): field labels.
- **Hint** (400, 13px, Ink Dim): one line under a field or a section.
- **Mono** (12.5px): customer IDs such as SS-2051.

### Named Rules
**The Arm's Length Rule.** Body text is never below 15px, and labels are never below 13px or in capitals. Small capitals labels with wide tracking belong to the old console style and are being removed.

## 4. Elevation

The system is flat. Depth comes from tonal layers: Desk Grey behind, then the Sheet, then Sheet Shade for inputs and hover. It is not built from shadows.

The only tinted surfaces are the Next step bar and rows that need checking (Warn at about 10%). There are no cards inside cards: a pane is one Sheet, and its sections are divided by 1px rules.

### Named Rules
**The One Sheet Rule.** A pane is one surface. Sections inside it are separated by rules and spacing, never by nested bordered boxes.

## 5. Components

### Next step bar
- **Character:** the screen's single instruction.
- **Shape:** 6px radius, a 1px teal border at about 33%, a teal tint at 10–12%.
- **Content:** a "Next step" label in teal, one sentence on why, and the primary button. Below it, when needed, sit the application number field or a short list headed "Also needed before registering".
- **Done state:** a neutral Sheet Shade background and a check mark with the status. No button.

### Buttons
- **Shape:** 3px radius.
- **Primary:** Portal Teal fill, 15px, 11px × 20px padding. Only for the next action: the Next step button, or Confirm beside a value to check.
- **Default:** Sheet Shade fill, a 1px Rule border, 14px, 8px × 14px padding.
- **Small:** 13px, 6px × 11px padding (Upload, Replace, "Use 3 kW").
- **States:** hover darkens the border; active moves 1px down; disabled sits at 42% opacity with a not-allowed cursor; focus shows a 2px teal ring offset by 2px.
- **Labels:** a verb and an object ("Save details", "Replace number", "Send the link again").

### Sections (fold)
- A `<details>` element with a 1px top rule. The summary holds a chevron, a title and the meta in Ink Dim ("4 of 4 on file", "1 missing").
- The current step's section is rendered first. Finished sections fold.
- A section the owner opens or closes stays that way until another customer is picked. A section the owner is working in (adding documents) stays open.

### Progress steps
- Six equal columns. Each step has a 3px top track (Rule, or Teal when done), a 21px round mark (a number, a check when done, or a teal ring for the current step) and a short label: Documents, Details, Registered, Accepted, E-signed, Uploaded.
- Below 700px they wrap to three columns.

### Inputs and fields
- Sheet Shade fill, a 1px Rule border, 3px radius, 15px text, 9px × 11px padding.
- The label sits above, with a red star when the portal needs the field. One hint line sits below.
- An error appears in red under the hint while typing; the server checks the same rules again.
- A missing required field gets a warn border and ring, which clears as soon as it has a value.
- The cost reads back in lakh while typing ("Rs 2,10,000").

### Values to check
- A warn-tinted row: the field name and its source, an input with the value read, and a teal Confirm button. One line underneath says why it needs checking.
- A PIN conflict shows both values as two buttons: "Use 411001 (bill)" and "Use 410503 (Aadhaar)".

### Pills and status text
- Pill: fully rounded, 12px, a tinted background with the status colour, in lower case ("on file", "needed", "later").
- In the customer list, status is coloured text with no background: Done, Check 1 highlighted detail, Waiting for the customer's e-sign.

## 6. Do's and Don'ts

### Do:
- **Do** lead every screen with the one next step and its reason in one sentence.
- **Do** put a doubt beside its fix: the value, the input and Confirm in one row.
- **Do** use the portal's own words for fields (Consumer number, Application number, Vendor Consent).
- **Do** fold what is finished, and keep a section open while the owner is working in it.
- **Do** check both themes: every new colour needs a light and a dark value.
- **Do** keep transitions at 150–250 ms ease-out, with a `prefers-reduced-motion` alternative.

### Don't:
- **Don't** add big-number stat tiles. Counts go in one line ("4 in progress · 1 waiting for e-sign").
- **Don't** use small capitals labels with wide tracking, or text under 13px.
- **Don't** show a second filled button next to the Next step. Save is a plain button.
- **Don't** nest bordered cards inside a pane, and don't use coloured side stripes on rows.
- **Don't** repeat a message that is already shown beside its value.
- **Don't** use `--fg-faint` for readable text.
- **Don't** use em dashes in interface copy.
