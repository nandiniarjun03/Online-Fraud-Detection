# Assignment 4 – Automated Coffee Ordering System (Multi-Agent LangGraph)

Nandini Arjun · Emp ID 81004545

| File | Purpose |
|---|---|
| `coffee_tools.py` | Menu database and the six tools (get_menu, check_availability, validate_order, update_cart, calculate_total, place_order) |
| `coffee_graph.py` | Shared state, planner, menu/order/placement agents, evaluator, LangGraph wiring |
| `run_scenarios.py` | Runs the six test scenarios (plus 5b, the fault-injected retry demo) and writes `scenario_log.json` |
| `build_report.py`, `pdfkit_common.py` | Build `Assignment4_81004545_Nandini.pdf` from the code, graph and log |
| `graph.png`, `graph.mmd` | Graph diagram generated from LangGraph (`draw_mermaid`) |

## Run

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
python run_scenarios.py          # live run, writes scenario_log.json
python build_report.py           # writes Assignment4_81004545_Nandini.pdf
```
