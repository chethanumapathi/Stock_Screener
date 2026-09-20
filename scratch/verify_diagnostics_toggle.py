import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"

def test_diagnostics_decoupling():
    # Wait for server ready
    for _ in range(15):
        try:
            r = requests.get(f"{BASE_URL}/api/status", timeout=2)
            if r.status_code == 200:
                print("Server is UP!")
                break
        except Exception:
            time.sleep(0.5)

    with open('data/backtest_strategies.json', 'r', encoding='utf-8') as f:
        strats = json.load(f)
    target = next(s for s in strats if 'Weekly Yearly-R1' in s['name'])
    strat_code = target['code']

    print("\n--- 1. Testing POST /api/backtest (Should skip heavy diagnostics) ---")
    t0 = time.time()
    resp = requests.post(f"{BASE_URL}/api/backtest", json={
        "code": strat_code,
        "segment": "nifty50",
        "timeframe": "1d",
        "start_date": "2023-01-01",
        "end_date": "2026-09-20",
        "capital_per_trade": 100000.0,
        "slippage_pct": 0.5,
        "include_brokerage": True,
        "include_taxes": True,
        "brokerage_per_order": 20.0,
        "min_market_cap_cr": 0.0
    }, timeout=60)
    elapsed = time.time() - t0
    print(f"Backtest took: {elapsed:.2f}s, HTTP status: {resp.status_code}")
    assert resp.status_code == 200, f"Backtest failed: {resp.text}"
    bt_data = resp.json()
    
    trades = bt_data.get("trades", [])
    diag = bt_data.get("diagnostics", {})
    overall_rep = bt_data.get("overall_report", {})
    print(f"Total trades returned: {len(trades)}")
    print(f"Diagnostics dict empty as required: {diag == {}} (keys: {list(diag.keys())})")
    print(f"Overall report Ulcer Index: {overall_rep.get('ulcer_index')}, Recovery Factor: {overall_rep.get('recovery_factor')}")
    assert diag == {}, f"Diagnostics MUST be empty on run backtest! Got: {diag.keys()}"

    # 2. Export PDF WITHOUT diagnostics (Should be 2 pages)
    print("\n--- 2. Testing PDF Export without diagnostics ---")
    pdf_resp_no_diag = requests.post(f"{BASE_URL}/api/export-backtest-pdf", json={
        "strategy_name": "Test_RSI_No_Diag",
        "timeframe": "1d",
        "duration_seconds": elapsed,
        "capital_per_trade": 100000.0,
        "slippage_pct": 0.5,
        "brokerage_per_order": 20.0,
        "overall_report": overall_rep,
        "year_wise_returns": bt_data.get("year_wise_returns", []),
        "drawdown_chart": bt_data.get("drawdown_chart", {}),
        "diagnostics": {},
        "summary": bt_data.get("summary", {})
    }, timeout=30)
    assert pdf_resp_no_diag.status_code == 200, f"PDF export failed: {pdf_resp_no_diag.text}"
    pdf_no_diag_bytes = pdf_resp_no_diag.content
    print(f"PDF bytes without diagnostics: {len(pdf_no_diag_bytes)} bytes")

    # 3. Call /api/backtest/diagnostics on demand
    print("\n--- 3. Testing POST /api/backtest/diagnostics on demand ---")
    t0_diag = time.time()
    diag_resp = requests.post(f"{BASE_URL}/api/backtest/diagnostics", json={
        "trades": trades,
        "capital_per_trade": 100000.0,
        "slippage_pct": 0.5,
        "include_brokerage": True,
        "include_taxes": True,
        "brokerage_per_order": 20.0
    }, timeout=60)
    diag_elapsed = time.time() - t0_diag
    print(f"Diagnostics took: {diag_elapsed:.2f}s, HTTP status: {diag_resp.status_code}")
    assert diag_resp.status_code == 200, f"Diagnostics failed: {diag_resp.text}"
    diag_res_data = diag_resp.json()
    full_diag = diag_res_data.get("diagnostics", {})
    print(f"Diagnostics computed on demand keys: {list(full_diag.keys())}")
    assert "benchmark_comparison" in full_diag, "Missing benchmark_comparison"
    assert "monte_carlo" in full_diag, "Missing monte_carlo"
    assert "out_of_sample_split" in full_diag, "Missing out_of_sample_split"

    # 4. Export PDF WITH diagnostics (Should be 4 pages)
    print("\n--- 4. Testing PDF Export WITH diagnostics ---")
    pdf_resp_with_diag = requests.post(f"{BASE_URL}/api/export-backtest-pdf", json={
        "strategy_name": "Test_RSI_With_Diag",
        "timeframe": "1d",
        "duration_seconds": elapsed,
        "capital_per_trade": 100000.0,
        "slippage_pct": 0.5,
        "brokerage_per_order": 20.0,
        "overall_report": overall_rep,
        "year_wise_returns": bt_data.get("year_wise_returns", []),
        "drawdown_chart": bt_data.get("drawdown_chart", {}),
        "diagnostics": full_diag,
        "summary": bt_data.get("summary", {})
    }, timeout=30)
    assert pdf_resp_with_diag.status_code == 200, f"PDF export failed: {pdf_resp_with_diag.text}"
    pdf_with_diag_bytes = pdf_resp_with_diag.content
    print(f"PDF bytes WITH diagnostics: {len(pdf_with_diag_bytes)} bytes")

    # Check page count using pypdf or PyPDF2 if available
    try:
        import pypdf
        import io
        reader_no = pypdf.PdfReader(io.BytesIO(pdf_no_diag_bytes))
        reader_with = pypdf.PdfReader(io.BytesIO(pdf_with_diag_bytes))
        print(f"\n[PAGE COUNT CHECK]")
        print(f"Pages WITHOUT diagnostics: {len(reader_no.pages)} (Expected: 2)")
        print(f"Pages WITH diagnostics: {len(reader_with.pages)} (Expected: 4)")
        assert len(reader_no.pages) == 2, f"Expected 2 pages without diagnostics, got {len(reader_no.pages)}"
        assert len(reader_with.pages) == 4, f"Expected 4 pages with diagnostics, got {len(reader_with.pages)}"
    except ImportError:
        try:
            import PyPDF2
            import io
            reader_no = PyPDF2.PdfReader(io.BytesIO(pdf_no_diag_bytes))
            reader_with = PyPDF2.PdfReader(io.BytesIO(pdf_with_diag_bytes))
            print(f"\n[PAGE COUNT CHECK (PyPDF2)]")
            print(f"Pages WITHOUT diagnostics: {len(reader_no.pages)} (Expected: 2)")
            print(f"Pages WITH diagnostics: {len(reader_with.pages)} (Expected: 4)")
            assert len(reader_no.pages) == 2, f"Expected 2 pages without diagnostics, got {len(reader_no.pages)}"
            assert len(reader_with.pages) == 4, f"Expected 4 pages with diagnostics, got {len(reader_with.pages)}"
        except ImportError:
            print("Note: pypdf/PyPDF2 not installed for page counting, but both PDFs generated successfully.")

    print("\nALL BACKEND & PDF VERIFICATIONS PASSED PERFECTLY!")

if __name__ == "__main__":
    test_diagnostics_decoupling()
