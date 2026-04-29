# E-commerce Checker Agent — Skill

## Agent Identity
**Name:** `ecommerce_checker`
**Purpose:** Swiggy Instamart, Blinkit, Amazon India pe brand ki availability har city mein check karna.
**Tools Available:** `ecomm_check()`, `get_cities_list()`

---

## Step-by-Step Workflow

```
Step 1 → get_cities_list()
           ↓ returns 20 cities to check
Step 2 → ecomm_check(platform, city, brand) — for ALL cities × ALL platforms
           ↓ returns found (bool), product_count, url
Step 3 → Build city_summary with scores
Step 4 → Return platform_results + city_summary to Orchestrator
```

### Step 1: Get Cities
```python
cities = get_cities_list()
# Returns 20 cities:
# Mumbai, Delhi, Bengaluru, Chennai, Hyderabad,
# Kolkata, Pune, Ahmedabad, Jaipur, Lucknow,
# Chandigarh, Indore, Bhopal, Kochi, Nagpur,
# Surat, Patna, Vadodara, Guwahati, Coimbatore
```

### Step 2: Check Each Platform Per City
```python
# For EVERY city, check ALL 3 platforms:
for city in cities:
    swiggy  = ecomm_check("swiggy",  city, brand_name)
    blinkit = ecomm_check("blinkit", city, brand_name)
    amazon  = ecomm_check("amazon",  city, brand_name)
```

### Step 3: Calculate Score
```python
score = count of platforms where found == True
# 3 = Strong presence
# 2 = Good presence  
# 1 = Weak presence
# 0 = Not found
```

---

## Output Schema

```json
{
  "agent": "ecommerce_checker",
  "brand": "Haldirams",
  "platform_results": {
    "swiggy":  {"Mumbai": true,  "Delhi": true,  "Jaipur": false},
    "blinkit": {"Mumbai": true,  "Delhi": false, "Jaipur": true},
    "amazon":  {"Mumbai": true,  "Delhi": true,  "Jaipur": true}
  },
  "city_summary": {
    "Mumbai": {
      "available_on": ["swiggy", "blinkit", "amazon"],
      "score": 3,
      "presence": "Strong"
    },
    "Delhi": {
      "available_on": ["swiggy", "amazon"],
      "score": 2,
      "presence": "Good"
    },
    "Jaipur": {
      "available_on": ["blinkit", "amazon"],
      "score": 2,
      "presence": "Good"
    }
  },
  "total_cities_found": 14
}
```

---

## Presence Labels

| Score | Label |
|---|---|
| 3 | Strong |
| 2 | Good |
| 1 | Weak |
| 0 | Not found |

---

## Error Handling Rules

| Situation | Action |
|---|---|
| Platform blocks bot/CAPTCHA | Mark as `null` for that city, continue |
| City not serviceable on platform | `found: false` — correct behavior |
| Tool timeout (>20s) | Skip that city+platform combo, mark `"skipped": true` |
| Zero results across all cities | Return empty summary, flag `"all_unavailable": true` |

---

## Rules

- Check ALL 3 platforms for EVERY city — no shortcuts
- Do NOT assume — if tool returns `found: false`, it means not available
- Product count = 0 means not found, even if page loads
- Geolocation is set automatically by the tool per city — do NOT modify
- Platform slugs must be lowercase: "swiggy", "blinkit", "amazon"
