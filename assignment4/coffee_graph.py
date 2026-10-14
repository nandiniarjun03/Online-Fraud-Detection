"""Automated Coffee Ordering System - multi-agent LangGraph implementation.

Graph:  START -> planner -> {menu_agent | order_agent | placement_agent} -> evaluator -> END
        evaluator --(rejected, retries left)--> planner
"""
from __future__ import annotations

import json
from typing import Annotated, Literal, Optional, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

import coffee_tools as T

MODEL = "claude-opus-5-5"
MAX_RETRIES = 2

# One client per role. Low effort keeps the chat agents fast; the judge thinks harder.
agent_llm = ChatAnthropic(model=MODEL, max_tokens=4096, output_config={"effort": "low"})
judge_llm = ChatAnthropic(model=MODEL, max_tokens=4096, output_config={"effort": "medium"})


# =========================================================================== shared state
class CoffeeState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]  # approved conversation only
    intent: Literal["browse_menu", "build_order", "place_order"]
    cart: list[dict]                 # committed cart (only changes on an approved turn)
    pending_cart: list[dict]         # cart proposed by the agent in the current attempt
    order_id: Optional[str]
    customer_name: Optional[str]
    awaiting_confirmation: bool      # placement agent has shown the total and asked to confirm
    evaluation: dict                 # {verdict, score, feedback}
    retry_count: int                 # retries used in the current turn (max 2)
    active_agent: str
    draft_response: str              # agent answer waiting for the evaluator
    tool_log: list[dict]             # tool calls + results of the current attempt
    planner_note: str                # evaluator feedback passed to the agent on a retry
    fault_injection: bool            # test hook: force one bad answer to exercise the retry loop


# =========================================================================== LLM-facing tools
# The cart and customer data live in graph state, not in the model's context. These wrappers
# expose only what the model should choose; the cart is injected by `run_agent` below.
@tool("get_menu")
def get_menu_tool(category: Optional[str] = None) -> str:
    """List drinks with prices per size, availability, milk options and add-ons. Optional category: coffee, tea or cold."""


@tool("check_availability")
def check_availability_tool(item_name: str) -> str:
    """Check whether a drink is on the menu and currently in stock."""


@tool("validate_order")
def validate_order_tool(item: str, size: Optional[str] = None, milk: Optional[str] = None,
                        extras: Optional[list[str]] = None) -> str:
    """Validate one drink and its customisations. Leave size/milk empty if the customer did not say; the result lists what is missing."""


@tool("update_cart")
def update_cart_tool(action: Literal["add", "remove", "update_quantity", "clear"], item: str = "",
                     size: Optional[str] = None, milk: Optional[str] = None,
                     extras: Optional[list[str]] = None, quantity: int = 1) -> str:
    """Change the customer's cart. 'add' validates the drink first and refuses invalid or out-of-stock items."""


@tool("calculate_total")
def calculate_total_tool() -> str:
    """Compute subtotal, tax and total for the current cart."""


@tool("place_order")
def place_order_tool(customer_name: str) -> str:
    """Submit the current cart. Only call after the customer has seen the total and explicitly confirmed."""


def _execute(name: str, args: dict, ctx: dict) -> dict:
    """Run one tool call against the real implementation, using state held in ctx."""
    if name == "get_menu":
        return T.get_menu(args.get("category"))
    if name == "check_availability":
        return T.check_availability(args["item_name"])
    if name == "validate_order":
        return T.validate_order(args["item"], args.get("size"), args.get("milk"), args.get("extras"))
    if name == "update_cart":
        result = T.update_cart(ctx["cart"], args["action"], {k: v for k, v in args.items() if k != "action"})
        ctx["cart"] = result["cart"]
        return result
    if name == "calculate_total":
        return T.calculate_total(ctx["cart"])
    if name == "place_order":
        # Guardrails enforced in code, not left to the prompt.
        if not ctx["cart"]:
            return {"success": False, "reason": "Cart is empty - nothing to place."}
        if not ctx["awaiting_confirmation"]:
            return {"success": False, "reason": "Show the total and get the customer's confirmation first."}
        result = T.place_order(ctx["cart"], args.get("customer_name") or ctx.get("customer_name") or "")
        if result.get("success"):
            ctx["order_id"] = result["order_id"]
            ctx["customer_name"] = result["customer_name"]
        return result
    return {"error": f"unknown tool {name}"}


