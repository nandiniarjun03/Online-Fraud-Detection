"""Build Assignment4_81004545_Nandini.pdf from the source files, graph image and scenario log."""
import ast
import json
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Frame, Image, KeepTogether, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)

import pdfkit_common as K
from pdfkit_common import ACCENT, ACCENT_SOFT, INK, MUTED, RULE, C, P, body, bullets, cell, code_block, h1, h2, note, small, table

HERE = Path(__file__).resolve().parent
K.REPO = HERE
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "Assignment4_81004545_Nandini.pdf"
LOG = HERE / "scenario_log.json"

NAME, EMP_ID = "Nandini Arjun", "81004545"
TITLE = "Assignment 4: Automated Coffee Ordering System using Multi-Agent LangGraph"


# --------------------------------------------------------------------------- code extraction
def code_of(path, *names, title=None):
    """Return a highlighted code block for top-level defs/classes/assignments, by name, in file order."""
    src = (HERE / path).read_text().split("\n")
    tree = ast.parse("\n".join(src))
    spans = []
    for node in tree.body:
        n = getattr(node, "name", None)
        if n is None and isinstance(node, (ast.Assign, ast.AnnAssign)):
            tgt = node.targets[0] if isinstance(node, ast.Assign) else node.target
            n = getattr(tgt, "id", None)
        if n in names:
            start = min([d.lineno for d in getattr(node, "decorator_list", [])] + [node.lineno])
            spans.append((start, node.end_lineno))
    assert len(spans) == len(names), (path, names, spans)
    parts = []
    for i, (a, b) in enumerate(spans):
        parts.append("\n".join(src[a - 1:b]))
    text = "\n\n".join(parts)
    return code_block(text, "python", title or f"{path} - {', '.join(names)}")


# --------------------------------------------------------------------------- page template
class Doc(BaseDocTemplate):
    def __init__(self, fn, **kw):
        super().__init__(fn, **kw)
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="f")
        self.addPageTemplates([PageTemplate("p", frames=[frame], onPage=self.decorate)])

    def afterFlowable(self, f):
        if isinstance(f, Paragraph) and f.style.name in ("h1", "h2"):
            level = 0 if f.style.name == "h1" else 1
            key = f"k{id(f)}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(f.getPlainText(), key, level)

    @staticmethod
    def decorate(c, doc):
        w, h = A4
        c.saveState()
        c.setFont("Sans", 7.5)
        c.setFillColor(MUTED)
        c.drawString(doc.leftMargin, h - 12 * mm, f"Assignment 4 - Multi-Agent Coffee Ordering System")
        c.drawRightString(w - doc.rightMargin, h - 12 * mm, f"{NAME}  |  Emp ID {EMP_ID}")
        c.setStrokeColor(RULE)
        c.setLineWidth(0.5)
        c.line(doc.leftMargin, h - 14 * mm, w - doc.rightMargin, h - 14 * mm)
        c.line(doc.leftMargin, 13 * mm, w - doc.rightMargin, 13 * mm)
        c.drawRightString(w - doc.rightMargin, 9 * mm, f"Page {doc.page}")
        c.restoreState()


# --------------------------------------------------------------------------- transcript helpers
bubble_user = ParagraphStyle("bu", parent=body, fontSize=9, leading=12.5, spaceAfter=0)
bubble_bot = ParagraphStyle("bb", parent=body, fontSize=9, leading=12.5, spaceAfter=0)
meta = ParagraphStyle("meta", parent=small, fontSize=7.8, leading=10.5, spaceAfter=0)


def esc(t):
    return K.esc(str(t))


