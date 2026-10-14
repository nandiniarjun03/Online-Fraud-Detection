"""Menu database and the six business tools of the coffee ordering system.

Everything in this module is plain, deterministic Python. The agents never compute
prices or check stock themselves - they call these functions and report what comes back.
"""
from __future__ import annotations

import copy
import itertools
from typing import Optional

# --------------------------------------------------------------------------- menu database
# Base prices are per size. Milk and add-ons carry a surcharge on top of the base price.
MENU: dict = {
    "drinks": {
        "espresso":          {"name": "Espresso",          "category": "coffee", "prices": {"small": 2.50, "medium": 3.00, "large": 3.50}, "milk": "not_allowed", "available": True},
        "americano":         {"name": "Americano",         "category": "coffee", "prices": {"small": 3.00, "medium": 3.50, "large": 4.00}, "milk": "optional",    "available": True},
        "latte":             {"name": "Latte",             "category": "coffee", "prices": {"small": 3.75, "medium": 4.25, "large": 4.75}, "milk": "required",    "available": True},
        "cappuccino":        {"name": "Cappuccino",        "category": "coffee", "prices": {"small": 3.75, "medium": 4.25, "large": 4.75}, "milk": "required",    "available": True},
        "flat white":        {"name": "Flat White",        "category": "coffee", "prices": {"small": 4.00, "medium": 4.50, "large": 5.00}, "milk": "required",    "available": True},
        "mocha":             {"name": "Mocha",             "category": "coffee", "prices": {"small": 4.25, "medium": 4.75, "large": 5.25}, "milk": "required",    "available": True},
        "caramel macchiato": {"name": "Caramel Macchiato", "category": "coffee", "prices": {"small": 4.50, "medium": 5.00, "large": 5.50}, "milk": "required",    "available": False},
        "cold brew":         {"name": "Cold Brew",         "category": "cold",   "prices": {"small": 3.50, "medium": 4.00, "large": 4.50}, "milk": "optional",    "available": True},
        "chai latte":        {"name": "Chai Latte",        "category": "tea",    "prices": {"small": 4.00, "medium": 4.50, "large": 5.00}, "milk": "required",    "available": True},
    },
    "sizes": ["small", "medium", "large"],
    "milks": {"whole": 0.00, "skim": 0.00, "oat": 0.60, "almond": 0.60, "soy": 0.50},
    "add_ons": {"extra shot": 0.80, "vanilla syrup": 0.50, "caramel syrup": 0.50,
                "hazelnut syrup": 0.50, "whipped cream": 0.40},
    # Free-text preferences that are accepted but never change the price.
    "preferences": ["no sugar", "less sugar", "extra hot", "less ice"],
}

TAX_RATE = 0.08
_order_numbers = itertools.count(1042)   # mock backend: sequential order numbers
ORDERS_DB: dict[str, dict] = {}          # mock backend: submitted orders


def _key(name: Optional[str]) -> str:
    return (name or "").strip().lower()


def _find_drink(name: str) -> Optional[dict]:
    key = _key(name)
    if key in MENU["drinks"]:
        return MENU["drinks"][key]
    for drink in MENU["drinks"].values():          # tolerate "Lattes", "a latte", ...
        if drink["name"].lower() in key or key.rstrip("s") == drink["name"].lower():
            return drink
    return None


# --------------------------------------------------------------------------- tool 1
def get_menu(category: Optional[str] = None) -> dict:
    """Return the menu (optionally filtered by category: coffee, tea, cold)."""
    drinks = [
        {"item": d["name"], "category": d["category"], "prices": d["prices"],
         "milk": d["milk"], "available": d["available"]}
        for d in MENU["drinks"].values()
        if not category or d["category"] == _key(category)
    ]
    return {"drinks": drinks, "sizes": MENU["sizes"], "milks": MENU["milks"],
            "add_ons": MENU["add_ons"], "preferences": MENU["preferences"],
            "currency": "USD", "tax_rate": TAX_RATE}


# --------------------------------------------------------------------------- tool 2
def check_availability(item_name: str) -> dict:
    """Return whether a drink is on the menu and currently in stock."""
    drink = _find_drink(item_name)
    if drink is None:
        return {"item": item_name, "on_menu": False, "available": False}
    return {"item": drink["name"], "on_menu": True, "available": drink["available"]}


