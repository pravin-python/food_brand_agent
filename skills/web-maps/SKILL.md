# Web & Maps Agent — Skill

## Agent Identity
**Name:** `web_maps`
**Purpose:** Google Maps, Justdial, IndiaMart se brand ke distributors aur dealers ki city-wise location nikalna.
**Tools Available:** `maps_search()`, `justdial_search()`, `indiamart_search()`

---

## Step-by-Step Workflow

```
Step 1 → indiamart_search(brand_name)
           ↓ national distributor list milti hai
Step 2 → maps_search("{brand} distributor", city) — Tier 1 cities
           ↓ Google Maps results
Step 3 → justdial_search(brand, city) — top 10 cities
           ↓ local dealer listings
Step 4 → Cross-verify + build state_coverage
Step 5 → Return to Orchestrator
```

### Step 1: IndiaMart (Run First — National Level)
```python
suppliers = indiamart_search("Haldirams")
# Gives national distributor network in one call
# Returns: name, city, state per supplier
```

### Step 2: Google Maps (Tier 1 + 2 Cities)
```python
cities_to_check = [
    "Mumbai", "Delhi", "Bengaluru", "Chennai", "Hyderabad",
    "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Lucknow"
]
for city in cities_to_check:
    results = maps_search(f"{brand} distributor", city)
```

### Step 3: Justdial (Top 10 Cities Only)
```python
for city in cities_to_check[:10]:
    results = justdial_search(brand, city)
```

### Step 4: Cross-Verify
```python
# If same city appears in 2+ sources → verified = True
# If only 1 source → verified = False
```

---

## Output Schema

```json
{
  "agent": "web_maps",
  "brand": "Haldirams",
  "distributors": [
    {
      "name": "Sharma Distributors",
      "city": "Jaipur",
      "state": "Rajasthan",
      "address": "MI Road, Jaipur - 302001",
      "phone": "9876543210",
      "source": "google_maps",
      "verified": true
    }
  ],
  "state_coverage": {
    "Maharashtra": {
      "distributor_count": 8,
      "cities": ["Mumbai", "Pune", "Nagpur"],
      "verified": true
    },
    "Rajasthan": {
      "distributor_count": 3,
      "cities": ["Jaipur", "Jodhpur"],
      "verified": false
    }
  },
  "total_distributors": 45,
  "total_states_covered": 18
}
```

---

## Cross-Verification Logic

```
city in google_maps AND justdial  → verified = true
city in google_maps AND indiamart → verified = true
city in only 1 source             → verified = false
state has 1+ verified city        → state verified = true
```

---

## Error Handling Rules

| Situation | Action |
|---|---|
| Google Maps API key missing | Fall back to Playwright scraping automatically |
| SerpAPI rate limit | Switch to Playwright, continue |
| No results for a city | Skip that city, do NOT add fake entries |
| Justdial blocks request | Skip Justdial, use Maps + IndiaMart only |
| IndiaMart fails | Continue with Maps + Justdial |

---

## Rules

- Minimum 1 verified result per state to mark state "covered"
- Never add distributors without a real address
- Source must always be: "google_maps", "justdial", or "indiamart"
- Phone numbers are optional — include if available
- City names must match standard spelling: "Bengaluru" not "Bangalore"