def md_inline(t):
    """Very small markdown -> ReportLab markup (bold, line breaks, bullets)."""
    import re
    t = esc(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    lines = []
    for line in t.split("\n"):
        s = line.strip()
        if s.startswith(("- ", "* ", "• ")):
            s = "• " + s[2:]
        if s.startswith("|") and set(s.replace("|", "").strip()) <= set("-: "):
            continue                                  # markdown table rule
        if s.startswith("|"):
            s = "   ".join(x.strip() for x in s.strip("|").split("|"))
        if s.startswith("#"):
            s = "<b>" + s.lstrip("# ") + "</b>"
        lines.append(s)
    return "<br/>".join(lines)


def bubble(text, who):
    style = bubble_user if who == "user" else bubble_bot
    label = "Customer" if who == "user" else "Assistant"
    fill = colors.HexColor("#eef2f7") if who == "user" else ACCENT_SOFT
    t = Table([[Paragraph(f"<b>{label}:</b> " + md_inline(text), style)]], colWidths=[None])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), fill),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                           ("LINEBEFORE", (0, 0), (0, -1), 2.5, ACCENT if who != "user" else MUTED)]))
    return t


def fmt_args(a):
    return ", ".join(f"{k}={json.dumps(v)}" for k, v in a.items()) if a else ""


def cart_line(cart):
    if not cart:
        return "empty"
    return "; ".join(f"{l['quantity']} x {l['size'].title()} {l['item']}"
                     + (f" ({l['milk']} milk)" if l["milk"] != "none" else "")
                     + (f" + {', '.join(l['extras'])}" if l["extras"] else "")
                     + f" ${l['line_total']:.2f}" for l in cart)


def turn_block(r):
    items = [bubble(r["user"], "user"), Spacer(1, 4)]
    trace = [f"<b>Flow:</b> {' → '.join(r['path'])}"]
    for i, a in enumerate(r["attempts"], 1):
        tools = "; ".join(f"{t['tool']}({esc(fmt_args(t['args']))})" for t in a.get("tools", [])) or "none"
        ev = a.get("evaluation") or {}
        trace.append(f"<b>Attempt {i}</b> - planner intent: <b>{a.get('intent')}</b> → {a.get('agent')}")
        trace.append(f"&nbsp;&nbsp;Tool calls: {tools}")
        if r.get("fault_injection") and i == 1:
            trace.append(f"&nbsp;&nbsp;Draft (fault injected): <i>{esc(a.get('draft'))}</i>")
        trace.append(f"&nbsp;&nbsp;Evaluator: <b>{ev.get('verdict')}</b>, score {ev.get('score')}/5 - {esc(ev.get('feedback'))}")
    trace.append(f"<b>Cart after turn:</b> {esc(cart_line(r['cart']))}"
                 + (f"   <b>Order ID:</b> {r['order_id']}" if r.get("order_id") else "")
                 + f"   <b>Retries used:</b> {r['retry_count']}")
    t = Table([[Paragraph("<br/>".join(trace), meta)]], colWidths=[None])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, RULE), ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    items += [t, Spacer(1, 4), bubble(r["response"], "bot"), Spacer(1, 12)]
    return items


# --------------------------------------------------------------------------- scenario checks
def check(results):
    """Return (scenario, verdict text) per scenario, judged from the log against the brief."""
    by = {}
    for r in results:
        by.setdefault(r["scenario"].split(".")[0] + ("b" if "5b" in r["scenario"] else ""), []).append(r)
    out = []

    def flow(r):
        return " → ".join(n for n in r["path"] if n not in ("__start__", "__end__"))

    r = by["1"][0]
    ok = r["attempts"][-1].get("agent") == "menu_agent" and any(t["tool"] == "get_menu" for t in r["attempts"][-1]["tools"])
    out.append(("1. Browse the menu", r["user"], flow(r), "Menu listed from get_menu, cart untouched", ok))
    r = by["2"][0]
    ok = any(l["item"] == "Latte" and l["size"] == "large" and l["milk"] == "oat" for l in r["cart"])
    out.append(("2. Build an order", r["user"], flow(r), "Large oat-milk latte added at tool price", ok))
    r1, r2 = by["3"]
    ok = not any(l["item"] == "Cappuccino" for l in r1["cart"]) and any(l["item"] == "Cappuccino" for l in r2["cart"])
    out.append(("3. Incomplete order", r1["user"], flow(r1), "Asked for size and milk; added only after reply", ok))
    r1, r2 = by["4"]
    ok = r1["awaiting_confirmation"] and not r1.get("order_id") and bool(r2.get("order_id"))
    out.append(("4. Place the order", r1["user"], flow(r1), f"Summary + total, then {r2.get('order_id')} after confirmation", ok))
    r = by["5"][0]
    ok = not r["cart"]
    out.append(("5. Unavailable item", r["user"], flow(r), "Out of stock reported, alternatives offered", ok))
    r = by["5b"][0]
    ok = r["attempts"][0]["evaluation"]["verdict"] == "rejected" and r["retry_count"] >= 1 and not r["cart"]
    out.append(("5b. Retry loop (fault injected)", r["user"], flow(r), "Bad draft rejected, retry produced correct answer", ok))
    r = by["6"][0]
    placed = any(t["tool"] == "place_order" for a in r["attempts"] for t in a.get("tools", []))
    ok = not r.get("order_id") and not r["cart"]
    out.append(("6. Empty cart", r["user"], flow(r),
                "Refused to place, asked what they would like" + (" (place_order refused by guardrail)" if placed else ""), ok))
    return out


