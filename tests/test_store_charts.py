from deye_bot import charts
from deye_bot.deye import Snapshot
from deye_bot.store import Store


def sample(ts, soc=50.0):
    return Snapshot(ts=ts, pv_w=1000 + ts % 7, load_w=500, grid_w=-200, battery_w=-300, soc=soc)


def test_store_roundtrip_and_window(tmp_path):
    st = Store(str(tmp_path / "x.db"))
    for ts in (1000, 2000, 90_000):
        st.add(sample(ts))
    st.add(sample(2000, soc=77))  # same timestamp replaces
    got = st.since(hours=1, now=90_000)
    assert [s.ts for s in got] == [90_000]
    allrows = st.since(hours=100, now=90_000)
    assert [s.ts for s in allrows] == [1000, 2000, 90_000]
    assert allrows[1].soc == 77


def test_chart_renders_png():
    png = charts.render([sample(1_700_000_000 + i * 300) for i in range(50)], 4)
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 5000


def test_chart_needs_data():
    assert charts.render([], 24) is None
    assert charts.render([sample(1)], 24) is None
