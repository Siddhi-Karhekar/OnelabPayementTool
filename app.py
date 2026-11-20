"""Month-End Reconciliation Assistant — Streamlit UI. Run: streamlit run app.py"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.generate_data import generate, save
from src.money import fmt_inr
from src.reconcile import CATEGORIES, LABELS, read_settlements, read_transactions, reconcile, summary_line

ASSUMPTIONS = """
1. Single currency INR. Reconciliation month: **October 2026**.
2. One settlement record per transaction, linked by `txn_id`, settled 1–2 days after payment.
3. Platform stores amounts to 4 decimals; the bank settles each amount rounded **half-up** to 2 decimals.
   All money uses Python `Decimal` (never float, never `round()`).
4. Refunds are negative transactions with `type="refund"` and an `original_txn_id`.
5. Per-row rounding tolerance: ≤ ₹0.01.
6. Matching is at the transaction level against the processor's itemised settlement report.
   Real banks deposit in batches; deposit-level matching is out of scope (next step).
   Fees, FX and chargebacks are out of scope.
7. A refund with no original sale is not processed by the bank, so it has no settlement row.
8. Each record is classified once, in this order: duplicate → orphan refund → late → rounding → unexplained.
"""

SIGN_NOTE = ("Negative = money the platform recorded that the bank hasn't paid yet; "
             "positive = money the bank paid that the platform didn't expect.")

st.set_page_config(page_title="Month-End Reconciliation Assistant", layout="wide")
st.title("Month-End Reconciliation Assistant")
st.caption("Why don't October's platform transactions match the bank's settlements?")


def load_data():
    """Sidebar: generate sample data or upload CSVs. Returns (txns, setts, planted or None)."""
    with st.sidebar:
        st.header("Data")
        source = st.radio("Source", ["Generate sample data", "Upload CSVs"])
        if source == "Generate sample data":
            seed = st.number_input("Seed", min_value=0, value=42, step=1)
            t, s, planted = generate(seed=int(seed))
            save(t, s, planted)
            return t, s, planted
        t_file = st.file_uploader("transactions.csv", type="csv")
        s_file = st.file_uploader("settlements.csv", type="csv")
        if not (t_file and s_file):
            st.info("Upload both files to reconcile.")
            st.stop()
        return read_transactions(t_file), read_settlements(s_file), None


def show_metrics(result):
    c1, c2, c3 = st.columns(3)
    c1.metric("Platform total", fmt_inr(result["platform_total"]))
    c2.metric("Bank total", fmt_inr(result["bank_total"]))
    c3.metric("Gap (Bank − Platform)", fmt_inr(result["total_gap"]))


def show_waterfall(result):
    """Platform total → each gap category → Bank total. Floats are used for drawing only."""
    keys = [*CATEGORIES, "unexplained"]
    labels = ["Platform total", *[LABELS[k] for k in keys], "Bank total"]
    values = [result["platform_total"], *[result["bridge"][k] for k in keys], result["bank_total"]]
    fig = go.Figure(go.Waterfall(
        x=labels, y=[float(v) for v in values],
        measure=["absolute", *["relative"] * len(keys), "total"],
        text=[fmt_inr(v) for v in values], textposition="outside",
    ))
    levels, running = [], float(values[0])
    for v in values[1:-1]:
        running += float(v)
        levels.append(running)
    levels += [float(values[0]), float(values[-1])]
    pad = max(max(levels) - min(levels), 1.0) * 0.35
    fig.update_layout(height=420, showlegend=False, margin=dict(t=30, b=20),
                      yaxis=dict(range=[min(levels) - pad, max(levels) + pad], tickprefix="₹"))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Y-axis is zoomed to the gap range so small categories are visible.")


def show_self_check(result, planted):
    """Planted vs detected, one row per gap type (generated data only)."""
    gaps = result["gaps"]
    rows = []
    for c in CATEGORIES:
        found = set(gaps.loc[gaps.category == c, "txn_id"])
        ok = found == set(planted[c])
        rows.append({"Gap type": LABELS[c], "Planted": len(planted[c]), "Detected": len(found),
                     "Match": "✅" if ok else "❌"})
    passed = sum(r["Match"] == "✅" for r in rows)
    st.subheader(f"Self-check: Planted vs Detected {passed}/{len(rows)} {'✅' if passed == len(rows) else '❌'}")
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def display_table(gaps, places):
    """Format money columns as ₹ strings for display."""
    out = gaps.copy()
    for col in ["platform_amount", "bank_amount", "impact"]:
        out[col] = out[col].map(lambda v: fmt_inr(v, places))
    return out.drop(columns="category")


def show_gap_tabs(result):
    gaps = result["gaps"]
    keys = [*CATEGORIES, "unexplained"]
    tabs = st.tabs([f"{LABELS[k]} ({(gaps.category == k).sum()})" for k in keys])
    for tab, key in zip(tabs, keys):
        with tab:
            rows = gaps[gaps.category == key]
            if rows.empty:
                st.success("No gaps in this category.")
                continue
            st.write(f"**Impact: {fmt_inr(result['bridge'][key])}** · Action: {rows.suggested_action.iloc[0]}")
            places = 4 if key == "rounding" else 2  # 4 dp so the sub-paisa differences are visible
            st.dataframe(display_table(rows, places), hide_index=True, use_container_width=True)


def main():
    transactions, settlements, planted = load_data()
    with st.sidebar.expander("Assumptions"):
        st.markdown(ASSUMPTIONS)
    result = reconcile(transactions, settlements, month="2026-10")
    show_metrics(result)
    show_waterfall(result)
    st.markdown(f"**{summary_line(result)}**")
    st.caption(SIGN_NOTE)
    if planted is not None:
        show_self_check(result, planted)
    st.subheader("Gaps by category")
    show_gap_tabs(result)
    report = result["gaps"].assign(category=result["gaps"].category.map(LABELS))
    st.download_button("Download full gap report (CSV)", report.to_csv(index=False),
                       file_name="gap_report_2026-10.csv", mime="text/csv")


main()