# --------------------------------------------------------------------------- content
def build():
    doc = Doc(str(OUT), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=20 * mm,
              bottomMargin=18 * mm, title=TITLE, author=NAME, subject="Assignment 4 - Multi AI Agents")
    FW = doc.width
    results = json.loads(LOG.read_text()) if LOG.exists() else None
    s = []

    # ---- title block
    title_tbl = Table([[Paragraph(f'<font color="#ffffff" size="15"><b>{TITLE}</b></font>',
                                  ParagraphStyle("tt", leading=20))],
                       [Paragraph(f'<font color="#f4ece4" size="9.5">Name: <b>{NAME}</b> &nbsp;&nbsp;|&nbsp;&nbsp; '
                                  f'Emp ID: <b>{EMP_ID}</b> &nbsp;&nbsp;|&nbsp;&nbsp; Stack: LangGraph · LangChain · '
                                  f'Claude (Anthropic API)</font>', ParagraphStyle("ts", leading=13))]],
                      colWidths=[FW])
    title_tbl.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), ACCENT),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                                   ("TOPPADDING", (0, 0), (-1, 0), 12), ("BOTTOMPADDING", (0, -1), (-1, -1), 12)]))
    s += [title_tbl, Spacer(1, 10)]
    s += table(["Deliverable", "Where in this document"], [
        ["1. Source code", "Section 3 (walkthrough of every component); full files coffee_tools.py, coffee_graph.py, run_scenarios.py submitted alongside"],
        ["2. Graph diagram generated from LangGraph", "Section 2"],
        ["3. Short report (architecture, design choices, test results)", "Section 1"],
        ["4. Logs of all six test scenarios", "Section 4"],
    ], [62 * mm, FW - 62 * mm])

    # ---- 1. report
    s.append(P("1. Short Report", h1))
    s.append(P("1.1 Architecture", h2))
    s.append(P(
        "The system is a LangGraph <font face='Mono'>StateGraph</font> with five nodes. Every customer message enters "
        "the <b>planner</b>, which classifies the intent with a structured LLM call and writes it to state. A routing "
        "function reads the intent and sends the turn to exactly one specialist: the <b>menu agent</b>, the <b>order "
        "agent</b> or the <b>placement agent</b>. Each specialist runs its own tool-calling loop over a restricted set of "
        "tools and produces a <i>draft</i> answer. The draft always goes to the <b>evaluator</b> (LLM-as-judge), which "
        "either approves it, so it is delivered to the customer and the turn ends, or rejects it and sends the turn back "
        "to the planner with feedback, up to two retries."))
    s += table(["Node", "Responsibility", "Tools it may call"], [
        ["planner", "Classify the latest message as browse_menu, build_order or place_order", "none (structured output)"],
        ["menu_agent", "Drinks, sizes, milks, add-ons, prices and stock - only from tool output", "get_menu, check_availability"],
        ["order_agent", "Extract items + customisations, ask for missing details, maintain the cart",
         "get_menu, check_availability, validate_order, update_cart"],
        ["placement_agent", "Show cart and total, ask to confirm, then submit and return order ID", "calculate_total, place_order"],
        ["evaluator", "Score the draft on the 4-point rubric; approve, or reject and trigger a retry", "none (structured output)"],
    ], [32 * mm, 80 * mm, FW - 112 * mm])
    s.append(P(
        f"Edges: {C('START → planner')} (normal); {C('planner → agents')} (conditional, via "
        f"{C('route_from_planner')}); {C('agent → evaluator')} (normal, one per agent); {C('evaluator → END | planner')} "
        f"(conditional, via {C('route_from_evaluator')}). State is persisted per conversation with LangGraph's "
        f"{C('MemorySaver')} checkpointer, keyed by {C('thread_id')}, so the cart survives across turns."))

    s.append(P("1.2 Design choices", h2))
    s += bullets([
        "<b>Facts come from code, not the model.</b> The six tools are deterministic Python functions over a menu dictionary "
        "(prices per size, milk and add-on surcharges, stock flags). Agents must call them; the evaluator receives the same "
        "menu as ground truth, so an invented drink or price is caught.",
        "<b>The model never edits the cart directly.</b> Tools that need the cart (update_cart, calculate_total, place_order) "
        "get it injected from graph state. update_cart re-runs validate_order on every add, so an invalid or out-of-stock "
        "item cannot enter the cart even if an agent tries.",
        "<b>Draft-then-commit.</b> An agent writes only <i>draft_response</i> and <i>pending_cart</i>. The evaluator commits "
        "both (adds the answer to messages, copies pending_cart to cart) only on approval. A rejected attempt therefore never "
        "reaches the customer and its cart changes are discarded before the retry.",
        "<b>Hard guardrails for checkout.</b> place_order is refused in code when the cart is empty or when the customer has "
        "not yet been shown the total and asked to confirm (state flag <i>awaiting_confirmation</i>).",
        "<b>Structured outputs.</b> The planner returns a Pydantic <i>PlannerDecision</i> and the evaluator an <i>Evaluation</i> "
        "(four rubric booleans, score 1-5, verdict, feedback) using Claude's JSON-schema structured output, so routing never "
        "depends on parsing free text. Approval also requires a score of at least 4.",
        "<b>Retry loop with feedback.</b> On rejection the evaluator increments <i>retry_count</i>; the planner re-routes and "
        "passes the evaluator's feedback into the agent's prompt. After 2 retries the turn ends with a safe apology instead "
        "of the rejected draft. retry_count is reset at the start of every customer turn.",
        "<b>Model.</b> Claude Opus 5.5 through langchain-anthropic; low effort for the chat agents and planner (fast replies), "
        "medium effort for the evaluator, which needs more careful checking.",
    ])

    s.append(CondPageBreak(70 * mm))
    s.append(P("1.3 Test results", h2))
    if results:
        rows = [[a, f"“{esc(u)}”", f, d, "<b>Pass</b>" if ok else "<b>Fail</b>"] for a, u, f, d, ok in check(results)]
        s += table(["Scenario", "Customer message", "Flow", "Observed result", ""], rows,
                   [30 * mm, 33 * mm, 47 * mm, FW - 125 * mm, 15 * mm])
        s.append(P("All runs used the live model; the complete transcript with tool calls and evaluator verdicts for every "
                   "turn is in Section 4. Scenario 5b deliberately injects a faulty first draft (an agent that skips the "
                   "stock check and confirms the out-of-stock drink) to demonstrate that the evaluator rejects it and the "
                   "retry loop recovers, because with a correctly behaving agent the retry path is rarely exercised.", small))
    else:
        s += note("The six scenarios have not been run yet. They need live calls to Claude, and no API key was "
                  "available when this document was generated. Section 4 lists the planned test script and the "
                  "expected behaviour; running run_scenarios.py and then build_report.py fills in this table and "
                  "the logs automatically.", "Not yet run")
    s.append(P("1.4 Conclusion", h2))
    s.append(P(
        "Splitting the work into a planner, three single-purpose agents and an independent judge makes the system easy to "
        "reason about: each agent has a short prompt and only the tools it needs, while correctness-critical rules (prices, "
        "stock, empty-cart and confirmation checks) live in code. The evaluator adds a second line of defence for anything "
        "the prompts miss. Natural extensions are a real inventory database, payment, order-status tracking and "
        "streaming the replies to a chat UI."))

    # ---- 2. graph
    s.append(PageBreak())
    s.append(P("2. Graph Diagram (generated from LangGraph)", h1))
    s.append(P(f"Rendered from {C('app.get_graph().draw_mermaid()')}. Solid arrows are normal edges; dashed arrows are "
               "conditional edges. The dashed evaluator → planner edge is the retry loop."))
    img = Image(str(HERE / "graph.png"))
    ratio = img.imageHeight / img.imageWidth
    img.drawWidth, img.drawHeight = 120 * mm, 120 * mm * ratio
    s += [img, Spacer(1, 8)]
    s += code_block((HERE / "graph.mmd").read_text().strip(), "text", "Mermaid source produced by LangGraph")

    # ---- 3. code
    s.append(PageBreak())
    s.append(P("3. Implementation", h1))
    s.append(P(f"The code is split into {C('coffee_tools.py')} (menu database and the six business tools), "
               f"{C('coffee_graph.py')} (state, agents, evaluator and graph) and {C('run_scenarios.py')} (test driver)."))
    s.append(P("3.1 Menu database", h2))
    s.append(P("Prices are per size; milk and add-ons add a surcharge. Caramel Macchiato is deliberately out of stock "
               "for scenario 5. The milk rule per drink (required / optional / not allowed) drives the follow-up questions."))
    s += code_of("coffee_tools.py", "MENU", "TAX_RATE")
    s.append(P("3.2 The six tools", h2))
    s += table(["Tool", "Used by", "Input → Output"], [
        [C("get_menu"), "menu_agent, order_agent", "optional category → menu JSON (drinks, prices, stock, milks, add-ons)"],
        [C("check_availability"), "menu_agent, order_agent", "item name → on_menu / available flags"],
        [C("validate_order"), "order_agent", "item, size, milk, extras → valid / invalid + reason + missing fields + unit price"],
        [C("update_cart"), "order_agent", "cart, action, item → updated cart (add re-validates)"],
        [C("calculate_total"), "placement_agent", "cart → subtotal, 8% tax, total"],
        [C("place_order"), "placement_agent", "cart, customer name → order ID, pickup minutes"],
    ], [34 * mm, 38 * mm, FW - 72 * mm])
    s += code_of("coffee_tools.py", "get_menu", "check_availability", title="coffee_tools.py - get_menu, check_availability")
    s += code_of("coffee_tools.py", "validate_order")
    s += code_of("coffee_tools.py", "update_cart")
    s += code_of("coffee_tools.py", "calculate_total", "place_order")

    s.append(P("3.3 Shared state", h2))
    s.append(P(f"{C('messages')} uses LangGraph's {C('add_messages')} reducer and holds only approved replies. "
               f"{C('cart')} is the committed cart; {C('pending_cart')} and {C('draft_response')} hold the current attempt "
               "until the evaluator approves it."))
    s += code_of("coffee_graph.py", "CoffeeState")

    s.append(P("3.4 Tool binding and the agent loop", h2))
    s.append(P(f"Tools are declared with LangChain's {C('@tool')} and bound with {C('bind_tools')}. The model only sees "
               f"the arguments it should choose; {C('_execute')} maps each call to the real function and injects the cart "
               "and checkout state. The place_order guardrails live here."))
    s += code_of("coffee_graph.py", "update_cart_tool", "place_order_tool", title="coffee_graph.py - two of the LLM-facing tool declarations")
    s += code_of("coffee_graph.py", "_execute", "run_agent")

    s.append(P("3.5 Planner agent and routing", h2))
    s += code_of("coffee_graph.py", "PlannerDecision", "PLANNER_PROMPT", "planner", "route_from_planner")
    s.append(P("3.6 Menu agent", h2))
    s += code_of("coffee_graph.py", "MENU_PROMPT", "menu_agent")
    s.append(P("3.7 Order agent", h2))
    s.append(P("The fault-injection branch is a test hook used only by scenario 5b; it is off for normal use."))
    s += code_of("coffee_graph.py", "ORDER_PROMPT", "order_agent")
    s.append(P("3.8 Placement agent", h2))
    s += code_of("coffee_graph.py", "PLACEMENT_PROMPT", "placement_agent")
    s.append(P("3.9 Evaluator agent and retry routing", h2))
    s += code_of("coffee_graph.py", "Evaluation", "JUDGE_PROMPT")
    s += code_of("coffee_graph.py", "evaluator", "_placed_this_turn", "route_from_evaluator")
    s.append(P("3.10 Building the graph", h2))
    s += code_of("coffee_graph.py", "build_app", "new_turn")
    s.append(P("3.11 Running a turn and capturing the trace", h2))
    s += code_of("run_scenarios.py", "SCRIPT", "run_turn")

    # ---- 4. logs
    s.append(PageBreak())
    s.append(P("4. Test Scenario Logs", h1))
    if results:
        s.append(P("Captured from the live run with LangGraph's update stream. Scenarios 1-4 are one continuous conversation "
                   "(thread <i>main</i>), so the cart carries over; 5, 5b and 6 each use a fresh thread with an empty cart."))
        current = None
        for r in results:
            if r["scenario"] != current:
                current = r["scenario"]
                s.append(CondPageBreak(60 * mm))
                s.append(P(f"Scenario {current}", h2))
            s += turn_block(r)
    else:
        s += note("No live run yet - see the note in Section 1.3. These are the planned test turns and the "
                  "behaviour each one is expected to produce.", "Not yet run")
        s += table(["Scenario", "Thread", "Customer message", "Expected behaviour"], [
            ["1. Browse the menu", "main", "What coffees do you have?", "planner → menu_agent → evaluator → end; drinks and prices from get_menu, Caramel Macchiato marked out of stock"],
            ["2. Build an order", "main", "I want a large latte with oat milk.", "planner → order_agent → evaluator → end; 1 x Large Latte (oat milk) $5.35 added, asks for anything else"],
            ["3. Incomplete order", "main", "Get me a cappuccino.", "validate_order reports size and milk missing; agent asks for them, nothing added"],
            ["3. (follow-up)", "main", "Medium, with whole milk please.", "Medium Cappuccino (whole milk) $4.25 added"],
            ["4. Place the order", "main", "That's all, place my order.", "planner → placement_agent; cart, subtotal, 8% tax, total; asks to confirm and for a name"],
            ["4. (confirm)", "main", "Yes, confirm it. The name is Nandini.", "place_order returns order ID (e.g. #1042) and pickup time"],
            ["5. Unavailable item", "s5", "One caramel macchiato.", "Out of stock reported, 2-3 alternatives suggested, cart stays empty"],
            ["5b. Retry (fault injected)", "s5b", "One caramel macchiato.", "Forced bad draft rejected by evaluator → planner retry → correct out-of-stock answer"],
            ["6. Empty cart", "s6", "Place my order.", "Refuses to place (guardrail), asks what they would like"],
        ], [30 * mm, 16 * mm, 44 * mm, FW - 90 * mm])

    s.append(CondPageBreak(50 * mm))
    s.append(P("How to run", h2))
    s += code_block("pip install langgraph langchain-anthropic\n"
                    "export ANTHROPIC_API_KEY=...        # your key\n"
                    "python run_scenarios.py              # runs all scenarios, writes scenario_log.json", "bash", "Terminal")
    doc.build(s)
    print("wrote", OUT)


if __name__ == "__main__":
    build()
