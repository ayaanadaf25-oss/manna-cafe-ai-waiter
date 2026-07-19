# Manna Cafe AI Waiter 🍔

Production WhatsApp order desk for **Manna Cafe**.

Customers can:
1. View the digital menu & place food orders  
2. Check order status  
3. Cancel a **Pending** order  

The cafe owner only monitors / updates `status` in Google Sheets.

---

## Architecture

```
WhatsApp Customer
      │ sends message
      ▼
Twilio WhatsApp API
      │ HTTP POST (instant)
      ▼
Flask Webhook (/webhook)          ← app.py
      │
      ├─ flows.py     (menu router 1/2/3 + free-text orders)
      │     ├─ ai_extract.py  (OpenAI JSON or heuristic menu match)
      │     └─ sheets.py      (Live_Orders / Menu / Incoming_Messages)
      │
      └─ whatsapp.py  (TwiML reply — Twilio delivers instantly)
             │
             ▼
      Customer WhatsApp
```

---

## Project structure

```
manna_cafe_ai_waiter/
├── app.py                 ← Flask + /webhook + /health + /orders
├── Procfile
├── railway.toml
├── runtime.txt
├── requirements.txt
├── .env.example
├── .gitignore
├── core/
│   ├── config.py          ← env vars
│   ├── sheets.py          ← Google Sheets DB
│   ├── flows.py           ← menu routing + business logic
│   ├── ai_extract.py      ← AI / heuristic order extract
│   ├── whatsapp.py        ← TwiML + outbound Twilio
│   └── test_flows.py      ← pytest
├── credentials/
│   └── google_service_account.json   ← you add this (not in git)
└── docs/
    └── README.md
```

---

## Conversation flows

| Customer text | Bot action |
|---------------|------------|
| `hi` / `hello` / `menu` | Main menu (1/2/3) |
| `1` | Digital menu link + order instructions |
| free text e.g. `1 Ultimate Chicken Burger` | Extract item+qty → append `Live_Orders` → confirm |
| `2` | Latest order status for that phone |
| `3` | Cancel latest **Pending** order |
| `4` | Invalid option help |

### Google Sheet: `MannaCafe_Counter_Dashboard`

**Live_Orders** columns:

`order_id | phone | item_name | quantity | status | created_at`

Owner edits **status** only: `Pending` → `Preparing` → `Ready` / `Served` / `Cancelled`.

---

## Local setup

```bash
cd manna_cafe_ai_waiter
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env — Twilio + Google service account

# put service account JSON here OR paste JSON into GOOGLE_SERVICE_ACCOUNT_JSON
# credentials/google_service_account.json

# Share the Google Sheet with the service account email (Editor)

pytest core/test_flows.py -v
python app.py
# webhook: http://localhost:5000/webhook
```

### Share the Sheet

1. Open Google Cloud → Service Account → copy `client_email`  
2. Open [MannaCafe_Counter_Dashboard](https://docs.google.com/spreadsheets/d/1g4Xi6nQ_gUwINeKL79DG7vhFZadbBYGzKzBaWcUuEt4/edit)  
3. Share → paste service account email → **Editor**

---

## Railway deploy (exact commands)

```bash
# 0) Unzip & enter project
unzip manna_cafe_ai_waiter.zip
cd manna_cafe_ai_waiter

# 1) Init git (Railway deploys from git)
git init
git add .
git commit -m "Manna Cafe AI Waiter production webhook"

# 2) Login / create project (install CLI first if needed:
#    npm i -g @railway/cli   OR   brew install railway)
railway login
railway init
# follow prompts: create new project e.g. "manna-cafe-ai-waiter"

# 3) Set environment variables
railway variables set \
  TWILIO_ACCOUNT_SID="ACxxxx" \
  TWILIO_AUTH_TOKEN="your_token" \
  TWILIO_WHATSAPP_FROM="whatsapp:+14155238886" \
  SPREADSHEET_ID="1g4Xi6nQ_gUwINeKL79DG7vhFZadbBYGzKzBaWcUuEt4" \
  SPREADSHEET_NAME="MannaCafe_Counter_Dashboard" \
  SECRET_KEY="$(openssl rand -hex 32)" \
  CAFE_NAME="Manna Cafe" \
  TIMEZONE="Asia/Kolkata" \
  LOG_INCOMING_MESSAGES="true"

# Service account JSON (single-line). Example from file:
railway variables set GOOGLE_SERVICE_ACCOUNT_JSON="$(cat credentials/google_service_account.json | tr -d '\n')"

# Optional OpenAI (better free-text extraction)
# railway variables set OPENAI_API_KEY="sk-..." OPENAI_MODEL="gpt-4o-mini"

# 4) Deploy
railway up

# 5) Public domain
railway domain
# copy the URL, e.g. https://manna-cafe-ai-waiter-production.up.railway.app

# 6) Health check
curl https://YOUR-DOMAIN.up.railway.app/health
```

### Point Twilio at Railway

1. Twilio Console → Messaging → Try it out → **WhatsApp Sandbox**  
   (or your WhatsApp Sender → Integration)  
2. **When a message comes in:**  
   `https://YOUR-DOMAIN.up.railway.app/webhook`  
3. Method: **HTTP POST**  
4. Save  

Join the sandbox from your phone (Twilio join code), then text:

```
hi
1
1 Ultimate Chicken Burger
2
3
```

---

## Optional: GitHub → Railway

```bash
gh repo create manna-cafe-ai-waiter --private --source=. --remote=origin --push
# Railway Dashboard → New Project → Deploy from GitHub repo
# Add the same variables in the Railway Variables UI
```

---

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/webhook` | Twilio WhatsApp inbound (TwiML out) |
| GET | `/health` | Health check |
| GET | `/orders` | Kitchen JSON snapshot (lock down in prod) |
| GET | `/` | Service index |

---

## Production checklist

- [ ] `.env` / Railway variables set (never commit secrets)
- [ ] Sheet shared with service account **Editor**
- [ ] Twilio webhook → `https://…/webhook` POST  
- [ ] `/health` returns 200  
- [ ] Test full path: hi → 1 → order → 2 → 3  
- [ ] Protect `/orders` if public  
- [ ] Optional: `OPENAI_API_KEY` for stronger NLP  

---

## Support

Check Railway logs:

```bash
railway logs
```

All inbound messages log at INFO with phone + body + reply preview.