# --------------------------------------------------------------------------- tool 3
def validate_order(item: str, size: Optional[str], milk: Optional[str],
                   extras: Optional[list[str]] = None) -> dict:
    """Check one drink and its customisations against the menu.

    Returns valid / invalid with a reason, the list of details still missing
    (so the agent can ask a follow-up question) and the unit price when valid.
    """
    extras = [_key(e) for e in (extras or []) if _key(e)]
    drink = _find_drink(item)
    if drink is None:
        return {"valid": False, "reason": f"'{item}' is not on our menu.", "missing": []}
    if not drink["available"]:
        return {"valid": False, "reason": f"{drink['name']} is currently out of stock.", "missing": []}

    missing = []
    size_k, milk_k = _key(size), _key(milk)
    if not size_k:
        missing.append("size")
    elif size_k not in MENU["sizes"]:
        return {"valid": False, "reason": f"'{size}' is not a size we offer (small, medium, large).", "missing": []}

    if drink["milk"] == "required" and milk_k in ("", "none", "no milk"):
        missing.append("milk")
    elif drink["milk"] == "not_allowed" and milk_k not in ("", "none", "no milk"):
        return {"valid": False, "reason": f"{drink['name']} is served without milk.", "missing": []}
    elif milk_k not in ("", "none", "no milk") and milk_k not in MENU["milks"]:
        return {"valid": False, "reason": f"'{milk}' milk is not available.", "missing": []}

    for extra in extras:
        if extra not in MENU["add_ons"] and extra not in MENU["preferences"]:
            return {"valid": False, "reason": f"'{extra}' is not an add-on we offer.", "missing": []}

    if missing:
        return {"valid": False, "reason": "More details are needed.", "missing": missing}

    milk_k = milk_k if milk_k in MENU["milks"] else "none"
    unit = drink["prices"][size_k] + MENU["milks"].get(milk_k, 0.0) \
        + sum(MENU["add_ons"].get(e, 0.0) for e in extras)
    return {"valid": True, "reason": "OK", "missing": [],
            "line": {"item": drink["name"], "size": size_k, "milk": milk_k,
                     "extras": extras, "unit_price": round(unit, 2)}}


# --------------------------------------------------------------------------- tool 4
def update_cart(cart: list[dict], action: str, item: dict) -> dict:
    """Add, remove or change the quantity of a cart line. Returns the new cart.

    `add` re-validates the item, so nothing invalid or out of stock can enter the cart
    even if an agent tries to add it.
    """
    cart = copy.deepcopy(cart)
    action = _key(action)
    if action == "clear":
        return {"ok": True, "cart": []}

    if action == "add":
        check = validate_order(item.get("item", ""), item.get("size"), item.get("milk"), item.get("extras"))
        if not check["valid"]:
            return {"ok": False, "reason": check["reason"], "missing": check["missing"], "cart": cart}
        line = check["line"]
        qty = max(1, int(item.get("quantity", 1)))
        for existing in cart:                       # merge identical lines
            if all(existing[k] == line[k] for k in ("item", "size", "milk", "extras")):
                existing["quantity"] += qty
                existing["line_total"] = round(existing["quantity"] * existing["unit_price"], 2)
                return {"ok": True, "cart": cart}
        cart.append({**line, "quantity": qty, "line_total": round(qty * line["unit_price"], 2)})
        return {"ok": True, "cart": cart}

    drink = _find_drink(item.get("item", ""))
    name = drink["name"] if drink else item.get("item", "")
    matches = [l for l in cart if l["item"] == name and (not item.get("size") or l["size"] == _key(item["size"]))]
    if not matches:
        return {"ok": False, "reason": f"{name} is not in the cart.", "cart": cart}
    target = matches[0]
    if action == "remove":
        cart.remove(target)
    elif action == "update_quantity":
        qty = int(item.get("quantity", 1))
        if qty <= 0:
            cart.remove(target)
        else:
            target["quantity"] = qty
            target["line_total"] = round(qty * target["unit_price"], 2)
    else:
        return {"ok": False, "reason": f"Unknown action '{action}'.", "cart": cart}
    return {"ok": True, "cart": cart}


# --------------------------------------------------------------------------- tool 5
def calculate_total(cart: list[dict]) -> dict:
    """Compute subtotal, tax and total for the cart."""
    subtotal = round(sum(l["unit_price"] * l["quantity"] for l in cart), 2)
    tax = round(subtotal * TAX_RATE, 2)
    return {"items": sum(l["quantity"] for l in cart), "subtotal": subtotal,
            "tax_rate": TAX_RATE, "tax": tax, "total": round(subtotal + tax, 2)}


# --------------------------------------------------------------------------- tool 6
def place_order(cart: list[dict], customer_name: str) -> dict:
    """Submit the order to the mock backend; returns an order ID and pickup estimate."""
    if not cart:
        return {"success": False, "reason": "Cannot place an empty order."}
    if not _key(customer_name):
        return {"success": False, "reason": "A customer name is required for pickup."}
    order_id = f"#{next(_order_numbers)}"
    drinks = sum(l["quantity"] for l in cart)
    pickup_minutes = 5 + 3 * drinks
    ORDERS_DB[order_id] = {"customer": customer_name.strip(), "cart": copy.deepcopy(cart),
                           "totals": calculate_total(cart), "pickup_minutes": pickup_minutes}
    return {"success": True, "order_id": order_id, "customer_name": customer_name.strip(),
            "pickup_minutes": pickup_minutes, "totals": ORDERS_DB[order_id]["totals"]}