def run_agent(system: str, state: CoffeeState, tools: list, ctx: dict, max_steps: int = 8):
    """Small tool-calling loop: call the model, run requested tools, repeat until it answers."""
    llm = agent_llm.bind_tools(tools)
    msgs: list[BaseMessage] = [SystemMessage(system), *state["messages"]]
    log = []
    for _ in range(max_steps):
        ai = llm.invoke(msgs)
        msgs.append(ai)
        if not ai.tool_calls:
            return ai.text, log
        for call in ai.tool_calls:
            result = _execute(call["name"], call["args"], ctx)
            log.append({"tool": call["name"], "args": call["args"], "result": result})
            msgs.append(ToolMessage(json.dumps(result), tool_call_id=call["id"]))
    return "Sorry, I couldn't finish that request. Could you try again?", log


def _cart_text(cart: list[dict]) -> str:
    if not cart:
        return "(empty)"
    return "; ".join(
        f"{l['quantity']} x {l['size'].title()} {l['item']}"
        + (f" ({l['milk']} milk)" if l["milk"] != "none" else "")
        + (f" + {', '.join(l['extras'])}" if l["extras"] else "")
        + f" @ ${l['unit_price']:.2f}"
        for l in cart)


def _retry_hint(state: CoffeeState) -> str:
    note = state.get("planner_note")
    return f"\n\nYOUR PREVIOUS ATTEMPT WAS REJECTED BY QUALITY REVIEW. Fix this: {note}" if note else ""


# =========================================================================== planner
class PlannerDecision(BaseModel):
    intent: Literal["browse_menu", "build_order", "place_order"] = Field(
        description="browse_menu = questions about drinks, prices, options or stock; "
                    "build_order = adding, changing or removing drinks, or answering the order agent's follow-up; "
                    "place_order = finishing, checking out, confirming or cancelling checkout")
    reason: str = Field(description="One short sentence explaining the choice")


PLANNER_PROMPT = """You are the planner of a coffee shop ordering assistant. You do not talk to the customer.
Classify the customer's LATEST message into exactly one intent, using the conversation for context.

Current cart: {cart}
Awaiting order confirmation: {awaiting}

Rules:
- A reply to a follow-up question about size, milk or quantity is build_order.
- "That's all", "checkout", "place my order", a name, or yes/no while confirmation is awaited is place_order.
- Asking what exists, what it costs or whether something is in stock (without ordering it) is browse_menu.
- Ordering a specific drink, even one that may be out of stock, is build_order."""


def planner(state: CoffeeState) -> dict:
    decider = agent_llm.with_structured_output(PlannerDecision, method="json_schema")
    decision = decider.invoke([
        SystemMessage(PLANNER_PROMPT.format(cart=_cart_text(state.get("cart", [])),
                                            awaiting=state.get("awaiting_confirmation", False))),
        *state["messages"],
    ])
    feedback = state.get("evaluation", {}).get("feedback", "") if state.get("retry_count", 0) else ""
    return {"intent": decision.intent, "planner_note": feedback}


def route_from_planner(state: CoffeeState) -> str:
    return {"browse_menu": "menu_agent", "build_order": "order_agent",
            "place_order": "placement_agent"}[state["intent"]]


# =========================================================================== menu agent
MENU_PROMPT = """You are the menu assistant at a coffee shop.
Answer the customer's question about drinks, sizes, milks, add-ons, prices and availability.
Always call get_menu (and check_availability for specific drinks) first, and answer ONLY from tool results -
never mention a drink, price or offer that the tools did not return. Mark out-of-stock drinks clearly.
Keep it short and friendly; prices in USD with two decimals. Do not add anything to the cart."""


