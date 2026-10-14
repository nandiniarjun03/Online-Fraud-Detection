"""Run the six test scenarios from the assignment and save a log of every turn."""
import json
import sys
import time

from coffee_graph import build_app, new_turn

app = build_app()

# (scenario, thread, customer message, fault_injection)
SCRIPT = [
    ("1. Browse the menu",          "main",  "What coffees do you have?", False),
    ("2. Build an order",           "main",  "I want a large latte with oat milk.", False),
    ("3. Incomplete order",         "main",  "Get me a cappuccino.", False),
    ("3. Incomplete order",         "main",  "Medium, with whole milk please.", False),
    ("4. Place the order",          "main",  "That's all, place my order.", False),
    ("4. Place the order",          "main",  "Yes, confirm it. The name is Nandini.", False),
    ("5. Unavailable item",         "s5",    "One caramel macchiato.", False),
    ("5b. Unavailable item - evaluator & retry (fault injected)", "s5b", "One caramel macchiato.", True),
    ("6. Empty cart",               "s6",    "Place my order.", False),
]


def run_turn(thread: str, text: str, fault: bool) -> dict:
    cfg = {"configurable": {"thread_id": thread}}
    path, attempts = [], []
    for update in app.stream(new_turn(text, fault), cfg, stream_mode="updates"):
        for node, delta in update.items():
            path.append(node)
            delta = delta or {}
            if node == "planner":
                attempts.append({"intent": delta.get("intent")})
            elif node.endswith("_agent"):
                attempts[-1].update(agent=node, draft=delta.get("draft_response"),
                                    tools=[{"tool": c["tool"], "args": c["args"]} for c in delta.get("tool_log", [])])
            elif node == "evaluator":
                ev = delta.get("evaluation", {})
                attempts[-1]["evaluation"] = {k: ev.get(k) for k in
                                              ("verdict", "score", "feedback", "correctness", "completeness",
                                               "no_hallucination", "intent_match")}
    state = app.get_state(cfg).values
    return {"path": ["__start__", *path, "__end__"], "attempts": attempts,
            "response": state["messages"][-1].content, "retry_count": state.get("retry_count", 0),
            "cart": state.get("cart", []), "order_id": state.get("order_id"),
            "awaiting_confirmation": state.get("awaiting_confirmation", False)}


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "scenario_log.json"
    results = []
    for scenario, thread, text, fault in SCRIPT:
        t0 = time.time()
        r = run_turn(thread, text, fault)
        r.update(scenario=scenario, thread=thread, user=text, fault_injection=fault,
                 seconds=round(time.time() - t0, 1))
        results.append(r)
        print(f"\n=== {scenario}  [thread {thread}]\nUSER: {text}\nFLOW: {' -> '.join(r['path'])}")
        for i, a in enumerate(r["attempts"]):
            print(f"  attempt {i + 1}: intent={a.get('intent')} tools={[t['tool'] for t in a.get('tools', [])]} "
                  f"verdict={a.get('evaluation', {}).get('verdict')} score={a.get('evaluation', {}).get('score')}")
        print(f"ASSISTANT: {r['response']}\nCART: {r['cart']}  ORDER: {r['order_id']}")
        json.dump(results, open(out, "w"), indent=2)
