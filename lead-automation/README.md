# AI Lead Responder: Google Form → Claude → Email/WhatsApp → Google Sheet

A Google Apps Script automation. It runs entirely inside your Google account, so there is no server to host.

```
Lead fills Google Form
        │  (installable "On form submit" trigger)
        ▼
handleFormSubmit ──► Claude API (structured JSON output)
        │              • email subject + body
        │              • WhatsApp message
        │              • lead score (hot/warm/cold) + one-line summary
        ▼
Deliver on the lead's preferred channel
        │  Email    → Gmail (send or draft)
        │  WhatsApp → wa.me click-to-chat link, or WhatsApp Cloud API
        ▼
Append a row to the "Leads Log" tab (lead + AI output + delivery status)
```

Failed leads are still logged, with the error, and **Lead Automation → Retry failed rows** processes them again.

## Setup (about 5 minutes)

1. **Create a Google Sheet** (for example "Leads"). Open **Extensions → Apps Script**.
2. Replace the contents of `Code.gs` with [`Code.gs`](Code.gs). In **Project Settings**, tick *Show "appsscript.json"* and paste [`appsscript.json`](appsscript.json).
   (Or use [clasp](https://github.com/google/clasp): `clasp create --type sheets --title Leads && clasp push`.)
3. **Project Settings → Script Properties**: add these.

   | Property | Required | Example / default |
   |---|---|---|
   | `ANTHROPIC_API_KEY` | ✅ | your key from console.anthropic.com |
   | `BUSINESS_NAME` | recommended | `Acme Studio` |
   | `BUSINESS_CONTEXT` | recommended | 2–5 sentences: what you sell, who for, what the next step is. The AI only states facts written here. |
   | `SENDER_NAME` | recommended | `Asha` |
   | `REPLY_TO` | optional | `sales@acme.com` |
   | `EMAIL_MODE` | optional | `send` (default) · `draft` (human reviews in Gmail) · `off` |
   | `WHATSAPP_MODE` | optional | `link` (default) · `cloud_api` · `off` |
   | `DEFAULT_COUNTRY_CODE` | optional | `91`, added to 10-digit local numbers |
   | `CLAUDE_MODEL` | optional | `claude-opus-5-5` |

4. Reload the Sheet. A **Lead Automation** menu appears. Run:
   - **1. Setup**: creates the `Leads Log` tab and installs the form-submit trigger. Approve the permissions prompt.
   - **2. Create lead capture Google Form**: builds the form (name, email, WhatsApp number, company, interest, details, preferred channel), links it to this Sheet and shows the public link.
5. **Run with a sample lead** sends a test lead to *your own* email address. Then check the `Leads Log` tab and your inbox.

Already have a form? Link it to the Sheet (Form → Responses → Link to Sheets) and run **Setup**. Questions are matched by title, and common wording like "Your name", "E-mail" or "Phone" is recognised. Questions that don't match any field are passed to the AI as extra context.

## WhatsApp options

- **`link` (default, no extra setup):** the log gets a `https://wa.me/<number>?text=<AI message>` link. Click it and the message opens pre-filled in WhatsApp, ready to send. This works with any personal or Business WhatsApp number.
- **`cloud_api` (fully automatic):** sends through the Meta WhatsApp Business Cloud API. Set `WHATSAPP_TOKEN` and `WHATSAPP_PHONE_NUMBER_ID`. WhatsApp only allows free-form text within 24 h after the customer messages you. To reach a *new* lead you need an approved template: create one whose body is a single variable `{{1}}`, then set `WHATSAPP_TEMPLATE_NAME` (and `WHATSAPP_TEMPLATE_LANG`, default `en`). The AI message fills `{{1}}`. Line breaks are flattened, because WhatsApp rejects them in template variables.

## Log columns

`Logged At · Lead ID · Submitted At · Name · Email · Phone · Company · Interest · Message · Preferred Channel · Lead Score · Lead Summary · Email Subject · Email Body · WhatsApp Message · WhatsApp Link · Delivery Channel · Delivery Status · Model · Error`

## Safeguards built in

- Form answers are passed to Claude as data, and the prompt tells it not to follow instructions written in them. It is also told not to invent prices, discounts or promises.
- Answers that start with `= + - @` are escaped, so a lead can't inject spreadsheet formulas.
- Rate limits, overloads and 5xx errors are retried with backoff (`retry-after` is respected).
- If Claude declines a request, the API falls back to another model automatically (`fallbacks: "default"`). If every model declines, that is logged.
- A script lock prevents overlapping writes when several leads submit at once.
- Anyone can type any email address into a public form. If you're worried about abuse, set `EMAIL_MODE=draft` and review replies before sending.

## Tests

The tests run offline in Node with mocked Google services and a mocked Claude API:

```bash
node test/run-tests.js
```

They cover: email and WhatsApp paths, Cloud API template payload, draft mode, retry/backoff, error logging and `retryFailed`, refusals, a missing key, custom form titles, formula injection, and phone normalisation.