def menu_agent(state: CoffeeState) -> dict:
    ctx = {"cart": list(state.get("cart", []))}
    text, log = run_agent(MENU_PROMPT + _retry_hint(state), state,
                          [get_menu_tool, check_availability_tool], ctx)
    return {"active_agent": "menu_agent", "draft_response": text, "tool_log": log,
            "pending_cart": state.get("cart", [])}


# =========================================================================== order agent
ORDER_PROMPT = """You are the order-taking assistant at a coffee shop. Current cart: {cart}

For each drink in the customer's latest message:
1. Extract item, size, milk, add-ons and quantity. Never guess a detail the customer did not give.
2. Call validate_order. If details are missing, ask a follow-up question for exactly those details and do not add it.
   If the drink is out of stock or not on the menu, say so and suggest 2-3 available alternatives from get_menu.
3. When valid, call update_cart with action "add" (or remove / update_quantity for changes).
Then confirm what changed using the price from the tool result, e.g. "1 x Large Latte (oat milk) - $5.35",
and ask whether they would like anything else. Never claim an item was added unless update_cart returned ok."""


def order_agent(state: CoffeeState) -> dict:
    ctx = {"cart": list(state.get("cart", []))}
    if state.get("fault_injection") and state.get("retry_count", 0) == 0:
        # Test hook for scenario 5: simulate an agent that skips the stock check and confirms anyway.
        bad = {"item": "Caramel Macchiato", "size": "medium", "milk": "whole", "extras": [],
               "unit_price": 5.00, "quantity": 1, "line_total": 5.00}
        return {"active_agent": "order_agent", "tool_log": [], "pending_cart": ctx["cart"] + [bad],
                "draft_response": "Done! I've added 1 x Medium Caramel Macchiato (whole milk) - $5.00 to your cart. Anything else?"}
    text, log = run_agent(ORDER_PROMPT.format(cart=_cart_text(ctx["cart"])) + _retry_hint(state), state,
                          [get_menu_tool, check_availability_tool, validate_order_tool, update_cart_tool], ctx)
    return {"active_agent": "order_agent", "draft_response": text, "tool_log": log, "pending_cart": ctx["cart"]}


# =========================================================================== placement agent
PLACEMENT_PROMPT = """You are the checkout assistant at a coffee shop.
Cart: {cart}
Customer name on file: {name}
Already asked the customer to confirm: {awaiting}

- If the cart is empty: do NOT place anything. Say the cart is empty and ask what they would like to order.
- If confirmation has not been asked yet: call calculate_total, show every line and the subtotal, tax and total,
  then ask the customer to confirm (and for a name for pickup if none is on file). Do not place the order yet.
- If confirmation was asked and the customer clearly agrees: call place_order with their name, then give the
  order ID and pickup time, e.g. "Order #1042 placed. Ready in about 8 minutes."
- If they decline or want changes, do not place the order; tell them they can keep editing their cart."""


def placement_agent(state: CoffeeState) -> dict:
    ctx = {"cart": list(state.get("cart", [])), "awaiting_confirmation": state.get("awaiting_confirmation", False),
           "customer_name": state.get("customer_name"), "order_id": None}
    prompt = PLACEMENT_PROMPT.format(cart=_cart_text(ctx["cart"]), name=ctx["customer_name"] or "(none)",
                                     awaiting=ctx["awaiting_confirmation"])
    text, log = run_agent(prompt + _retry_hint(state), state, [calculate_total_tool, place_order_tool], ctx)
    update = {"active_agent": "placement_agent", "draft_response": text, "tool_log": log}
    if ctx["order_id"]:                       # order submitted: start a fresh cart
        update.update(order_id=ctx["order_id"], customer_name=ctx["customer_name"], pending_cart=[])
    else:
        update["pending_cart"] = ctx["cart"]
    return update


# =========================================================================== evaluator
class Evaluation(BaseModel):
    correctness: bool = Field(description="Items, prices and totals match the tool output")
    completeness: bool = Field(description="Nothing required is missing (e.g. follow-up question, total, order ID)")
    no_hallucination: bool = Field(description="No drink, price, stock status or offer that is not backed by the menu/tool output")
    intent_match: bool = Field(description="The response answers what the customer actually asked")
    score: int = Field(ge=1, le=5, description="Overall quality 1-5")
    verdict: Literal["approved", "rejected"]
    feedback: str = Field(description="If rejected: what exactly is wrong and how to fix it. If approved: one short sentence.")


JUDGE_PROMPT = """You are a strict quality reviewer for a coffee shop assistant. Judge the DRAFT response
before the customer sees it, using this rubric:
1. Correctness - items and prices match the tool output and the menu.
2. Completeness - nothing required is missing.
3. No hallucination - no item, price, stock claim or offer outside the menu. Claiming an out-of-stock drink
   was added, or claiming a cart change that no update_cart call made, is a hallucination.
4. Intent match - it answers what the customer asked.
Reject if any criterion fails. Approve only with score >= 4."""


def evaluator(state: CoffeeState) -> dict:
    last_user = next(m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage))
    evidence = {
        "customer_message": last_user,
        "intent": state.get("intent"),
        "agent": state.get("active_agent"),
        "draft_response": state.get("draft_response"),
        "tool_calls_this_attempt": state.get("tool_log", []),
        "cart_before": state.get("cart", []),
        "cart_after": state.get("pending_cart", []),
        "menu_ground_truth": T.get_menu(),
    }
    judge = judge_llm.with_structured_output(Evaluation, method="json_schema")
    ev = judge.invoke([SystemMessage(JUDGE_PROMPT), HumanMessage(json.dumps(evidence, indent=1))])
    if ev.verdict == "approved" and ev.score < 4:
        ev.verdict = "rejected"
    evaluation = ev.model_dump()
    retries = state.get("retry_count", 0)

    if ev.verdict == "approved":
        # Commit: the customer sees the answer and the proposed cart becomes the real cart.
        tools_used = {c["tool"] for c in state.get("tool_log", [])}
        awaiting = (state["active_agent"] == "placement_agent" and "calculate_total" in tools_used
                    and not _placed_this_turn(state))
        return {"evaluation": evaluation, "messages": [AIMessage(state["draft_response"])],
                "cart": state.get("pending_cart", []), "awaiting_confirmation": awaiting}
    if retries < MAX_RETRIES:
        return {"evaluation": evaluation, "retry_count": retries + 1}
    # Out of retries: do not show the rejected draft or commit its cart change.
    evaluation["final"] = True
    return {"evaluation": evaluation, "awaiting_confirmation": False, "messages": [AIMessage(
        "Sorry, I wasn't able to handle that reliably. Could you rephrase, or ask to see the menu?")]}


def _placed_this_turn(state: CoffeeState) -> bool:
    return any(c["tool"] == "place_order" and c["result"].get("success") for c in state.get("tool_log", []))


def route_from_evaluator(state: CoffeeState) -> str:
    ev = state.get("evaluation", {})
    return "planner" if ev.get("verdict") == "rejected" and not ev.get("final") else END


# =========================================================================== graph
def build_app():
    g = StateGraph(CoffeeState)
    g.add_node("planner", planner)
    g.add_node("menu_agent", menu_agent)
    g.add_node("order_agent", order_agent)
    g.add_node("placement_agent", placement_agent)
    g.add_node("evaluator", evaluator)

    g.add_edge(START, "planner")
    g.add_conditional_edges("planner", route_from_planner,
                            {"menu_agent": "menu_agent", "order_agent": "order_agent",
                             "placement_agent": "placement_agent"})
    for agent in ("menu_agent", "order_agent", "placement_agent"):
        g.add_edge(agent, "evaluator")
    g.add_conditional_edges("evaluator", route_from_evaluator, {"planner": "planner", END: END})
    return g.compile(checkpointer=MemorySaver())


def new_turn(text: str, fault_injection: bool = False) -> dict:
    """Input for one customer message; resets the per-turn fields."""
    return {"messages": [HumanMessage(text)], "retry_count": 0, "evaluation": {}, "draft_response": "",
            "tool_log": [], "planner_note": "", "fault_injection": fault_injection}
